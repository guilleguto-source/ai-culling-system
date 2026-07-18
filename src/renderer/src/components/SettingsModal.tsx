import React, { useState, useEffect } from 'react';
import ProfilesBar from './ProfilesBar';

interface SettingsModalProps {
  settings: any;
  onClose: () => void;
  onSave: (newSettings: any) => void;
}

const PESTANAS: [string, string][] = [
  ['seleccion', '🧠 Selección'],
  ['preedicion', '🎨 Pre-edición'],
  ['lightroom', '⭐ Lightroom'],
  ['avanzado', '⚙ Avanzado'],
];

const selStyle: React.CSSProperties = {
  padding: '4px 6px', borderRadius: '4px', background: 'var(--bg-tertiary)',
  color: 'white', border: '1px solid var(--border-strong)',
};

/** Fila con título, ayuda y un control a la derecha. */
function Fila({ titulo, ayuda, children }: { titulo: string; ayuda?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px' }}>
      <div>
        <div style={{ fontWeight: 500 }}>{titulo}</div>
        {ayuda && <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>{ayuda}</div>}
      </div>
      {children}
    </div>
  );
}

/** Casilla con título y ayuda. */
function Check({ checked, onChange, titulo, ayuda }: {
  checked: boolean; onChange: (v: boolean) => void; titulo: string; ayuda?: string;
}) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)}
        style={{ width: '13px', height: '13px', flexShrink: 0 }} />
      <div>
        <div style={{ fontWeight: 500 }}>{titulo}</div>
        {ayuda && <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>{ayuda}</div>}
      </div>
    </label>
  );
}

export default function SettingsModal({ settings, onClose, onSave }: SettingsModalProps) {
  const [localSettings, setLocalSettings] = useState(() => JSON.parse(JSON.stringify(settings || {})));
  const [cachedProjects, setCachedProjects] = useState<any[]>([]);
  const [tab, setTab] = useState('seleccion');

  useEffect(() => {
    fetch('http://127.0.0.1:8000/cache/projects')
      .then(res => res.json())
      .then(data => setCachedProjects(data))
      .catch(err => console.error('Error fetching cache projects:', err));
  }, []);

  const handleClearCache = async (directory: string) => {
    try {
      const res = await fetch('http://127.0.0.1:8000/cache/clear', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory }),
      });
      if (res.ok) setCachedProjects(prev => prev.filter(p => p.directory !== directory));
    } catch (e) {
      console.error('Error clearing cache:', e);
    }
  };

  const handleOpenCacheFolder = async () => {
    try {
      await fetch('http://127.0.0.1:8000/cache/open', { method: 'POST' });
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
        'mejor de la misma ráfaga — no son basura. ¿Marcarlas igual como RECHAZADAS ' +
        '(banderín negro) en Lightroom?'
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
    handlePrefChange('pre_edit', { ...preEdit, [key]: value });
  };

  const usePresetFile = async (path: string) => {
    try {
      const res = await fetch('http://127.0.0.1:8000/presets/use', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      const data = await res.json();
      if (res.ok) {
        handlePrefChange('pre_edit', { ...preEdit, preset_path: data.active, recent_presets: data.recent });
      } else {
        alert(data.detail || 'Preset no válido');
      }
    } catch (e) {
      alert('Error de conexión con el backend');
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, backgroundColor: 'rgba(0, 0, 0, 0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 50, backdropFilter: 'blur(4px)',
    }}>
      <div className="glass-panel" style={{
        width: '560px', maxHeight: '92vh', display: 'flex', flexDirection: 'column',
        backgroundColor: 'var(--bg-secondary)', padding: 0, fontSize: '0.72rem',
      }}>

        {/* Cabecera */}
        <div style={{
          padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0,
        }}>
          <h2 style={{ margin: 0, fontSize: '0.95rem' }}>Ajustes</h2>
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none', color: 'var(--text-muted)',
            cursor: 'pointer', fontSize: '0.95rem',
          }}>×</button>
        </div>

        {/* Perfiles: aplican a todas las pestañas, van arriba */}
        <div style={{ padding: '12px 14px 0' }}>
          <ProfilesBar />
        </div>

        {/* Pestañas */}
        <div style={{ display: 'flex', gap: '6px', padding: '12px 14px 0', flexWrap: 'wrap' }}>
          {PESTANAS.map(([clave, texto]) => (
            <button key={clave}
              className={tab === clave ? 'btn btn-primary' : 'btn btn-secondary'}
              style={{ padding: '5px 12px', fontSize: '0.75rem' }}
              onClick={() => setTab(clave)}>
              {texto}
            </button>
          ))}
        </div>

        {/* Cuerpo */}
        <div style={{
          padding: '14px', display: 'flex', flexDirection: 'column', gap: '12px',
          overflowY: 'auto', flex: 1,
        }}>

          {tab === 'seleccion' && (
            <>
              <Fila titulo="Selectividad" ayuda="¿Qué tan exigente al descartar?">
                <select value={prefs.selectivity_target || 'standard'} style={selStyle}
                  onChange={e => handlePrefChange('selectivity_target', e.target.value)}>
                  <option value="few">Pocas (exigente)</option>
                  <option value="standard">Equilibrado</option>
                  <option value="more">Muchas (permisivo)</option>
                </select>
              </Fila>

              <Fila titulo="Sensibilidad al desenfoque" ayuda="Cuánto movimiento o falta de foco tolera">
                <select value={prefs.blurry_sensitivity || 'moderate'} style={selStyle}
                  onChange={e => handlePrefChange('blurry_sensitivity', e.target.value)}>
                  <option value="lenient">Permisiva</option>
                  <option value="moderate">Moderada</option>
                  <option value="strict">Estricta</option>
                </select>
              </Fila>

              <Check checked={prefs.detect_duplicates !== false}
                onChange={v => handlePrefChange('detect_duplicates', v)}
                titulo="Detectar repetidas"
                ayuda="Agrupa las ráfagas y elige la mejor de cada una" />

              <Check checked={prefs.detect_closed_eyes !== false}
                onChange={v => handlePrefChange('detect_closed_eyes', v)}
                titulo="Detectar ojos cerrados"
                ayuda="Descarta la peor de la grupal cuando hay alguien parpadeando" />

              <Check checked={prefs.ensure_person_coverage !== false}
                onChange={v => handlePrefChange('ensure_person_coverage', v)}
                titulo="Una buena foto de cada persona"
                ayuda="Si alguien quedó sin ninguna seleccionada, promueve su mejor foto" />
            </>
          )}

          {tab === 'preedicion' && (
            <>
              <Check checked={preEdit.enabled !== false}
                onChange={v => handlePreEditChange('enabled', v)}
                titulo="Pre-edición (preset + WB + exposición)"
                ayuda="Escribe ajustes de revelado reversibles en el XMP de las fotos elegidas" />

              {preEdit.enabled !== false && (
                <>
                  <div
                    onDragOver={e => e.preventDefault()}
                    onDrop={e => {
                      e.preventDefault();
                      const f = e.dataTransfer.files?.[0] as any;
                      if (f?.path) usePresetFile(f.path);
                    }}
                    style={{
                      border: '1px dashed var(--border-strong)', borderRadius: '6px',
                      padding: '10px', textAlign: 'center', fontSize: '0.72rem',
                      color: 'var(--text-muted)',
                    }}
                  >
                    Arrastrá aquí tu preset .xmp de Lightroom, o{' '}
                    <label style={{ color: 'var(--accent-primary)', cursor: 'pointer', textDecoration: 'underline' }}>
                      buscalo
                      <input type="file" accept=".xmp" style={{ display: 'none' }}
                        onChange={e => {
                          const f = e.target.files?.[0] as any;
                          if (f?.path) usePresetFile(f.path);
                          e.target.value = '';
                        }} />
                    </label>
                    <div style={{ marginTop: '4px', fontSize: '0.65rem' }}>
                      Las máscaras IA del preset pueden pedir "Actualizar ajustes de IA" en Lightroom
                    </div>
                  </div>

                  <Fila titulo="Preset activo">
                    <select value={preEdit.preset_path || ''} style={{ ...selStyle, maxWidth: '260px' }}
                      onChange={e => {
                        if (e.target.value === '') {
                          usePresetFile('');
                          handlePreEditChange('preset_path', '');
                        } else {
                          usePresetFile(e.target.value);
                        }
                      }}>
                      <option value="">Ninguno (solo WB + exposición)</option>
                      {(preEdit.recent_presets || []).map((p: any) => (
                        <option key={p.path} value={p.path}>{p.name}</option>
                      ))}
                    </select>
                  </Fila>

                  <Fila titulo="Sesgo de exposición" ayuda="Se suma a la exposición medida en las personas">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <input type="range" min={-0.5} max={0.5} step={0.05}
                        value={preEdit.exposure_bias ?? 0.3}
                        onChange={e => handlePreEditChange('exposure_bias', parseFloat(e.target.value))} />
                      <span style={{ width: '52px', textAlign: 'right' }}>
                        {(preEdit.exposure_bias ?? 0.3) >= 0 ? '+' : ''}{(preEdit.exposure_bias ?? 0.3).toFixed(2)} EV
                      </span>
                    </div>
                  </Fila>
                </>
              )}

              <Fila titulo="Auto-encuadre"
                ayuda="Recorte propuesto (reversible en Lightroom). En grupos: solo nivelado.">
                <select value={prefs.auto_crop || 'minimo'} style={selStyle}
                  onChange={e => handlePrefChange('auto_crop', e.target.value)}>
                  <option value="off">Desactivado</option>
                  <option value="minimo">Mínimo (10%)</option>
                  <option value="medio">Medio (20%)</option>
                  <option value="agresivo">Agresivo (35%)</option>
                </select>
              </Fila>
            </>
          )}

          {tab === 'lightroom' && (
            <>
              <div style={{ fontWeight: 600 }}>Calificación de estrellas y colores</div>
              {([
                ['Selecciones de IA', [
                  ['selected', 'Seleccionadas', 'La mejor de cada ráfaga'],
                  ['highlighted', 'Destacadas', 'El top 10% de las seleccionadas'],
                ]],
                ['Descartes', [
                  ['blurry', 'Pérdida total', 'Quemada, negra o movida sin NADA enfocado — para borrar'],
                  ['closed_eyes', 'Ojos cerrados', 'Retrato con ojos cerrados que no ganó su grupo'],
                  ['duplicates', 'Duplicadas', 'Fotos BUENAS que perdieron contra una hermana mejor'],
                ]],
              ] as [string, [string, string, string][]][]).map(([grupo, filas]) => (
                <div key={grupo}>
                  <div style={{
                    fontSize: '0.65rem', color: 'var(--text-muted)',
                    textTransform: 'uppercase', marginBottom: '6px',
                  }}>{grupo}</div>
                  {filas.map(([label, nombre, ayuda]) => {
                    const r = ratings[label] || { stars: 0, color: '', flag: 'none' };
                    return (
                      <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                        <span style={{ flex: 1 }} title={ayuda}>
                          {nombre}
                          <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', lineHeight: 1.25 }}>{ayuda}</div>
                        </span>
                        <select value={r.stars ?? 0} style={selStyle}
                          onChange={e => handleRatingChange(label, 'stars', parseInt(e.target.value))}>
                          {[0, 1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}★</option>)}
                        </select>
                        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                          {(['', 'Rojo', 'Amarillo', 'Verde', 'Azul', 'Morado'] as string[]).map(c => {
                            const hex: Record<string, string> = {
                              Rojo: '#e5484d', Amarillo: '#f0c000', Verde: '#46a758',
                              Azul: '#0091ff', Morado: '#8e4ec6',
                            };
                            const activo = (r.color || '') === c;
                            return (
                              <div key={c || 'none'} title={c || 'Sin color'}
                                onClick={() => handleRatingChange(label, 'color', c)}
                                style={{
                                  width: '14px', height: '14px', borderRadius: '50%',
                                  cursor: 'pointer', boxSizing: 'border-box',
                                  background: c ? hex[c]
                                    : 'linear-gradient(135deg, transparent 42%, #888 42%, #888 58%, transparent 58%)',
                                  border: activo ? '2px solid white' : '1px solid var(--border-strong)',
                                  transform: activo ? 'scale(1.2)' : 'none',
                                }} />
                            );
                          })}
                        </div>
                        <select value={r.flag || 'none'} style={selStyle}
                          onChange={e => handleRatingChange(label, 'flag', e.target.value)}>
                          <option value="none">Sin banderín</option>
                          <option value="pick">⚑ Seleccionada</option>
                          <option value="reject">⚐ Rechazada</option>
                        </select>
                      </div>
                    );
                  })}
                </div>
              ))}
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
                El color debe coincidir exactamente con tu conjunto de etiquetas de Lightroom.
              </div>

              <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)', margin: '6px 0' }} />

              {/* Con el catálogo configurado se puede avisar ANTES de sincronizar
                  si Lightroom tiene cambios que nunca se volcaron al archivo. */}
              <div>
                <div style={{ fontWeight: 500 }}>Catálogo de Lightroom (.lrcat)</div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: '6px' }}>
                  Opcional. Permite avisarte si hay cambios sin guardar al archivo antes de sincronizar.
                </div>
                <input
                  type="text"
                  value={prefs.lightroom_catalog_path || ''}
                  placeholder="C:\Users\...\Catalogo.lrcat"
                  onChange={e => handlePrefChange('lightroom_catalog_path', e.target.value)}
                  style={{
                    width: '100%', padding: '6px 8px', borderRadius: '4px',
                    background: 'var(--bg-tertiary)', color: 'var(--text-primary)',
                    border: '1px solid var(--border-strong)', fontSize: '0.72rem',
                  }}
                />
              </div>
            </>
          )}

          {tab === 'avanzado' && (
            <>
              <Check checked={prefs.overwrite_xmp_ratings === true}
                onChange={v => handlePrefChange('overwrite_xmp_ratings', v)}
                titulo="Sobrescribir estrellas existentes"
                ayuda="Cuidado: pisa las estrellas que ya tengas puestas en Lightroom" />

              <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)', margin: '4px 0' }} />

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ fontWeight: 600 }}>Caché e historial</div>
                <button className="btn btn-secondary" onClick={handleOpenCacheFolder}
                  style={{ padding: '4px 8px', fontSize: '0.7rem' }}>
                  Abrir carpeta
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '260px', overflowY: 'auto' }}>
                {cachedProjects.length === 0 ? (
                  <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>No hay proyectos en caché.</div>
                ) : (
                  cachedProjects.map(proj => (
                    <div key={proj.directory} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '8px', backgroundColor: 'var(--bg-tertiary)',
                      borderRadius: '6px', border: '1px solid var(--border-subtle)',
                    }}>
                      <div style={{ overflow: 'hidden', flex: 1, marginRight: '8px' }}>
                        <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                          title={proj.directory}>
                          {proj.directory.split(/[/\\]/).pop() || proj.directory}
                        </div>
                        <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)' }}>
                          {new Date(proj.last_accessed * 1000).toLocaleDateString()} • {proj.size_mb} MB
                        </div>
                      </div>
                      <button onClick={() => handleClearCache(proj.directory)} style={{
                        background: 'transparent', border: '1px solid var(--status-error-border)',
                        color: 'var(--status-error-text)', borderRadius: '4px',
                        padding: '4px 8px', cursor: 'pointer', fontSize: '0.7rem',
                      }}>Eliminar</button>
                    </div>
                  ))
                )}
              </div>
            </>
          )}

        </div>

        {/* Pie */}
        <div style={{
          padding: '14px 20px', borderTop: '1px solid var(--border-subtle)',
          display: 'flex', justifyContent: 'flex-end', gap: '12px',
          backgroundColor: 'var(--bg-primary)',
          borderBottomLeftRadius: '12px', borderBottomRightRadius: '12px',
        }}>
          <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
          <button className="btn btn-primary" onClick={handleSave}>Guardar</button>
        </div>

      </div>
    </div>
  );
}
