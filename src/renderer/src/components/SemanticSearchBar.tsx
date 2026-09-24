import React, { useState, useEffect } from 'react';
import { IconSearch } from './icons';
import { apiClient } from '../api/client';

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
        const data = await apiClient.semanticSearch(query.trim(), directory || '');
        const list = data.results || [];
        setResultsCount(list.length);
        if (onSearchResults) onSearchResults(list);
      } catch (e) {
        console.error('Error en búsqueda semántica:', e);
      } finally {
        setLoading(false);
      }
    }, 400);

    return () => clearTimeout(timer);
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
          left: '12px',
          marginTop: '4px',
          fontSize: '0.75rem',
          color: resultsCount > 0 ? 'var(--status-selected-text)' : 'var(--status-blurry-text)',
          fontWeight: 500
        }}>
          {resultsCount > 0
            ? `Se encontraron ${resultsCount} foto(s)`
            : 'No se encontraron fotos coincidentes'}
        </div>
      )}
    </div>
  );
}
