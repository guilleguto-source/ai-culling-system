import React, { useState, useEffect } from 'react';
import { IconSearch } from './icons';

interface SemanticSearchBarProps {
  directory?: string;
  onSearchResults?: (results: any[]) => void;
  onClearSearch?: () => void;
}

export default function SemanticSearchBar({ directory, onSearchResults, onClearSearch }: SemanticSearchBarProps) {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [resultsCount, setResultsCount] = useState<number | null>(null);

  useEffect(() => {
    if (!query.trim()) {
      setResultsCount(null);
      if (onClearSearch) onClearSearch();
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const queryParams = new URLSearchParams({ q: query.trim() });
        if (directory) {
          queryParams.append('directory', directory);
        }
        const res = await fetch(`http://127.0.0.1:8000/search/semantic?${queryParams.toString()}`);
        if (res.ok) {
          const data = await res.json();
          const list = data.results || [];
          setResultsCount(list.length);
          if (onSearchResults) onSearchResults(list);
        }
      } catch (e) {
        console.error('Error en búsqueda semántica:', e);
      } finally {
        setLoading(false);
      }
    }, 400);

    return () => clearTimeout(timer);
    // directory en las deps: si cambia la carpeta con una búsqueda activa, el
    // closure viejo buscaría en la carpeta anterior.
  }, [query, directory]);

  const handleClear = () => {
    setQuery('');
    setResultsCount(null);
    if (onClearSearch) onClearSearch();
  };

  return (
    <div style={{ position: 'relative', width: '340px' }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        backgroundColor: 'var(--bg-tertiary)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        padding: '6px 12px',
        gap: '8px',
        boxShadow: 'var(--shadow-sm)',
        transition: 'all var(--transition-fast)'
      }}>
        <IconSearch size={16} style={{ color: 'var(--text-muted)' }} />
        <input
          type="text"
          placeholder="Busca por texto ('novia de blanco', 'anillos')..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            color: 'var(--text-primary)',
            outline: 'none',
            fontSize: '0.85rem'
          }}
        />
        {loading && (
          <span style={{ fontSize: '0.75rem', color: 'var(--accent-primary)', animation: 'spin 1s linear infinite' }}>
            ⏳
          </span>
        )}
        {query && !loading && (
          <button
            onClick={handleClear}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              fontSize: '0.9rem',
              padding: '0 4px'
            }}
          >
            ✕
          </button>
        )}
      </div>

      {resultsCount !== null && (
        <div style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          right: 0,
          marginTop: '4px',
          padding: '6px 12px',
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-strong)',
          borderRadius: 'var(--radius-sm)',
          fontSize: '0.75rem',
          color: 'var(--text-secondary)',
          zIndex: 20,
          boxShadow: 'var(--shadow-md)'
        }}>
          {resultsCount > 0 ? `✨ ${resultsCount} fotos coincidentes` : 'Sin coincidencias'}
        </div>
      )}
    </div>
  );
}
