import { useState, useRef } from 'react';
import { queryContract } from './api';

/** Parses answer text for [N] markers and renders them as clickable superscripts */
function renderAnswer(text, onCiteClick) {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (match) {
      const n = parseInt(match[1], 10);
      return (
        <sup
          key={i}
          onClick={() => onCiteClick(n)}
          title={`Go to citation ${n}`}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '1.1em',
            height: '1.1em',
            fontSize: '0.7em',
            fontWeight: '600',
            background: 'var(--color-primary)',
            color: 'white',
            borderRadius: '3px',
            cursor: 'pointer',
            marginLeft: '1px',
            verticalAlign: 'super',
            lineHeight: 1,
          }}
        >
          {n}
        </sup>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

export default function QueryScreen({ selectedContractId }) {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [expandedCitation, setExpandedCitation] = useState(null);
  const [highlightedCitation, setHighlightedCitation] = useState(null);

  const scrollToCitation = (msgIdx, citeN) => {
    // citeN is 1-indexed per the LLM numbering
    const id = `cite-${msgIdx}-${citeN - 1}`;
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      setHighlightedCitation(id);
      setTimeout(() => setHighlightedCitation(null), 1800);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!inputValue.trim()) return;

    const question = inputValue.trim();
    setInputValue('');
    
    // Add user message
    setMessages(prev => [...prev, { role: 'user', text: question }]);
    setLoading(true);

    try {
      const data = await queryContract(question, selectedContractId);
      setMessages(prev => [...prev, { 
        role: 'bot', 
        text: data.answer, 
        citations: data.cited_clauses || []
      }]);
    } catch (err) {
      setMessages(prev => [...prev, { 
        role: 'bot', 
        text: `Error: ${err.message}`, 
        isError: true 
      }]);
    } finally {
      setLoading(false);
    }
  };

  const isNoAnswer = (text) => text.toLowerCase().includes('cannot answer this based on the provided context');

  return (
    <div className="query-container">
      <div className="chat-history">
        {messages.map((msg, i) => (
          <div key={i} className={`chat-message ${msg.role}`}>
            {msg.role === 'user' ? (
              <p>{msg.text}</p>
            ) : (
              <div>
                <p className={`bot-answer ${isNoAnswer(msg.text) ? 'bot-no-answer' : ''}`}>
                  {renderAnswer(msg.text, (n) => scrollToCitation(i, n))}
                </p>
                
                {msg.citations && msg.citations.length > 0 && (
                  <div className="citation-list">
                    <h4>Citations</h4>
                    <div className="citation-grid">
                      {msg.citations.map((cite, j) => {
                        const cardId = `cite-${i}-${j}`;
                        const isHighlighted = highlightedCitation === cardId;
                        return (
                          <div
                            key={j}
                            id={cardId}
                            className={`clause-card ${cite.risk_level?.toLowerCase() || 'unclassified'}`}
                            style={isHighlighted ? { outline: '2px solid var(--color-primary)', transition: 'outline 0.3s' } : {}}
                          >
                            <div className="clause-card-header">
                              <span className="clause-id">[{j+1}] {cite.contract_id || cite.id}</span>
                              <span className={`risk-badge ${cite.risk_level?.toLowerCase() || 'unclassified'}`}>
                                {cite.risk_level || 'Unknown'} Risk
                              </span>
                            </div>
                            <p className="clause-text">
                              {expandedCitation === `${i}-${j}` ? cite.text : (cite.text.substring(0, 150) + '...')}
                            </p>
                            <button 
                              className="tab-btn" 
                              style={{ padding: '0.5rem 0', marginTop: '0.5rem', fontSize: '0.8rem' }}
                              onClick={() => setExpandedCitation(expandedCitation === `${i}-${j}` ? null : `${i}-${j}`)}
                            >
                              {expandedCitation === `${i}-${j}` ? 'Show Less' : 'Show Full Clause'}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="chat-message bot">
            <div className="spinner" style={{ width: '20px', height: '20px', margin: 0, borderWidth: '2px' }} />
          </div>
        )}
      </div>

      <form className="input-area" onSubmit={handleSubmit}>
        <input 
          type="text" 
          placeholder={selectedContractId ? `Ask about ${selectedContractId}...` : "Ask a general question across all contracts..."}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !inputValue.trim()}>Send</button>
      </form>
    </div>
  );
}
