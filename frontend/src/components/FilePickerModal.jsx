import React, { useState, useEffect } from 'react';
import { X, Folder, File, ChevronRight, CheckSquare, Square, CheckCircle, Database } from 'lucide-react';

export default function FilePickerModal({ isOpen, onClose, provider, accessToken, onIngest, onDisconnect }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [breadcrumbs, setBreadcrumbs] = useState([{ id: 'root', name: 'Home' }]);

  const currentFolderId = breadcrumbs[breadcrumbs.length - 1].id;

  useEffect(() => {
    if (isOpen && provider && accessToken) {
      fetchItems('root');
    }
  }, [isOpen, provider, accessToken]);

  const fetchItems = async (folderId) => {
    setLoading(true);
    try {
      const url = folderId === 'root' 
        ? `http://localhost:8000/browse/${provider}/root`
        : `http://localhost:8000/browse/${provider}/folder/${folderId}`;
        
      const res = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${accessToken}`
        }
      });
      const data = await res.json();
      if (data.status === 'success') {
        setItems(data.items);
      }
    } catch (e) {
      console.error("Failed to fetch items:", e);
    } finally {
      setLoading(false);
    }
  };

  const navigateTo = (folder) => {
    setBreadcrumbs([...breadcrumbs, { id: folder.id, name: folder.name }]);
    fetchItems(folder.id);
  };

  const navigateBreadcrumb = (index) => {
    const newCrumbs = breadcrumbs.slice(0, index + 1);
    setBreadcrumbs(newCrumbs);
    fetchItems(newCrumbs[newCrumbs.length - 1].id);
  };

  const toggleSelect = (id) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  const handleSelectAll = () => {
    if (selectedIds.size === items.length && items.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(items.map(i => i.id)));
    }
  };

  const handleIngest = () => {
    const selectedItems = Array.from(selectedIds).map(id => {
      const item = items.find(i => i.id === id);
      return {
        id: id,
        type: item && item.mimeType === 'application/vnd.google-apps.folder' ? 'folder' : 'file'
      };
    });
    onIngest(selectedItems);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(2, 6, 23, 0.85)',
      backdropFilter: 'blur(8px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000, padding: '2rem'
    }}>
      <div className="glass-panel" style={{
        width: '100%', maxWidth: '900px', height: '85vh',
        display: 'flex', flexDirection: 'column', padding: 0,
        overflow: 'hidden', border: '1px solid rgba(139, 92, 246, 0.4)',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)'
      }}>
        
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '1.25rem 1.5rem', borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          background: 'rgba(15, 23, 42, 0.6)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Database color="#a78bfa" size={24} />
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#f8fafc', textTransform: 'capitalize', margin: 0 }}>
              Browse {provider}
            </h2>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <button onClick={onDisconnect} style={{
              background: 'transparent', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#ef4444',
              cursor: 'pointer', padding: '0.35rem 0.75rem', borderRadius: '6px', fontSize: '0.85rem',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.2s'
            }} onMouseOver={e => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)'} onMouseOut={e => e.currentTarget.style.background = 'transparent'}>
              Disconnect
            </button>
            <button onClick={onClose} style={{
              background: 'transparent', border: 'none', color: '#94a3b8',
              cursor: 'pointer', padding: '0.5rem', borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.2s'
            }} onMouseOver={e => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'} onMouseOut={e => e.currentTarget.style.background = 'transparent'}>
              <X size={20} />
            </button>
          </div>
        </div>
        
        {/* Breadcrumbs */}
        <div style={{
          display: 'flex', alignItems: 'center', padding: '0.75rem 1.5rem',
          background: 'rgba(30, 41, 59, 0.4)', borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
          overflowX: 'auto', whiteSpace: 'nowrap', fontSize: '0.875rem'
        }}>
          {breadcrumbs.map((crumb, idx) => (
            <React.Fragment key={crumb.id}>
              <button 
                onClick={() => navigateBreadcrumb(idx)}
                style={{
                  background: 'transparent', border: 'none', 
                  color: idx === breadcrumbs.length - 1 ? '#a78bfa' : '#94a3b8',
                  fontWeight: idx === breadcrumbs.length - 1 ? 600 : 400,
                  cursor: 'pointer', padding: '0.25rem 0.5rem', borderRadius: '4px',
                  transition: 'color 0.2s'
                }}
                onMouseOver={e => e.currentTarget.style.color = '#c4b5fd'} 
                onMouseOut={e => e.currentTarget.style.color = idx === breadcrumbs.length - 1 ? '#a78bfa' : '#94a3b8'}
              >
                {crumb.name}
              </button>
              {idx < breadcrumbs.length - 1 && <ChevronRight size={14} color="#475569" style={{ margin: '0 4px' }} />}
            </React.Fragment>
          ))}
        </div>

        {/* File List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '1rem 1.5rem', background: 'rgba(2, 6, 23, 0.3)' }}>
          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
              <div className="spinner" style={{ width: '40px', height: '40px', borderWidth: '3px' }}></div>
            </div>
          ) : items.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#64748b', marginTop: '3rem', fontSize: '1rem' }}>
              <Folder size={48} color="#334155" style={{ margin: '0 auto 1rem auto' }} />
              This folder is empty.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div style={{ display: 'flex', padding: '0 1rem 0.5rem 1rem', borderBottom: '1px solid rgba(255,255,255,0.05)', marginBottom: '0.5rem' }}>
                <button onClick={handleSelectAll} style={{ background: 'transparent', border: 'none', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.85rem' }}>
                  {selectedIds.size === items.length && items.length > 0 ? <CheckSquare size={16} /> : <Square size={16} />}
                  Select All
                </button>
              </div>
              {items.map(item => {
                const isFolder = item.mimeType === 'application/vnd.google-apps.folder';
                const isSelected = selectedIds.has(item.id);
                return (
                  <div key={item.id} style={{
                    display: 'flex', alignItems: 'center', padding: '0.75rem 1rem',
                    background: isSelected ? 'rgba(139, 92, 246, 0.15)' : 'rgba(15, 23, 42, 0.4)',
                    border: isSelected ? '1px solid rgba(139, 92, 246, 0.5)' : '1px solid transparent',
                    borderRadius: '8px', transition: 'all 0.2s', cursor: 'pointer'
                  }} 
                  onClick={() => isFolder ? navigateTo(item) : toggleSelect(item.id)}
                  onMouseOver={e => { if(!isSelected) e.currentTarget.style.background = 'rgba(30, 41, 59, 0.8)'; }}
                  onMouseOut={e => { if(!isSelected) e.currentTarget.style.background = 'rgba(15, 23, 42, 0.4)'; }}
                  >
                    <div style={{ marginRight: '1rem', display: 'flex', alignItems: 'center' }} onClick={(e) => { e.stopPropagation(); toggleSelect(item.id); }}>
                      {isSelected ? <CheckSquare size={20} color="#a78bfa" /> : <Square size={20} color="#475569" />}
                    </div>
                    
                    <div style={{ display: 'flex', alignItems: 'center', flex: 1, gap: '0.75rem' }}>
                      {isFolder ? <Folder size={20} color="#60a5fa" /> : <File size={20} color="#94a3b8" />}
                      <span style={{ 
                        color: isFolder ? '#f8fafc' : '#cbd5e1', 
                        fontWeight: isFolder ? 500 : 400,
                        fontSize: '0.95rem'
                      }}>
                        {item.name}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        
        {/* Footer */}
        <div style={{
          padding: '1.25rem 1.5rem', borderTop: '1px solid rgba(255, 255, 255, 0.1)',
          background: 'rgba(15, 23, 42, 0.6)', display: 'flex', justifyContent: 'space-between', alignItems: 'center'
        }}>
          <span style={{ color: '#94a3b8', fontSize: '0.9rem' }}>
            <strong style={{ color: '#f8fafc' }}>{selectedIds.size}</strong> items selected
          </span>
          <div style={{ display: 'flex', gap: '1rem' }}>
            <button onClick={onClose} className="btn" style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.2)' }}>
              Cancel
            </button>
            <button 
              onClick={handleIngest}
              disabled={selectedIds.size === 0}
              className="btn"
              style={{ 
                background: selectedIds.size > 0 ? 'linear-gradient(135deg, #8b5cf6, #3b82f6)' : '#334155', 
                opacity: selectedIds.size === 0 ? 0.5 : 1,
                cursor: selectedIds.size === 0 ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', gap: '0.5rem'
              }}
            >
              <CheckCircle size={18} /> Ingest Selected
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
