import { useState } from 'react';
import ContractPicker from './ContractPicker';
import QueryScreen from './QueryScreen';
import RiskDashboard from './RiskDashboard';

export default function App() {
  const [selectedContractId, setSelectedContractId] = useState(null);
  const [activeTab, setActiveTab] = useState('query'); // 'query' or 'dashboard'

  return (
    <div className="app-container">
      {/* Sidebar */}
      <div className="sidebar">
        <div className="sidebar-header">
          <h1 style={{ fontFamily: 'var(--font-display)', color: 'var(--color-primary)' }}>
            GraphRAG Legal
          </h1>
          <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.875rem' }}>
            Contract Intelligence
          </p>
        </div>
        <div className="sidebar-content">
          <ContractPicker 
            selectedContractId={selectedContractId} 
            onSelectContract={id => {
              setSelectedContractId(id);
              if (id) setActiveTab('dashboard'); // Auto-switch to dashboard on new selection
            }} 
          />
        </div>
      </div>

      {/* Main Content Area */}
      <div className="main-content">
        <div className="topbar">
          <div className="view-tabs">
            <button 
              className={`tab-btn ${activeTab === 'query' ? 'active' : ''}`}
              onClick={() => setActiveTab('query')}
            >
              Query Agent
            </button>
            <button 
              className={`tab-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
              onClick={() => setActiveTab('dashboard')}
              disabled={!selectedContractId}
            >
              Risk Dashboard
            </button>
          </div>
          
          <div style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
            {selectedContractId ? `Scoping to: ${selectedContractId.length > 30 ? selectedContractId.substring(0, 30) + '...' : selectedContractId}` : 'Global Context (All Contracts)'}
          </div>
        </div>

        <div className="content-pane">
          {activeTab === 'query' && (
            <QueryScreen selectedContractId={selectedContractId} />
          )}
          {activeTab === 'dashboard' && (
            <RiskDashboard contractId={selectedContractId} />
          )}
        </div>
      </div>
    </div>
  );
}
