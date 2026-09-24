import React, { useState, useMemo, useEffect, useCallback, forwardRef } from 'react';
import { VirtuosoGrid } from 'react-virtuoso';
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
  storylinePaths?: Set<string> | null;
}

export default function GridView({ results, selectedPaths = new Set(), onSelectPaths, storylinePaths = null }: GridViewProps) {
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
    if (storylinePaths) {
      arr = arr.filter(r => storylinePaths.has(r.path));
    }

    const finalArr: any[] = [];
    let currentChapter = null;

    for (const r of arr) {
      const chap = r.chapter_id || 'capitulo_0';
      if (chap !== currentChapter) {
        const title = chap === 'capitulo_broll' ? 'Detalles & B-Roll' : `Capítulo ${chap.replace('capitulo_', '')}`;
        finalArr.push({
          is_header: true,
          title,
          path: `header_${chap}`, // Clave única
        });
        currentChapter = chap;
      }
      finalArr.push(r);
    }
    return finalArr;
  }, [results, filtro, semanticPaths, storylinePaths]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return;

      const key = e.key.toLowerCase();
      
      if ((e.ctrlKey || e.metaKey) && (key === 'a' || key === 'e')) {
        e.preventDefault();
        if (onSelectPaths) {
          const allVisiblePaths = new Set(visibles.filter(img => !img.is_header).map(img => img.path));
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
        if (!visibles[i].is_header) {
          newSelected.add(visibles[i].path);
        }
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
      onSelectPaths(new Set(visibles.filter(img => !img.is_header).map(img => img.path)));
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
            padding: '16px 24px',
            backgroundColor: 'var(--color-bg)',
            borderBottom: '1px solid var(--border-default)',
            gap: 'var(--space-3)',
            flexWrap: 'wrap'
          }}
        >
          <div className="flex items-center gap-4" style={{ paddingLeft: '8px' }}>
            {FILTROS.map(([clave, texto, fn]) => {
              const count = countByFilter(fn);
              const isActive = filtro === clave;
              return (
                <button
                  key={clave}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: isActive ? 'var(--text-primary)' : 'var(--text-tertiary)',
                    fontWeight: isActive ? 600 : 400,
                    cursor: count > 0 || clave === 'todas' ? 'pointer' : 'default',
                    opacity: (count === 0 && clave !== 'todas') ? 0.4 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '4px 0',
                    fontSize: 'var(--text-sm)',
                    letterSpacing: '0.02em',
                  }}
                  onClick={() => setFiltro(clave)}
                  disabled={count === 0 && clave !== 'todas'}
                >
                  <span style={{ textTransform: 'uppercase' }}>{texto}</span>
                  <span
                    className="font-mono"
                    style={{
                      opacity: isActive ? 1 : 0.6,
                      fontSize: '11px',
                      color: isActive ? 'var(--accent-primary)' : 'inherit',
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
        <div style={{ flex: 1, backgroundColor: 'var(--color-bg)' }}>
          <VirtuosoGrid
            totalCount={visibles.length}
            overscan={200}
            components={{
              List: forwardRef(({ style, children, ...props }, ref) => {
                const minW = density === 'compact' ? '120px' : density === 'normal' ? '180px' : '280px';
                const gap = density === 'compact' ? 'var(--space-2)' : 'var(--space-3)';
                return (
                  <div
                    ref={ref}
                    {...props}
                    style={{
                      ...style,
                      display: 'grid',
                      gridTemplateColumns: `repeat(auto-fill, minmax(${minW}, 1fr))`,
                      gap: gap,
                      padding: 'var(--space-4)',
                    }}
                  >
                    {children}
                  </div>
                );
              }),
              Item: ({ children, ...props }) => {
                const index = props['data-index'];
                const img = visibles[index];
                const isHeader = img?.is_header;
                return (
                  <div {...props} style={{ ...(props.style || {}), gridColumn: isHeader ? '1 / -1' : undefined }}>
                    {children}
                  </div>
                );
              },
            }}
            itemContent={index => {
              const img = visibles[index];

              if (img.is_header) {
                return (
                  <div style={{
                    gridColumn: '1 / -1',
                    padding: '16px 0 8px 0',
                    borderBottom: '1px solid var(--border-default)',
                    marginBottom: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px'
                  }}>
                    <span style={{ fontSize: '18px', fontWeight: 'bold', color: 'var(--text-primary)' }}>
                      {img.title}
                    </span>
                  </div>
                );
              }

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
            }}
          />
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
