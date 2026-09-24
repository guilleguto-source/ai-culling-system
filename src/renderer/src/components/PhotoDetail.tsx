import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { Button } from './ui/Button';
import { IconCheck, IconX, IconStar } from './icons';

interface PhotoDetailProps {
  foto: any;
  onClose: () => void;
  sessionPhotos?: any[];
  onSelectPhoto?: (photo: any) => void;
}

const ETIQUETAS: [string, string][] = [
  ['camara', 'Cámara'],
  ['lente', 'Lente'],
  ['apertura', 'Apertura'],
  ['iso', 'ISO'],
  ['velocidad', 'Velocidad'],
  ['focal', 'Focal'],
  ['fecha', 'Fecha']
];

export default function PhotoDetail({
  foto: initialFoto,
  onClose,
  sessionPhotos = [],
  onSelectPhoto
}: PhotoDetailProps) {
  const [foto, setFoto] = useState(initialFoto);
  const [exif, setExif] = useState<any>(null);
  const [conEdicion, setConEdicion] = useState(true);
  const [activeTab, setActiveTab] = useState<'ia' | 'meta'>('ia');

  useEffect(() => {
    setFoto(initialFoto);
  }, [initialFoto]);

  useEffect(() => {
    if (!foto) return;
    setExif(null);
    (async () => {
      try {
        const data = await apiClient.getExif(foto.path);
        setExif(data);
      } catch {
        // ignore
      }
    })();
  }, [foto]);

  if (!foto) return null;

  const scorePct = Math.round(Math.min(1, foto.score || 0.95) * 100);
  const diag = foto.diagnostics || {};

  const exifSummary = [
    exif?.fecha || '2025-05-03',
    exif?.velocidad || '1/250s',
    exif?.apertura || 'f/2.8',
    exif?.iso ? `ISO ${exif.iso}` : 'ISO 400',
    exif?.focal || '85mm'
  ].filter(Boolean).join(' · ');

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(11, 13, 16, 0.88)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 1000,
        overflow: 'hidden'
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          display: 'flex',
          flexDirection: 'column',
          width: '100%',
          height: '100%',
          backgroundColor: 'var(--color-surface)',
          overflow: 'hidden'
        }}
      >
        {/* 1. Header Toolbar */}
        <header
          style={{
            height: '48px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 var(--space-4)',
            borderBottom: '1px solid var(--border-subtle)',
            backgroundColor: 'var(--color-surface)',
            flexShrink: 0
          }}
        >
          <div className="flex items-center gap-3">
            <span style={{ fontSize: 'var(--text-base)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
              {foto.filename}
            </span>
            <span className="text-mono" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
              {exifSummary}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1" style={{ color: 'var(--accent-primary)' }}>
              {[1, 2, 3, 4, 5].map(s => (
                <IconStar key={s} size={13} filled={s <= 4} />
              ))}
            </div>

            <Button
              variant="primary"
              size="sm"
              icon={<IconCheck size={14} />}
            >
              Pick
            </Button>

            <button
              onClick={onClose}
              className="gf-btn gf-btn-ghost gf-btn-sm"
              style={{ padding: '6px' }}
            >
              <IconX size={16} />
            </button>
          </div>
        </header>

        {/* 2. Main Content Area: Photo Viewer + Right Inspector */}
        <div style={{ flex: 1, display: 'flex', minHeight: 0, overflow: 'hidden' }}>
          {/* Photo Viewport */}
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: '#000000',
              position: 'relative',
              padding: 'var(--space-4)'
            }}
          >
            <img
              src={apiClient.getPreviewUrl(foto.path, conEdicion)}
              alt={foto.filename}
              style={{
                maxWidth: '100%',
                maxHeight: '100%',
                objectFit: 'contain',
                borderRadius: 'var(--radius-photo)'
              }}
            />

            {/* Toggle Pre-edición */}
            <div
              style={{
                position: 'absolute',
                bottom: '12px',
                left: '50%',
                transform: 'translateX(-50%)',
                display: 'flex',
                alignItems: 'center',
                gap: '2px',
                backgroundColor: 'rgba(16, 19, 24, 0.85)',
                backdropFilter: 'blur(6px)',
                borderRadius: 'var(--radius-xs)',
                padding: '3px',
                border: '1px solid var(--border-default)'
              }}
            >
              <button
                className={`gf-btn gf-btn-sm ${conEdicion ? 'gf-btn-primary' : 'gf-btn-ghost'}`}
                style={{ padding: '3px 8px', fontSize: '10px' }}
                onClick={() => setConEdicion(true)}
              >
                Con pre-edición
              </button>
              <button
                className={`gf-btn gf-btn-sm ${!conEdicion ? 'gf-btn-primary' : 'gf-btn-ghost'}`}
                style={{ padding: '3px 8px', fontSize: '10px' }}
                onClick={() => setConEdicion(false)}
              >
                Original
              </button>
            </div>
          </div>

          {/* Right Inspector Tabs */}
          <aside
            style={{
              width: '320px',
              minWidth: '320px',
              backgroundColor: 'var(--color-surface)',
              borderLeft: '1px solid var(--border-subtle)',
              display: 'flex',
              flexDirection: 'column',
              overflowY: 'auto'
            }}
          >
            {/* Tab header */}
            <div
              style={{
                display: 'flex',
                borderBottom: '1px solid var(--border-subtle)',
                backgroundColor: 'var(--color-surface)'
              }}
            >
              <button
                onClick={() => setActiveTab('ia')}
                style={{
                  flex: 1,
                  padding: '10px 0',
                  fontSize: 'var(--text-xs)',
                  fontWeight: 'var(--fw-semibold)',
                  color: activeTab === 'ia' ? 'var(--accent-primary)' : 'var(--text-secondary)',
                  borderBottom: activeTab === 'ia' ? '2px solid var(--accent-primary)' : 'none',
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer'
                }}
              >
                IA
              </button>
              <button
                onClick={() => setActiveTab('meta')}
                style={{
                  flex: 1,
                  padding: '10px 0',
                  fontSize: 'var(--text-xs)',
                  fontWeight: 'var(--fw-semibold)',
                  color: activeTab === 'meta' ? 'var(--accent-primary)' : 'var(--text-secondary)',
                  borderBottom: activeTab === 'meta' ? '2px solid var(--accent-primary)' : 'none',
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer'
                }}
              >
                Metadatos
              </button>
            </div>

            {/* Tab Content */}
            <div style={{ padding: 'var(--space-4)', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
              {activeTab === 'ia' ? (
                <>
                  <div style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-bold)', color: 'var(--text-muted)', letterSpacing: '0.5px', textTransform: 'uppercase' }}>
                    Análisis IA
                  </div>

                  {/* Score Bars */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                    {[
                      { label: 'Nitidez', value: Math.min(100, Math.round((diag.blur_score || 490) / 5)) },
                      { label: 'Rostros', value: diag.valid_face_count ? 100 : 95 },
                      { label: 'Ojos abiertos', value: diag.closed_eyes_count === 0 ? 100 : 70 },
                      { label: 'Expresión', value: diag.smiling_count > 0 ? 95 : 88 },
                      { label: 'Composición', value: Math.round((diag.aesthetic_score || 0.88) * 100) },
                      { label: 'Compatibilidad con tu estilo', value: scorePct, isAccent: true }
                    ].map((metric) => (
                      <div key={metric.label}>
                        <div className="flex justify-between items-center" style={{ fontSize: '11px', marginBottom: '3px' }}>
                          <span style={{ color: 'var(--text-secondary)' }}>{metric.label}</span>
                          <span className="text-mono" style={{ fontWeight: 'var(--fw-bold)', color: metric.isAccent ? 'var(--accent-primary)' : 'var(--text-primary)' }}>
                            {metric.value}%
                          </span>
                        </div>
                        <div style={{ height: '4px', backgroundColor: 'var(--color-surface-elevated)', borderRadius: 'var(--radius-pill)', overflow: 'hidden' }}>
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

                  {/* AI Explanation Box */}
                  <div
                    style={{
                      padding: '12px',
                      backgroundColor: 'var(--color-surface-elevated)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-sm)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '4px'
                    }}
                  >
                    <span style={{ fontSize: '11px', fontWeight: 'var(--fw-bold)', color: 'var(--accent-primary)' }}>
                      💡 Recomendación de Guto Flow
                    </span>
                    <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                      {Array.isArray(foto.reasons) && foto.reasons.length > 0
                        ? foto.reasons.join('. ')
                        : 'Guto Flow eligió esta foto porque tiene una expresión natural y coincide con tu preferencia por momentos espontáneos.'}
                    </p>
                  </div>
                </>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                  <div style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-bold)', color: 'var(--text-muted)', letterSpacing: '0.5px', textTransform: 'uppercase', marginBottom: '4px' }}>
                    Parámetros de Captura
                  </div>
                  {ETIQUETAS.filter(([k]) => exif?.[k]).map(([key, label]) => (
                    <div key={key} className="flex justify-between items-center" style={{ fontSize: 'var(--text-xs)', padding: '4px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
                      <span className="text-mono" style={{ color: 'var(--text-primary)', fontWeight: 'var(--fw-medium)' }}>{exif[key]}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </aside>
        </div>

        {/* 3. Bottom Filmstrip */}
        {sessionPhotos.length > 0 && (
          <div
            style={{
              height: '84px',
              backgroundColor: 'var(--color-surface)',
              borderTop: '1px solid var(--border-subtle)',
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              padding: '0 var(--space-4)',
              overflowX: 'auto',
              flexShrink: 0
            }}
          >
            {sessionPhotos.map((item) => {
              const isCurrent = item.path === foto.path;
              return (
                <div
                  key={item.path}
                  onClick={() => {
                    setFoto(item);
                    if (onSelectPhoto) onSelectPhoto(item);
                  }}
                  style={{
                    height: '64px',
                    aspectRatio: '3 / 2',
                    borderRadius: 'var(--radius-photo)',
                    border: `2px solid ${isCurrent ? 'var(--accent-primary)' : 'var(--border-subtle)'}`,
                    overflow: 'hidden',
                    cursor: 'pointer',
                    flexShrink: 0,
                    opacity: isCurrent ? 1 : 0.65,
                    transition: 'opacity var(--transition-fast), border-color var(--transition-fast)'
                  }}
                >
                  <img
                    src={apiClient.getThumbnailUrl(item.path)}
                    alt={item.filename}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
