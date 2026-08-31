const API_BASE = 'http://localhost:8000';

export async function fetchContracts() {
  const res = await fetch(`${API_BASE}/contracts`);
  if (!res.ok) throw new Error('Failed to fetch contracts');
  return res.json();
}

export async function uploadContract(file) {
  const formData = new FormData();
  formData.append('file', file);
  
  const res = await fetch(`${API_BASE}/contracts/upload`, {
    method: 'POST',
    body: formData,
  });
  
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Upload failed');
  }
  
  return res.json();
}

export async function fetchRiskSummary(contractId) {
  const res = await fetch(`${API_BASE}/contracts/${contractId}/risk-summary`);
  if (!res.ok) throw new Error('Failed to fetch risk summary');
  return res.json();
}

export async function queryContract(question, contractId) {
  const payload = { question };
  if (contractId) payload.contract_id = contractId;
  
  const res = await fetch(`${API_BASE}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  
  if (!res.ok) throw new Error('Query failed');
  return res.json();
}
