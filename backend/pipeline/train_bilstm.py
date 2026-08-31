import os
import json
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.metrics import f1_score, confusion_matrix
import numpy as np
from transformers import AutoTokenizer, AutoModel
import gc

from backend.models.risk_classifier import BiLSTMRiskModel, _labels

class ClauseDataset(Dataset):
    def __init__(self, data_path, is_train=False):
        self.samples = []
        self.is_train = is_train
        
        # Build raw texts and labels
        label_map = {"Low": 0, "Medium": 1, "High": 2}
        
        with open(data_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                rec = json.loads(line)
                
                # Exclude impossible clauses from training
                if rec.get("is_impossible"):
                    continue
                    
                risk = rec.get("risk_level", "Unknown")
                if risk not in label_map:
                    continue # Skip unknowns
                    
                text = rec.get("clause_text", "")
                self.samples.append((text, label_map[risk]))
                
    def __len__(self):
        return len(self.samples)
        
    def __getitem__(self, idx):
        return self.samples[idx]

def train():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_dir = os.path.join(root_dir, "data", "processed")
    model_dir = os.path.join(root_dir, "models")
    os.makedirs(model_dir, exist_ok=True)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    # 1. Load Data
    print("Loading datasets...")
    train_dataset = ClauseDataset(os.path.join(data_dir, "train.jsonl"), is_train=True)
    val_dataset = ClauseDataset(os.path.join(data_dir, "val.jsonl"))
    test_dataset = ClauseDataset(os.path.join(data_dir, "test.jsonl"))
    
    # 2. Init Transformer
    print("Loading all-MiniLM-L6-v2...")
    tokenizer = AutoTokenizer.from_pretrained('sentence-transformers/all-MiniLM-L6-v2')
    transformer = AutoModel.from_pretrained('sentence-transformers/all-MiniLM-L6-v2').to(device)
    transformer.eval() # We will freeze it
    
    # Pre-extract embeddings for speed, otherwise training takes forever on CPU
    def pre_extract(dataset):
        extracted = []
        batch_size = 64
        with torch.no_grad():
            for i in range(0, len(dataset), batch_size):
                batch = [item for item in dataset.samples[i:i+batch_size]]
                texts = [item[0] for item in batch]
                labels = [item[1] for item in batch]
                
                inputs = tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=512).to(device)
                outputs = transformer(**inputs)
                
                # outputs.last_hidden_state: (batch, seq_len, 384)
                # We save it to CPU RAM to not blow up GPU/RAM
                hidden_states = outputs.last_hidden_state.cpu()
                
                for j in range(len(texts)):
                    # Get actual seq len (excluding padding if we want, but padding is fine for BiLSTM if we mask or let it process)
                    # Actually, PyTorch LSTM can just process the padded sequence
                    extracted.append((hidden_states[j], labels[j]))
                    
        return extracted
        
    print(f"Pre-extracting embeddings for {len(train_dataset)} training samples...")
    train_data = pre_extract(train_dataset)
    print(f"Pre-extracting embeddings for {len(val_dataset)} validation samples...")
    val_data = pre_extract(val_dataset)
    print(f"Pre-extracting embeddings for {len(test_dataset)} test samples...")
    test_data = pre_extract(test_dataset)
    
    # Free up memory
    del transformer
    gc.collect()
    torch.cuda.empty_cache()
    
    def collate_fn(batch):
        # batch is list of (tensor, label)
        sequences = [item[0] for item in batch]
        labels = [item[1] for item in batch]
        
        # sequences might have different lengths if extracted in different batches with different padding
        # But we already padded them per batch. Still, let's pad sequence to max in this batch to be safe.
        padded_seqs = nn.utils.rnn.pad_sequence(sequences, batch_first=True, padding_value=0.0)
        labels = torch.tensor(labels, dtype=torch.long)
        return padded_seqs, labels
        
    train_loader = DataLoader(train_data, batch_size=64, shuffle=True, collate_fn=collate_fn)
    val_loader = DataLoader(val_data, batch_size=128, collate_fn=collate_fn)
    test_loader = DataLoader(test_data, batch_size=128, collate_fn=collate_fn)
    
    # 3. Init Model
    embed_dim = 384
    hidden_dim = 128
    num_classes = 3
    
    model = BiLSTMRiskModel(embed_dim, hidden_dim, num_classes).to(device)
    
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    
    # 4. Train Loop
    epochs = 10 # Since it's faster with pre-extracted, let's do 10
    print(f"Starting training for {epochs} epochs...")
    
    best_val_loss = float('inf')
    
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for X, y in train_loader:
            X, y = X.to(device), y.to(device)
            
            optimizer.zero_grad()
            out = model(X)
            loss = criterion(out, y)
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            
        # Validation
        model.eval()
        val_loss = 0
        with torch.no_grad():
            for X, y in val_loader:
                X, y = X.to(device), y.to(device)
                out = model(X)
                val_loss += criterion(out, y).item()
                
        avg_train_loss = total_loss / len(train_loader)
        avg_val_loss = val_loss / len(val_loader)
        print(f"Epoch {epoch+1}/{epochs} - Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f}")
        
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            # Save best model
            torch.save(model.state_dict(), os.path.join(model_dir, "bilstm_risk.pt"))
            
    # 5. Evaluation on Test Set
    print("\nLoading best model for Test evaluation...")
    model.load_state_dict(torch.load(os.path.join(model_dir, "bilstm_risk.pt")))
    model.eval()
    
    all_preds = []
    all_labels = []
    
    with torch.no_grad():
        for X, y in test_loader:
            X, y = X.to(device), y.to(device)
            out = model(X)
            preds = torch.argmax(out, dim=1)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(y.cpu().numpy())
            
    acc = np.mean(np.array(all_preds) == np.array(all_labels))
    macro_f1 = f1_score(all_labels, all_preds, average='macro')
    cm = confusion_matrix(all_labels, all_preds)
    
    print("==========================================")
    print("             TEST SET RESULTS             ")
    print("==========================================")
    print(f"Accuracy: {acc:.4f}")
    print(f"Macro-F1: {macro_f1:.4f}")
    print("\nConfusion Matrix (Rows: Actual, Cols: Predicted)")
    print(f"          {'Low':>8} {'Medium':>8} {'High':>8}")
    for i, row in enumerate(cm):
        print(f"{_labels[i]:>8}: {row[0]:>8} {row[1]:>8} {row[2]:>8}")
        
if __name__ == "__main__":
    train()
