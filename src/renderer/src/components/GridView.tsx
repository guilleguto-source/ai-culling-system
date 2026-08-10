import React, { useState, useMemo, useEffect, useCallback } from 'react';
import InspectorPanel from './inspector/InspectorPanel';
import PhotoThumbnail from './PhotoThumbnail';
import PhotoDetail from './PhotoDetail';
import { apiClient } from '../api/client';
import { useToast } from './Toast';

const FILTROS: [string, string, (r: any) => boolean][] = [
  ['todas', 'Todas', () => true],
  ['elegidas', 'Elegidas', r => r.label === 'selected' || r.label === 'highlighted'],
  ['recomendadas', 'Recomendadas', r => r.label === 'recommended'],
  ['repetidas', 'Repetidas', r => r.label === 'duplicates'],
  ['descartes', 'Descartes', r => r.label === 'blurry' || r.label === 'closed_eyes'],
  ['dudosas', 'Dudosas', r => (r.margin ?? 1) < 0.05],
];

interface GridViewProps {
  results: any[];
  selectedPaths?: Set<string>;
  onSelectPaths?: (paths: Set<string>) => void;
}

export default function GridView({ results, selectedPaths = new Set(), onSelectPaths }: GridViewProps) {
  const [filtro, setFiltro] = useState('todas');
  const [selectedPhoto, setSelectedPhoto] = useState<any>(null);
  const [modalPhoto, setModalPhoto] = useState<any>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [semanticPaths, setSemanticPaths] = useState<Set<string> | null>(null);
  const [lastSelectedIndex, setLastSelectedIndex] = useState<number | null>(null);
  const [density, setDensity] = useState<'compact' | 'normal' | 'large'>(() => {
    return (localStorage.getItem('guto_grid_density') as any) || 'normal';
  });

  const { showToast } = useToast();

  const handleDensityChange = (newDensity: 'compact' | 'normal' | 'large') => {
    setDensity(newDensity);
    localStorage.setItem('guto_grid_density', newDensity);
  };

  const handlePreferenceAction = useCallback(async (photo: any, isPick: boolean) => {
    if (!photo) return;
    const clusterPhotos = results.filter(r => r.cluster_id === photo.cluster_id);
    const rival = clusterPhotos.find(r => r.path !== photo.path);

    // Optimistically update label
    photo.label = isPick ? 'selected' : 'blurry';
    setSelectedPhoto({ ...photo });

    if (rival) {
      try {
        await apiClient.learnPreference(
          isPick ? photo.path : rival.path,
          isPick ? rival.path : photo.path
        );
        showToast(isPick ? 'Preferencia guardada (Pick)' : 'Preferencia guardada (Reject)', 'success');
      } catch (err) {
        console.error('Error learning preference:', err);
      }
    }
  }, [results, showToast]);

  const visibles = useMemo(() => {
    const f = FILTROS.find(([k]) => k === filtro)?.[2] || (() => true);
    let arr = results.filter(f);
    if (semanticPaths) {
      arr = arr.filter(r => semanticPaths.has(r.path));
    }
    return arr;
  }, [results, filtro, semanticPaths]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return;

      const key = e.key.toLowerCase();
      
      // Ctrl+A / Cmd+A or Ctrl+E to select all visibles
      if ((e.ctrlKey || e.metaKey) && (key === 'a' || key === 'e')) {
        e.preventDefault();
        if (onSelectPaths) {
          const allVisiblePaths = new Set(visibles.map(img => img.path));
          onSelectPaths(allVisiblePaths);
        }
        return;
      }

      if (['p', 'a'].includes(key)) {
        e.preventDefault();
        if (selectedPhoto) handlePreferenceAction(selectedPhoto, true);
      } else if (['x', 'd'].includes(key)) {
        e.preventDefault();
        if (selectedPhoto) handlePreferenceAction(selectedPhoto, false);
      } else if (key === 'enter' && selectedPhoto) {
        e.preventDefault();
        setModalPhoto(selectedPhoto);
      } else if (key === 'escape') {
        if (modalPhoto) setModalPhoto(null);
        else if (selectedPhoto) setSelectedPhoto(null);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedPhoto, modalPhoto, handlePreferenceAction, onSelectPaths, visibles]);

  // Semantic search debounced
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSemanticPaths(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const firstPath = results[0]?.path || '';
        const dir = firstPath.substring(0, Math.max(firstPath.lastIndexOf('\\'), firstPath.lastIndexOf('/')));
        const data = await apiClient.semanticSearch(searchQuery, dir);
        setSemanticPaths(new Set((data.results || []).map((x: any) => x.path)));
      } catch (e) {
        console.error('Semantic search error', e);
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [searchQuery, results]);

  const countByFilter = (fn: (r: any) => boolean) => results.filter(fn).length;

  const handlePhotoClick = (img: any, index: number, e: React.MouseEvent) => {
    setSelectedPhoto(img);

    if (!onSelectPaths) return;

    let newSelected = new Set(selectedPaths);

    if (e.shiftKey && lastSelectedIndex !== null) {
      // Rango de selección
      const start = Math.min(lastSelectedIndex, index);
      const end = Math.max(lastSelectedIndex, index);
      // Limpiamos o añadimos sobre lo actual? Generalmente añade.
      for (let i = start; i <= end; i++) {
        newSelected.add(visibles[i].path);
      }
    } else if (e.ctrlKey || e.metaKey) {
      // Toggle individual
      if (newSelected.has(img.path)) {
        newSelected.delete(img.path);
      } else {
        newSelected.add(img.path);
      }
    } else {
      // Selección única
      newSelected = new Set([img.path]);
    }

    onSelectPaths(newSelected);
    setLastSelectedIndex(index);
  };

  const selectAll = () => {
    if (onSelectPaths) {
      onSelectPaths(new Set(visibles.map(img => img.path)));
    }
  };

  if (!results || results.length === 0) return null;

  return (
    <div style={{ display: 'flex', width: '100%', height: '100%', overflow: 'hidden' }}>
      {/* Main Grid Column */}
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0 }}>
        {/* Toolbar Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 16px',
            backgroundColor: 'var(--color-surface)',
            borderBottom: '1px solid var(--border-subtle)',
            gap: 'var(--space-3)',
            flexWrap: 'wrap'
          }}
        >
          {/* Filters */}
          <div className="flex items-center gap-1">
            {FILTROS.map(([clave, texto, fn]) => {
              const count = countByFilter(fn);
              const isActive = filtro === clave;
              return (
                <button
                  key={clave}
                  className={`gf-btn gf-btn-sm ${isActive ? 'gf-btn-primary' : 'gf-btn-ghost'}`}
                  style={{
                    borderRadius: 'var(--radius-pill)',
                    padding: '4px 10px',
                    fontSize: 'var(--text-xs)'
                  }}
                  onClick={() => setFiltro(clave)}
                  disabled={count === 0 && clave !== 'todas'}
                >
                  <span>{texto}</span>
                  <span
                    className="text-mono"
                    style={{
                      opacity: isActive ? 1 : 0.6,
                      marginLeft: '2px',
                      fontSize: '10px'
                    }}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Right Controls: Density + Search */}
          <div className="flex items-center gap-3">
            <button 
              className="gf-btn gf-btn-sm gf-btn-ghost" 
              onClick={selectAll}
              style={{ fontSize: 'var(--text-xs)' }}
              title="Seleccionar Todas (Ctrl+A)"
            >
              Seleccionar Todas
            </button>

            {/* Density switch */}
            <div
              style={{
                display: 'flex',
                backgroundColor: 'var(--color-surface-elevated)',
                borderRadius: 'var(--radius-xs)',
                padding: '2px',
                border: '1px solid var(--border-subtle)'
              }}
            >
              {(['compact', 'normal', 'large'] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => handleDensityChange(d)}
                  style={{
                    padding: '3px 8px',
                    fontSize: '10px',
                    fontWeight: 'var(--fw-medium)',
                    borderRadius: 'var(--radius-xs)',
                    border: 'none',
                    cursor: 'pointer',
                    backgroundColor: density === d ? 'var(--color-surface-hover)' : 'transparent',
                    color: density === d ? 'var(--accent-primary)' : 'var(--text-tertiary)'
                  }}
                >
                  {d === 'compact' ? 'S' : d === 'normal' ? 'M' : 'L'}
                </button>
              ))}
            </div>

            {/* Quick Search */}
            <input
              type="text"
              placeholder="Buscar por contenido..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                padding: '5px 10px',
                borderRadius: 'var(--radius-xs)',
                border: '1px solid var(--border-default)',
                backgroundColor: 'var(--color-surface-elevated)',
                color: 'var(--text-primary)',
                fontSize: 'var(--text-xs)',
                outline: 'none',
                width: '180px'
              }}
            />
          </div>
        </div>

        {/* Thumbnails Flow Area */}
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexWrap: 'wrap',
            gap: density === 'compact' ? 'var(--space-2)' : 'var(--space-3)',
            padding: 'var(--space-4)',
            overflowY: 'auto',
            alignContent: 'flex-start',
            backgroundColor: 'var(--color-bg)'
          }}
        >
          {visibles.map((img, index) => {
            const isSelected = selectedPaths.has(img.path) || selectedPhoto?.path === img.path;
            
            return (
              <PhotoThumbnail
                key={img.path}
                photo={img}
                size={density}
                isActive={isSelected}
                onClick={(e) => handlePhotoClick(img, index, e)}
                onPick={(e) => {
                  e.stopPropagation();
                  handlePreferenceAction(img, true);
                }}
                onReject={(e) => {
                  e.stopPropagation();
                  handlePreferenceAction(img, false);
                }}
              />
            );
          })}
        </div>
      </div>

      {/* Inspector Panel Drawer */}
      {selectedPhoto && (
        <InspectorPanel
          foto={selectedPhoto}
          onClose={() => setSelectedPhoto(null)}
        />
      )}

      {/* Full Modal Viewer when pressing Enter */}
      {modalPhoto && (
        <PhotoDetail
          foto={modalPhoto}
          onClose={() => setModalPhoto(null)}
        />
      )}
    </div>
  );
}
