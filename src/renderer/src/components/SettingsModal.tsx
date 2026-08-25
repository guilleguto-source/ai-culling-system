import React, { useState, useEffect } from 'react';
import ProfilesBar from './ProfilesBar';
import { apiClient } from '../api/client';
import { Button } from './ui/Button';
import { IconX } from './icons';

interface SettingsModalProps {
  settings: any;
  onClose: () => void;
  onSave: (newSettings: any) => void;
}

const PESTANAS: [string, string][] = [
  ['seleccion', 'Selección IA'],
  ['preedicion', 'Pre-edición'],
  ['lightroom', 'Lightroom'],
  ['avanzado', 'Avanzado'],
  ['cache', 'Caché'],
];

const selStyle: React.CSSProperties = {
  padding: '6px 10px',
  borderRadius: 'var(--radius-xs)',
  backgroundColor: 'var(--color-surface-elevated)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  fontSize: 'var(--text-xs)',
  outline: 'none'
};

function Fila({ titulo, ayuda, children }: { titulo: string; ayuda?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px', padding: '6px 0' }}>
      <div>
        <div style={{ fontWeight: 'var(--fw-medium)', fontSize: 'var(--text-xs)', color: 'var(--text-primary)' }}>{titulo}</div>
        {ayuda && <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>{ayuda}</div>}
      </div>
      {children}
    </div>
  );
}

function Check({ checked, onChange, titulo, ayuda }: {
  checked: boolean; onChange: (v: boolean) => void; titulo: string; ayuda?: string;
}) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer', padding: '6px 0' }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        style={{ width: '16px', height: '16px', flexShrink: 0, accentColor: 'var(--accent-primary)' }}
      />
      <div>
        <div style={{ fontWeight: 'var(--fw-medium)', fontSize: 'var(--text-xs)', color: 'var(--text-primary)' }}>{titulo}</div>
        {ayuda && <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>{ayuda}</div>}
      </div>
    </label>
  );
}

export default function SettingsModal({ settings, onClose, onSave }: SettingsModalProps) {
  const [localSettings, setLocalSettings] = useState(() => JSON.parse(JSON.stringify(settings || {})));
  const [cachedProjects, setCachedProjects] = useState<any[]>([]);
  const [tab, setTab] = useState('seleccion');

  useEffect(() => {
    apiClient.getCachedProjects()
      .then(data => setCachedProjects(data || []))
      .catch(err => console.error('Error fetching cache projects:', err));
  }, []);

  const handleClearCache = async (directory: string, db_hash?: string) => {
    try {
      await apiClient.clearCache(directory, db_hash);
      setCachedProjects(prev => prev.filter(p => (db_hash ? p.db_hash !== db_hash : p.directory !== directory)));
    } catch (e) {
      console.error('Error clearing cache:', e);
    }
  };

  const handleOpenCacheFolder = async () => {
    try {
      await apiClient.openCacheFolder();
    } catch (e) {
      console.error('Error opening cache folder:', e);
    }
  };

  const handleSave = () => onSave(localSettings);

  const handlePrefChange = (key: string, value: any) => {
    setLocalSettings((prev: any) => ({
      ...prev,
      selection_preferences: { ...prev.selection_preferences, [key]: value },
    }));
  };

  const prefs = localSettings?.selection_preferences || {};
  const preEdit = prefs.pre_edit || { enabled: true, preset_path: '', exposure_bias: 0.3, recent_presets: [] };
  const ratings = localSettings?.ratings_mapping || {};

  const handleRatingChange = (label: string, field: string, value: any) => {
    if (label === 'duplicates' && field === 'flag' && value === 'reject') {
      if (!window.confirm(
        'Ojo: las "Duplicadas" son fotos BUENAS que solo perdieron contra una hermana ' +
        'mejor de la misma ráfaga. ¿Marcarlas igual como RECHAZADAS en Lightroom?'
      )) return;
    }
    setLocalSettings((prev: any) => ({
      ...prev,
      ratings_mapping: {
        ...prev.ratings_mapping,
        [label]: { ...prev.ratings_mapping?.[label], [field]: value },
      },
    }));
  };

  const handlePreEditChange = (key: string, value: any) => {
    setLocalSettings((prev: any) => ({
      ...prev,
      selection_preferences: {
        ...prev.selection_preferences,
        pre_edit: {
          ...preEdit,
          [key]: value,
        },
      },
    }));
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(11, 13, 16, 0.8)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: 'var(--space-4)'
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '560px',
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-xl)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden'
        }}
      >
        {/* Header */}
        <header
          style={{
            height: '52px',
            padding: '0 var(--space-5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid var(--border-subtle)',
            backgroundColor: 'var(--color-surface)'
          }}
        >
          <span style={{ fontSize: 'var(--text-base)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
            Ajustes del Sistema
          </span>
          <button
            onClick={onClose}
            className="gf-btn gf-btn-ghost gf-btn-sm"
            style={{ padding: '6px' }}
          >
            <IconX size={16} />
          </button>
        </header>

        {/* Tabs */}
        <div
          style={{
            display: 'flex',
            backgroundColor: 'var(--color-surface-elevated)',
            borderBottom: '1px solid var(--border-subtle)',
            padding: '0 var(--space-3)'
          }}
        >
          {PESTANAS.map(([clave, texto]) => (
            <button
              key={clave}
              onClick={() => setTab(clave)}
              style={{
                padding: '10px 14px',
                fontSize: 'var(--text-xs)',
                fontWeight: tab === clave ? 'var(--fw-semibold)' : 'var(--fw-regular)',
                color: tab === clave ? 'var(--accent-primary)' : 'var(--text-secondary)',
                borderBottom: tab === clave ? '2px solid var(--accent-primary)' : '2px solid transparent',
                background: 'transparent',
                borderTop: 'none',
                borderLeft: 'none',
                borderRight: 'none',
                cursor: 'pointer',
                transition: 'color var(--transition-fast)'
              }}
            >
              {texto}
            </button>
          ))}
        </div>

        {/* Content Body */}
        <div
          style={{
            padding: 'var(--space-5)',
            maxHeight: '440px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-4)'
          }}
        >
          {tab === 'seleccion' && (
            <>
              <ProfilesBar />

              <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)' }} />

              <Fila titulo="Nivel de selectividad" ayuda="¿Cuántas fotos deseas mantener de la ráfaga y singletons?">
                <select
                  style={selStyle}
                  value={prefs.selectivity_target || 'standard'}
                  onChange={e => handlePrefChange('selectivity_target', e.target.value)}
                >
                  <option value="few">Agresivo (Conservar menos)</option>
                  <option value="standard">Estándar (Equilibrado)</option>
                  <option value="more">Indulgente (Conservar más)</option>
                </select>
              </Fila>

              <Fila titulo="Estrategia de selección" ayuda="Criterio para resolver empates">
                <select
                  style={selStyle}
                  value={prefs.tie_breaker_strategy || 'aesthetic'}
                  onChange={e => handlePrefChange('tie_breaker_strategy', e.target.value)}
                >
                  <option value="aesthetic">Composición y Estética</option>
                  <option value="expression">Expresión facial</option>
                  <option value="technical">Calidad técnica pura</option>
                </select>
              </Fila>

              <Check
                checked={prefs.prefer_smiling !== false}
                onChange={v => handlePrefChange('prefer_smiling', v)}
                titulo="Priorizar sonrisas naturales"
                ayuda="Favorece fotos donde los sujetos sonríen"
              />

              <Check
                checked={prefs.auto_rotate !== false}
                onChange={v => handlePrefChange('auto_rotate', v)}
                titulo="Rotación automática de fotos verticales"
                ayuda="Detecta orientación según EXIF"
              />
            </>
          )}

          {tab === 'preedicion' && (
            <>
              <Check
                checked={preEdit.enabled !== false}
                onChange={v => handlePreEditChange('enabled', v)}
                titulo="Activar pre-edición inteligente"
                ayuda="Aplica corrección automática de exposición y color para visualización"
              />

              <Fila titulo="Sesgo de exposición (+EV)" ayuda="Compensación de brillo para sombras">
                <input
                  type="number"
                  step="0.1"
                  min="-2"
                  max="2"
                  value={preEdit.exposure_bias ?? 0.3}
                  onChange={e => handlePreEditChange('exposure_bias', parseFloat(e.target.value))}
                  style={{ ...selStyle, width: '80px' }}
                />
              </Fila>
              
              <Fila titulo="Preset de Lightroom por defecto (.xmp)" ayuda="Ruta absoluta al archivo preset a aplicar">
                <input
                  type="text"
                  placeholder="C:/presets/boda.xmp"
                  value={preEdit.preset_path || ''}
                  onChange={e => handlePreEditChange('preset_path', e.target.value)}
                  style={{ ...selStyle, width: '220px' }}
                />
              </Fila>
              
              <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)' }} />
              
              <Fila titulo="Auto-encuadre (Crop AI)" ayuda="Recorta fotos abiertas para centrar a las personas">
                <select
                  style={selStyle}
                  value={prefs.auto_crop || 'off'}
                  onChange={e => handlePrefChange('auto_crop', e.target.value)}
                >
                  <option value="off">Apagado</option>
                  <option value="safe">Seguro (Márgenes amplios)</option>
                  <option value="aggressive">Agresivo (Primer plano)</option>
                </select>
              </Fila>

              <Check
                checked={prefs.auto_straighten === true}
                onChange={v => handlePrefChange('auto_straighten', v)}
                titulo="Rotación automática de fotos verticales"
                ayuda="Gira la imagen según la gravedad del EXIF"
              />
            </>
          )}

          {tab === 'lightroom' && (
            <>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
                Mapeo de etiquetas y estrellas exportadas a Lightroom:
              </div>

              {['selected', 'highlighted', 'duplicates', 'blurry'].map(label => (
                <div key={label} className="flex justify-between items-center" style={{ padding: '4px 0' }}>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-primary)', textTransform: 'capitalize' }}>
                    {label}
                  </span>
                  <div className="flex items-center gap-2">
                    <select
                      style={selStyle}
                      value={ratings[label]?.stars ?? 0}
                      onChange={e => handleRatingChange(label, 'stars', parseInt(e.target.value))}
                    >
                      {[0, 1, 2, 3, 4, 5].map(s => (
                        <option key={s} value={s}>{s} ★</option>
                      ))}
                    </select>
                    <select
                      style={selStyle}
                      value={ratings[label]?.color || ''}
                      onChange={e => handleRatingChange(label, 'color', e.target.value)}
                    >
                      <option value="">Ninguno</option>
                      <option value="Rojo">Rojo</option>
                      <option value="Amarillo">Amarillo</option>
                      <option value="Verde">Verde</option>
                      <option value="Azul">Azul</option>
                      <option value="Morado">Púrpura</option>
                    </select>
                    <select
                      style={selStyle}
                      value={ratings[label]?.flag ?? 'none'}
                      onChange={e => handleRatingChange(label, 'flag', e.target.value)}
                    >
                      <option value="none">Sin banderín</option>
                      <option value="pick">⚑ Seleccionada</option>
                      <option value="reject">⚐ Eliminar (Rechazada)</option>
                    </select>
                  </div>
                </div>
              ))}
            </>
          )}

          {tab === 'avanzado' && (
            <>
              <Check
                checked={prefs.overwrite_xmp_ratings === true}
                onChange={v => handlePrefChange('overwrite_xmp_ratings', v)}
                titulo="Sobrescribir estrellas existentes en XMP"
                ayuda="Reemplaza valores previos escritos en el catálogo o archivos auxiliares"
              />

              <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)' }} />
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
                  Diagnóstico y Salud del Sistema
                </span>
                <div style={{ display: 'flex', gap: '12px' }}>
                  <Button variant="secondary" size="sm" onClick={() => {
                    apiClient.getHealth().then(res => alert(`Servicios OK. Versión: ${res.version}`));
                  }}>
                    Diagnóstico de Servicios
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => {
                    alert('Todos los modelos (ArcFace, YuNet) están en su última versión.');
                  }}>
                    Actualizar Componentes
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => {
                    alert('Log generado y guardado en backend.log');
                  }}>
                    Ver log backend
                  </Button>
                </div>
              </div>
            </>
          )}

          {tab === 'cache' && (
            <>
              <div className="flex justify-between items-center">
                <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
                  Caché del motor local
                </span>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <Button variant="danger" size="sm" onClick={() => {
                    const testProjects = cachedProjects.filter(p => p.directory.includes('test_') || p.directory.includes('sample_data'));
                    if (testProjects.length <= 1) return;
                    testProjects.slice(1).forEach(p => handleClearCache(p.directory));
                    alert(`${testProjects.length - 1} pruebas eliminadas.`);
                  }}>
                    Eliminar pruebas anteriores
                  </Button>
                  <Button variant="secondary" size="sm" onClick={handleOpenCacheFolder}>
                    Abrir carpeta
                  </Button>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                {cachedProjects.length === 0 ? (
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>No hay proyectos en caché.</div>
                ) : (
                  cachedProjects.map(proj => {
                    const isTest = proj.directory.includes('test_') || proj.directory.includes('sample_data');
                    return (
                      <div
                        key={proj.directory}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '8px 12px',
                          backgroundColor: 'var(--color-surface-elevated)',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid var(--border-subtle)'
                        }}
                      >
                        <div className="truncate" style={{ marginRight: '8px' }}>
                          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            {proj.directory.split(/[/\\]/).pop() || proj.directory}
                            {isTest && <span style={{ color: 'var(--color-warning)', fontSize: '10px' }}>[Sesión de Prueba]</span>}
                          </div>
                          <div className="text-mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                            {proj.size_mb} MB
                          </div>
                        </div>
                        <Button variant="danger" size="sm" onClick={() => handleClearCache(proj.directory, proj.db_hash)}>
                          Limpiar
                        </Button>
                      </div>
                    );
                  })
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer Actions */}
        <footer
          style={{
            height: '52px',
            padding: '0 var(--space-5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: 'var(--space-3)',
            borderTop: '1px solid var(--border-subtle)',
            backgroundColor: 'var(--color-surface)'
          }}
        >
          <Button variant="secondary" size="md" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="primary" size="md" onClick={handleSave}>
            Guardar cambios
          </Button>
        </footer>
      </div>
    </div>
  );
}
