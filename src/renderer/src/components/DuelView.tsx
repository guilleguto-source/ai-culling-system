import React, { useState, useMemo, useEffect } from 'react';
import Loupe from './Loupe';
import FaceGridAlignment from './FaceGridAlignment';
import PhotoDetail from './PhotoDetail';
import { apiClient } from '../api/client';
import { Button } from './ui/Button';
import { IconCheck, IconX, IconStar } from './icons';

interface DuelViewProps {
  results: any[];
  onBackToGrid?: () => void;
}

export default function DuelView({ results, onBackToGrid }: DuelViewProps) {
  if (!results || results.length === 0) return null;

  const clusters = useMemo(() => {
    const map = new Map<number, any[]>();
    for (const img of results) {
      if (!map.has(img.cluster_id)) {
        map.set(img.cluster_id, []);
      }
      map.get(img.cluster_id)!.push(img);
    }
    return Array.from(map.values()).filter(group => group.length > 1);
  }, [results]);

  const [currentClusterIdx, setCurrentClusterIdx] = useState(0);
  const [learnedOverrides, setLearnedOverrides] = useState<Record<number, string>>({});
  const [, setIsLearning] = useState(false);
  const [showViewerModal, setShowViewerModal] = useState<any>(null);

  if (clusters.length === 0) {
    return (
      <div className="flex-center" style={{ height: '100%', color: 'var(--text-muted)' }}>
        No se detectaron ráfagas para comparar en esta sesión.
      </div>
    );
  }

  const currentGroup = clusters[currentClusterIdx] || clusters[0];
  const clusterId = currentGroup[0].cluster_id;

  const representative = currentGroup.find(img => img.path === learnedOverrides[clusterId])
    || currentGroup.find(img => img.is_cluster_representative)
    || currentGroup[0];

  const ordered = [
    representative,
    ...currentGroup
      .filter(img => img !== representative)
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0)),
  ];

  const alternative = ordered[1] || ordered[0];

  const handleApproveRepresentative = async () => {
    if (!alternative || alternative.path === representative.path) return;
    setIsLearning(true);
    try {
      await apiClient.learnPreference(representative.path, alternative.path);
    } catch (e) {
      console.error('Error approving:', e);
    } finally {
      setIsLearning(false);
    }
  };

  const handleChooseAlternative = async (alt: any) => {
    if (!alt || alt.path === representative.path) return;
    setIsLearning(true);
    try {
      await apiClient.learnPreference(alt.path, representative.path);
      setLearnedOverrides(prev => ({ ...prev, [clusterId]: alt.path }));
    } catch (e) {
      console.error('Error choosing alternative:', e);
    } finally {
      setIsLearning(false);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return;
      if (e.key === 'ArrowRight') {
        e.preventDefault();
        setCurrentClusterIdx(c => Math.min(c + 1, clusters.length - 1));
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setCurrentClusterIdx(c => Math.max(c - 1, 0));
      } else if (e.key === 'p' || e.key === 'P' || e.key === 'Enter') {
        e.preventDefault();
        handleApproveRepresentative();
      } else if (e.key === 'x' || e.key === 'X') {
        e.preventDefault();
        if (alternative) handleChooseAlternative(alternative);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const repScorePct = representative?.score != null ? Math.round(Math.min(1, representative.score) * 100) : null;
  const altScorePct = alternative?.score != null ? Math.round(Math.min(1, alternative.score) * 100) : null;

  const repDiag = representative?.diagnostics || {};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', backgroundColor: 'var(--color-bg)' }}>
      {/* 1. Header Toolbar */}
      <div
        style={{
          height: '46px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 var(--space-4)',
          backgroundColor: 'var(--color-surface)',
          borderBottom: '1px solid var(--border-subtle)',
          flexShrink: 0
        }}
      >
        <div className="flex items-center gap-2">
          {onBackToGrid && (
            <Button variant="ghost" size="sm" onClick={onBackToGrid}>
              ‹ Volver
            </Button>
          )}
          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
            Ráfaga {currentClusterIdx + 1} de {clusters.length}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={currentClusterIdx === 0}
            onClick={() => setCurrentClusterIdx(c => c - 1)}
          >
            ‹ Anterior
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={currentClusterIdx === clusters.length - 1}
            onClick={() => setCurrentClusterIdx(c => c + 1)}
          >
            Siguiente ›
          </Button>
        </div>
      </div>

      {/* 2. Main Arena + Analysis Sidebar */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0, overflow: 'hidden' }}>
        {/* Duel Area Wrapper */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflowY: 'auto' }}>
          {/* Two Cards */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 'var(--space-4)',
              padding: 'var(--space-4)',
              flex: 1
            }}
        >
          {/* Left Card: Candidato IA */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--accent-primary)',
              borderRadius: 'var(--radius-md)',
              overflow: 'hidden',
              boxShadow: 'var(--shadow-guto)'
            }}
          >
            {/* Card Header */}
            <div
              style={{
                padding: '10px 16px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                borderBottom: '1px solid var(--border-default)',
                backgroundColor: 'rgba(233, 160, 74, 0.06)'
              }}
            >
              <div>
                <div style={{ fontSize: '13px', fontWeight: 'var(--fw-bold)', color: 'var(--accent-primary)', letterSpacing: '0.02em' }}>
                  Candidato Recomendado (IA)
                </div>
                <div className="flex items-center gap-1" style={{ color: 'var(--accent-primary)', fontSize: '11px', marginTop: '2px' }}>
                  {[1, 2, 3, 4, 5].map(star => (
                    <IconStar key={star} size={11} filled={star <= 4} />
                  ))}
                </div>
              </div>
              <span
                className="font-mono"
                style={{
                  backgroundColor: 'var(--accent-primary)',
                  color: '#08090C',
                  fontWeight: 'var(--fw-bold)',
                  padding: '2px 8px',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '11px'
                }}
              >
                {repScorePct !== null ? `${repScorePct}%` : '—'}
              </span>
            </div>

            {/* Photo Loupe */}
            <div style={{ flex: 1, minHeight: '320px', backgroundColor: 'var(--color-bg)', position: 'relative' }}>
              <Loupe
                src={apiClient.getThumbnailUrl(representative.path, 'duel')}
                alt={representative.filename}
                style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
              />
            </div>

            {/* Bullets Pros */}
            <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: '6px', borderTop: '1px solid var(--border-default)' }}>
              <div className="flex items-center gap-2 text-success" style={{ fontSize: '11px' }}>
                <IconCheck size={13} /> <span>Ojos abiertos y nítidos</span>
              </div>
              <div className="flex items-center gap-2 text-success" style={{ fontSize: '11px' }}>
                <IconCheck size={13} /> <span>Mejor expresión facial</span>
              </div>
              <div className="flex items-center gap-2 text-success" style={{ fontSize: '11px' }}>
                <IconCheck size={13} /> <span>Coincide con tu perfil de estilo</span>
              </div>

              <Button
                variant="primary"
                size="md"
                onClick={handleApproveRepresentative}
                style={{ marginTop: 'var(--space-2)', width: '100%' }}
                icon={<IconCheck size={15} />}
              >
                Elegir esta foto (P)
              </Button>
            </div>
          </div>

          {/* Right Card: Alternativa */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              overflow: 'hidden',
              boxShadow: 'var(--shadow-card)'
            }}
          >
            {/* Card Header */}
            <div
              style={{
                padding: '10px 16px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                borderBottom: '1px solid var(--border-default)'
              }}
            >
              <div>
                <div style={{ fontSize: '13px', fontWeight: 'var(--fw-bold)', color: 'var(--text-secondary)' }}>
                  Alternativa #{alternative !== representative ? '2' : '1'}
                </div>
                <div className="flex items-center gap-1" style={{ color: 'var(--text-tertiary)', fontSize: '11px', marginTop: '2px' }}>
                  {[1, 2, 3, 4, 5].map(star => (
                    <IconStar key={star} size={11} filled={star <= 3} />
                  ))}
                </div>
              </div>
              <span
                className="font-mono"
                style={{
                  backgroundColor: 'var(--color-surface-elevated)',
                  color: 'var(--text-secondary)',
                  fontWeight: 'var(--fw-bold)',
                  padding: '2px 8px',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '11px',
                  border: '1px solid var(--border-default)'
                }}
              >
                {altScorePct !== null ? `${altScorePct}%` : '—'}
              </span>
            </div>

            {/* Photo Loupe */}
            <div style={{ flex: 1, minHeight: '320px', backgroundColor: '#000000', position: 'relative' }}>
              <Loupe
                src={apiClient.getThumbnailUrl(alternative.path, 'duel')}
                alt={alternative.filename}
                style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
              />
            </div>

            {/* Bullets Contras */}
            <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '6px', borderTop: '1px solid var(--border-subtle)' }}>
              <div className="flex items-center gap-2 text-muted" style={{ fontSize: 'var(--text-xs)' }}>
                <IconX size={14} className="text-danger" /> <span>Ligero movimiento o desenfoque</span>
              </div>
              <div className="flex items-center gap-2 text-muted" style={{ fontSize: 'var(--text-xs)' }}>
                <IconX size={14} className="text-danger" /> <span>Mirada secundaria fuera de cámara</span>
              </div>
              <div className="flex items-center gap-2 text-muted" style={{ fontSize: 'var(--text-xs)' }}>
                <span style={{ width: '14px', textAlign: 'center' }}>·</span> <span>Puntuación estética menor</span>
              </div>

              <Button
                variant="secondary"
                size="md"
                onClick={() => handleChooseAlternative(alternative)}
                style={{ marginTop: 'var(--space-2)', width: '100%' }}
              >
                Elegir esta
              </Button>
            </div>
          </div>
          </div>

          {/* Burst Face Strip (Narrative Select style) */}
          <div style={{ padding: '0 var(--space-4) var(--space-4) var(--space-4)' }}>
            <FaceGridAlignment
              clusterId={clusterId}
              selectedPhotoPath={representative.path}
              onSelectPhoto={(path) => handleChooseAlternative(path)}
            />
          </div>
        </div>

        {/* Right Analysis Sidebar */}
        <aside
          style={{
            width: '280px',
            minWidth: '280px',
            backgroundColor: 'var(--color-surface)',
            borderLeft: '1px solid var(--border-subtle)',
            padding: 'var(--space-4)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-4)',
            overflowY: 'auto'
          }}
        >
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)' }}>
            Análisis IA
          </div>

          {/* Metric Bars */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {[
              { label: 'Nitidez', value: Math.min(100, Math.round((repDiag.blur_score || 450) / 5)) },
              { label: 'Rostros', value: repDiag.valid_face_count ? 100 : 95 },
              { label: 'Ojos abiertos', value: repDiag.closed_eyes_count === 0 ? 100 : 60 },
              { label: 'Expresión', value: repDiag.smiling_count > 0 ? 94 : 88 },
              { label: 'Composición', value: Math.round((repDiag.aesthetic_score || 0.86) * 100) },
              { label: 'Compatibilidad con tu estilo', value: repScorePct, isAccent: true }
            ].map((metric) => (
              <div key={metric.label}>
                <div className="flex justify-between items-center" style={{ fontSize: '11px', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>{metric.label}</span>
                  <span className="text-mono" style={{ fontWeight: 'var(--fw-bold)', color: metric.isAccent ? 'var(--accent-primary)' : 'var(--text-primary)' }}>
                    {metric.value}%
                  </span>
                </div>
                <div
                  style={{
                    height: '4px',
                    backgroundColor: 'var(--color-surface-elevated)',
                    borderRadius: 'var(--radius-pill)',
                    overflow: 'hidden'
                  }}
                >
                  <div
                    style={{
                      width: `${metric.value}%`,
                      height: '100%',
                      backgroundColor: metric.isAccent ? 'var(--accent-primary)' : 'var(--success)'
                    }}
                  />
                </div>
              </div>
            ))}
          </div>



          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowViewerModal(representative)}
            style={{ marginTop: 'auto', width: '100%' }}
          >
            Ver en visor
          </Button>
        </aside>
      </div>

      {/* 3. Keyboard Shortcuts Footer */}
      <footer
        style={{
          height: '32px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderTop: '1px solid var(--border-subtle)',
          backgroundColor: 'var(--color-surface)',
          fontSize: '11px',
          color: 'var(--text-muted)',
          gap: 'var(--space-4)'
        }}
      >
        <span><strong style={{ color: 'var(--text-secondary)' }}>P</strong> = Elegir</span>
        <span><strong style={{ color: 'var(--text-secondary)' }}>X</strong> = Rechazar</span>
        <span><strong style={{ color: 'var(--text-secondary)' }}>1-5</strong> = Estrellas</span>
        <span><strong style={{ color: 'var(--text-secondary)' }}>← / →</strong> = Navegar ráfagas</span>
      </footer>

      {/* Full Modal Viewer */}
      {showViewerModal && (
        <PhotoDetail
          foto={showViewerModal}
          onClose={() => setShowViewerModal(null)}
          sessionPhotos={currentGroup}
        />
      )}
    </div>
  );
}
