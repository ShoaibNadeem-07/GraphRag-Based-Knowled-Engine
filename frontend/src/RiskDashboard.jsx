import { useState, useEffect } from 'react';
import { fetchRiskSummary } from './api';

export default function RiskDashboard({ contractId }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!contractId) return;
    
    let isMounted = true;
    setLoading(true);
    
    fetchRiskSummary(contractId)
      .then(data => {
        if (isMounted) {
          setSummary(data);
          setError('');
        }
      })
      .catch(err => {
        if (isMounted) setError(err.message);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });
      
    return () => { isMounted = false; };
  }, [contractId]);

  if (!contractId) {
    return <p style={{ color: 'var(--color-text-secondary)' }}>Select a contract to view its risk dashboard.</p>;
  }

  if (loading) {
    return <p style={{ color: 'var(--color-text-secondary)' }}>Loading risk data...</p>;
  }

  if (error) {
    return <p className="error-msg">Error: {error}</p>;
  }

  if (!summary) return null;

  return (
    <div>
      <div className="dashboard-header">
        <h2>Risk Assessment</h2>
        <p style={{ color: 'var(--color-text-secondary)' }}>Contract: {contractId}</p>
      </div>

      <div className="risk-summary-cards">
        <div className="stat-card high">
          <span className="label">High Risk</span>
          <span className="value">{summary.counts.High}</span>
        </div>
        <div className="stat-card medium">
          <span className="label">Medium Risk</span>
          <span className="value">{summary.counts.Medium}</span>
        </div>
        <div className="stat-card low">
          <span className="label">Low Risk</span>
          <span className="value">{summary.counts.Low}</span>
        </div>
      </div>

      <h3>High Risk Clauses ({summary.high_risk_clauses.length})</h3>
      <br />
      <div className="clause-list">
        {summary.high_risk_clauses.map(c => (
          <div key={c.id} className="clause-card high">
            <div className="clause-card-header">
              <span className="clause-id">{c.id}</span>
              <span className="risk-badge high">High Risk</span>
            </div>
            <p className="clause-text">{c.short_text}</p>
          </div>
        ))}
        {summary.high_risk_clauses.length === 0 && (
          <p style={{ color: 'var(--color-text-secondary)' }}>No high risk clauses found.</p>
        )}
      </div>
    </div>
  );
}
