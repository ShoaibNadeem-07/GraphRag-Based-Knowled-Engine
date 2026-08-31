import { useState, useEffect } from 'react';
import { fetchContracts, uploadContract } from './api';

export default function ContractPicker({ selectedContractId, onSelectContract }) {
  const [contracts, setContracts] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const loadContracts = async () => {
    try {
      const data = await fetchContracts();
      setContracts(data);
    } catch (err) {
      console.error(err);
      setError('Failed to load contracts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadContracts();
  }, []);

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploading(true);
    setError('');
    
    try {
      const res = await uploadContract(file);
      await loadContracts();
      onSelectContract(res.contract_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
    
    // Reset file input
    e.target.value = '';
  };

  const filteredContracts = contracts.filter(c => 
    c.id.toLowerCase().includes(search.toLowerCase()) || 
    (c.title && c.title.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div style={{ position: 'relative', height: '100%' }}>
      {uploading && (
        <div className="processing-overlay">
          <div className="spinner"></div>
          <h3 style={{ fontFamily: 'var(--font-display)', marginBottom: '0.5rem' }}>Processing Contract</h3>
          <p style={{ color: 'var(--color-text-secondary)', maxWidth: '250px' }}>
            Extracting clauses, running NER, and assessing risk. This may take a minute...
          </p>
        </div>
      )}

      <div className="upload-zone" onClick={() => document.getElementById('file-upload').click()}>
        <h4 style={{ color: 'var(--color-primary)' }}>+ Upload New PDF</h4>
        <p>Drag and drop or click to browse</p>
        <input 
          id="file-upload" 
          type="file" 
          accept="application/pdf" 
          style={{ display: 'none' }} 
          onChange={handleFileChange}
        />
      </div>

      {error && <p className="error-msg" style={{ marginBottom: '1rem' }}>{error}</p>}

      <input 
        type="text" 
        placeholder="Filter contracts..." 
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ 
          width: '100%', 
          padding: '0.75rem', 
          marginBottom: '1rem',
          borderRadius: '6px',
          border: '1px solid var(--color-border)',
          fontFamily: 'var(--font-body)'
        }}
      />

      {loading ? (
        <p style={{ color: 'var(--color-text-secondary)' }}>Loading...</p>
      ) : (
        <ul className="contract-list">
          <li 
            className={`contract-item ${selectedContractId === null ? 'active' : ''}`}
            onClick={() => onSelectContract(null)}
          >
            All Contracts (Global Context)
          </li>
          {filteredContracts.map(c => (
            <li 
              key={c.id} 
              className={`contract-item ${selectedContractId === c.id ? 'active' : ''}`}
              onClick={() => onSelectContract(c.id)}
              title={c.title || c.id}
            >
              {c.id.length > 35 ? c.id.substring(0, 35) + '...' : c.id}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
