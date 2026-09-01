import React, { useState, useEffect } from 'react';
import { queryNamespace, purgeNamespace, purgeBatchNamespaces, fetchNamespaces, checkLink, enqueueLink } from './api';
import { Database, Trash2, Upload, FileText, CheckSquare, Square, CheckCircle, AlertCircle, MessageSquare, Bot, Search, Lock } from 'lucide-react';

function App() {
  
  // State variables for the Link Ingestion UI form
  const [linksText, setLinksText] = useState(() => {
    return localStorage.getItem('savedDriveLinks') || '';
  });

  useEffect(() => {
    localStorage.setItem('savedDriveLinks', linksText);
  }, [linksText]);
  const [linkHistory, setLinkHistory] = useState(() => {
    try {
      const saved = localStorage.getItem('linkHistory');
      return saved ? JSON.parse(saved) : [];
    } catch { return []; }
  });

  useEffect(() => {
    localStorage.setItem('linkHistory', JSON.stringify(linkHistory));
  }, [linkHistory]);
  const [access_token, setAccessToken] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);
  const [linkStatuses, setLinkStatuses] = useState({});
  
  // State variables for the Omni-Search RAG Chatbot UI
  const [queryForm, setQueryForm] = useState({ question: '' });
  const [botResponse, setBotResponse] = useState(null);
  const [isQuerying, setIsQuerying] = useState(false);
  
  // State variables for the Vector Database Manager UI
  const [namespaces, setNamespaces] = useState([]);
  const [selectedDbIds, setSelectedDbIds] = useState(new Set());

  const loadNamespaces = async () => {
    try {
      const res = await fetchNamespaces();
      setNamespaces(res.namespaces || []);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadNamespaces();
  }, []);

  // Utility to show temporary toast messages in the UI
  const showMessage = (text, type = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
  };

  /**
   * Pre-flights links to check if they are public or private, displaying colored feedback.
   */
  const handleCheckLinks = async (e) => {
    e.preventDefault();
    const links = linksText.split('\n').map(l => l.trim()).filter(l => l);
    if (!links.length) return showMessage('Please paste at least one link to check', 'error');

    setLoading(true);
    const statuses = { ...linkStatuses };
    
    for (const link of links) {
      try {
        const res = await checkLink(link, access_token);
        statuses[link] = res.info;
      } catch (err) {
        statuses[link] = { status: 'invalid', type: 'error', message: err.message };
      }
    }
    
    setLinkStatuses(statuses);
    setLoading(false);
  };

  const handleStartEngine = async () => {
    const validLinks = Object.entries(linkStatuses).filter(([link, info]) => info.status !== 'invalid' && (info.status !== 'locked' || access_token));
    if (validLinks.length === 0) return showMessage('No valid links to process.', 'error');
    
    setLoading(true);
    let successCount = 0;
    try {
      for (const [link, _] of validLinks) {
         await enqueueLink(link, access_token);
         successCount++;
      }
      
      setLinkHistory(prev => {
         const unique = new Set([...validLinks.map(v => v[0]), ...prev]);
         return Array.from(unique).slice(0, 20);
      });
      
      showMessage(`Successfully queued ${successCount} link(s) for background processing! Check Database Manager later.`);
      setLinksText('');
      setLinkStatuses({});
    } catch (err) {
      showMessage(`Failed to start engine: ${err.message}`, 'error');
    }
    setLoading(false);
  };

  const handlePurge = async (ns) => {
    if (!window.confirm(`Are you sure you want to delete the database: ${ns}?`)) return;
    try {
      const res = await purgeNamespace(ns);
      showMessage(res.message || 'Database purged successfully!');
      setSelectedDbIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(ns);
        return newSet;
      });
      loadNamespaces();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const handleToggleSelectDb = (id) => {
    setSelectedDbIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) newSet.delete(id);
      else newSet.add(id);
      return newSet;
    });
  };

  const handlePurgeMultiple = async () => {
    if (selectedDbIds.size === 0) return;
    if (!window.confirm(`Are you sure you want to delete ${selectedDbIds.size} databases?`)) return;
    
    setLoading(true);
    try {
      const namespacesToDelete = Array.from(selectedDbIds);
      await purgeBatchNamespaces(namespacesToDelete);
      
      showMessage(`Successfully deleted ${selectedDbIds.size} databases!`);
      setSelectedDbIds(new Set());
      loadNamespaces();
    } catch (err) {
      showMessage(`Error during multiple delete: ${err.message}`, 'error');
    }
    setLoading(false);
  };

  const handleQuery = async (e) => {
    e.preventDefault();
    if (!queryForm.question) return;
    
    setIsQuerying(true);
    setBotResponse(null);
    try {
      const selectedNamespaces = selectedDbIds.size > 0 ? Array.from(selectedDbIds) : null;
      const res = await queryNamespace(queryForm.question, selectedNamespaces, 4);
      setBotResponse(res.results);
    } catch (err) {
      showMessage(err.message, 'error');
    } finally {
      setIsQuerying(false);
    }
  };
  const handleSelectAllDbs = () => {
    if (namespaces.length === 0) return;
    if (selectedDbIds.size === namespaces.length) {
      setSelectedDbIds(new Set());
    } else {
      setSelectedDbIds(new Set(namespaces.map(ns => ns.id)));
    }
  };

  return (
    <div className="app-container" style={{ gridTemplateColumns: '1fr' }}>

      <div className="main-content">
        <div className="header">
          <h1>Vector Engine</h1>
          <p>Drop your Google Drive, Dropbox, or SharePoint links here, load them, and vectorize.</p>
        </div>

        {message && (
          <div className={`status-message ${message.type}`}>
            {message.type === 'success' ? <CheckCircle size={20} /> : <AlertCircle size={20} />}
            <span>{message.text}</span>
          </div>
        )}

        <div className="glass-panel">
          <form onSubmit={handleCheckLinks}>
            <div className="input-group">
              <label>Paste Links (Drive, Dropbox, SharePoint) (One per line)</label>
              <textarea 
                className="dropzone"
                required 
                value={linksText} 
                onChange={e => setLinksText(e.target.value)} 
                placeholder="Drop or paste links here...&#10;https://drive.google.com/file/d/.../view" 
              />
            </div>
            
            <div className="form-row">
              <div className="input-group flex-1">
                <label>Access Token (Optional for public links)</label>
                <input type="password" value={access_token} onChange={e => setAccessToken(e.target.value)} placeholder="Leave blank for public links" />
              </div>
              <button type="submit" className="btn load-btn" disabled={loading}>
                {loading ? <div className="spinner"></div> : <><Search size={18} /> Check Link</>}
              </button>
            </div>

            {linkHistory.length > 0 && (
              <div className="link-history" style={{ marginTop: '1rem' }}>
                <h3 style={{ fontSize: '0.85rem', color: '#94a3b8', marginBottom: '0.5rem' }}>Recent Links (Click to copy):</h3>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                  {linkHistory.map((hlink, idx) => (
                    <div 
                      key={idx} 
                      onClick={() => setLinksText(hlink)}
                      style={{ background: 'rgba(59, 130, 246, 0.2)', color: '#93c5fd', padding: '4px 10px', borderRadius: '12px', fontSize: '0.75rem', cursor: 'pointer', border: '1px solid rgba(59, 130, 246, 0.3)', maxWidth: '250px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', transition: 'all 0.2s' }}
                      title={hlink}
                    >
                      {hlink}
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {Object.keys(linkStatuses).length > 0 && (
              <div className="link-statuses" style={{ marginTop: '1rem', background: 'rgba(15, 23, 42, 0.5)', padding: '1rem', borderRadius: '8px' }}>
                <h3 style={{ fontSize: '0.85rem', color: '#94a3b8', marginBottom: '0.5rem' }}>Link Status:</h3>
                {Object.entries(linkStatuses).map(([link, info], idx) => (
                  <div key={idx} style={{ 
                    display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem',
                    color: info.status === 'valid' ? '#4ade80' : info.status === 'locked' ? '#fbbf24' : '#f87171' 
                  }}>
                    {info.status === 'valid' && <CheckCircle size={16} />}
                    {info.status === 'locked' && <Lock size={16} />}
                    {info.status === 'invalid' && <AlertCircle size={16} />}
                    <span style={{ fontSize: '0.8rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{link}</span>
                    <span style={{ fontSize: '0.75rem', opacity: 0.8 }}>- {info.message}</span>
                  </div>
                ))}
                
                {Object.values(linkStatuses).some(info => info.status !== 'invalid' && (info.status !== 'locked' || access_token)) && (
                  <div style={{ marginTop: '1rem', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '1rem', display: 'flex', justifyContent: 'flex-end' }}>
                     <button type="button" onClick={handleStartEngine} className="btn" style={{ background: '#10b981', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                       {loading ? <div className="spinner"></div> : <><Database size={18} /> Start Engine (Background)</>}
                     </button>
                  </div>
                )}
              </div>
            )}
          </form>
        </div>

        <div className="glass-panel bot-panel">
          <h2>Chat with Vector Data</h2>
          <form onSubmit={handleQuery} className="query-form">
            <div className="form-row">
              <div className="input-group flex-1" style={{ marginBottom: 0 }}>
                <label>Ask a Question</label>
                <input required value={queryForm.question} onChange={e => setQueryForm({...queryForm, question: e.target.value})} placeholder="Summarize the core concepts..." />
              </div>
              <button type="submit" className="btn query-btn" disabled={isQuerying}>
                {isQuerying ? <div className="spinner"></div> : <><MessageSquare size={18} /> Ask Bot</>}
              </button>
            </div>
          </form>

          {botResponse && (
            <div className="bot-response">
              <div className="bot-avatar"><Bot size={24} /></div>
              <div className="bot-message">{botResponse}</div>
            </div>
          )}
        </div>

        <div className="glass-panel db-panel" style={{ marginTop: '2rem', borderColor: 'rgba(139, 92, 246, 0.3)', background: 'rgba(30, 41, 59, 0.8)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)' }}>Database Manager</h2>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              {namespaces.length > 0 && (
                <button onClick={handleSelectAllDbs} className="btn" style={{ background: '#334155', padding: '0.5rem 1rem', minHeight: 'auto', fontSize: '0.875rem' }}>
                  <CheckSquare size={16} style={{ marginRight: '6px' }} /> {selectedDbIds.size === namespaces.length ? 'Deselect All' : 'Select All'}
                </button>
              )}
              {selectedDbIds.size > 0 && (
                <button onClick={handlePurgeMultiple} className="btn" style={{ background: '#ef4444', padding: '0.5rem 1rem', minHeight: 'auto', fontSize: '0.875rem' }} disabled={loading}>
                  {loading ? <div className="spinner" style={{width: 16, height: 16, borderWidth: 2}}></div> : <><Trash2 size={16} style={{ marginRight: '6px' }} /> Delete Selected ({selectedDbIds.size})</>}
                </button>
              )}
            </div>
          </div>
          <div className="db-list" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {namespaces.length === 0 ? (
              <p style={{ color: '#94a3b8' }}>No databases found.</p>
            ) : (
              namespaces.map(ns => (
                <div key={ns.id} className={`file-item ${selectedDbIds.has(ns.id) ? 'selected' : ''}`} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(15, 23, 42, 0.8)', padding: '1rem', borderRadius: '12px', border: selectedDbIds.has(ns.id) ? '1px solid #3b82f6' : '1px solid rgba(139, 92, 246, 0.4)', cursor: 'pointer' }} onClick={() => handleToggleSelectDb(ns.id)}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div className="file-checkbox">
                      {selectedDbIds.has(ns.id) ? <CheckSquare size={20} color="#3b82f6" /> : <Square size={20} color="#64748b" />}
                    </div>
                    <Database size={20} color="#c084fc" />
                    <span style={{ color: '#e2e8f0', fontFamily: 'monospace' }} title={ns.id}>{ns.name}</span>
                  </div>
                  <button onClick={(e) => { e.stopPropagation(); handlePurge(ns.id); }} className="btn" style={{ background: '#ef4444', padding: '0.5rem 1rem', minHeight: 'auto', fontSize: '0.875rem' }}>
                    <Trash2 size={16} style={{ marginRight: '6px' }} /> Delete
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
