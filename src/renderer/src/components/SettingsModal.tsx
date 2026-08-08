import React, { useState, useEffect } from 'react';
import ProfilesBar from './ProfilesBar';
import { apiClient } from '../api/client';

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
        <div style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{titulo}</div>
        {ayuda && <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>{ayuda}</div>}
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
        style={{ width: '15px', height: '15px', flexShrink: 0, accentColor: 'var(--accent-amber)' }} />
      <div>
        <div style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{titulo}</div>
        {ayuda && <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>{ayuda}</div>}
      </div>
    </label>
  );
}

export default function SettingsModal({ settings, onClose, onSave }: SettingsModalProps) {
  const [localSettings, setLocalSettings] = useState(() => JSON.parse(JSON.stringify(settings || {})));
  const [cachedProjects, setCachedProjects] = useState<any[]>([]);
  const [tab, setTab] = useState('seleccion');

  useEffect(() => {
    apiClient.getCacheProjects()
      .then(data => setCachedProjects(data))
      .catch(err => console.error('Error fetching cache projects:', err));
  }, []);

  const handleClearCache = async (directory: string) => {
    try {
      await apiClient.clearCache(directory);
      setCachedProjects(prev => prev.filter(p => p.directory !== directory));
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
      const data = await apiClient.usePreset(path);
      handlePrefChange('pre_edit', { ...preEdit, preset_path: data.active, recent_presets: data.recent });
    } catch (e: any) {
      alert(e.message || 'Error con el preset');
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
          <h2 style={{ margin: 0, fontSize: '0.95rem', color: 'var(--text-primary)' }}>Ajustes</h2>
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none', color: 'var(--text-secondary)',
            cursor: 'pointer', fontSize: '1.2rem', padding: '0 4px'
          }}>×</button>
        </div>

        {/* Perfiles */}
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
                        value={preEdit.exposure_bias ?? 0.0}
                        onChange={e => handlePreEditChange('exposure_bias', parseFloat(e.target.value))} />
                      <span style={{ width: '52px', textAlign: 'right' }}>
                        {(preEdit.exposure_bias ?? 0.0) >= 0 ? '+' : ''}{(preEdit.exposure_bias ?? 0.0).toFixed(2)} EV
                      </span>
                    </div>
                  </Fila>

                  {/* Neural 3D-LUT */}
                  <div style={{
                    border: '1px solid var(--border-subtle)', borderRadius: '6px',
                    padding: '10px', marginTop: '4px', backgroundColor: 'rgba(255,255,255,0.02)'
                  }}>
                    <Check
                      checked={preEdit.neural_lut?.enabled !== false}
                      onChange={v => {
                        const cur = preEdit.neural_lut || { enabled: true, strength: 0.8, fallback_lut: 'warm_golden' };
                        handlePreEditChange('neural_lut', { ...cur, enabled: v });
                      }}
                      titulo="Neural 3D-LUT (Look de Color Adaptativo)"
                      ayuda="Aprende el estilo de contraste y tonos de tus sesiones pasadas (coexiste con tu preset)"
                    />
                    {preEdit.neural_lut?.enabled !== false && (
                      <div style={{ marginTop: '8px', paddingLeft: '24px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <Fila titulo="Intensidad de color/tono" ayuda="0% usa solo tu preset base; 100% aplica todo el estilo aprendido">
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <input type="range" min={0.0} max={1.0} step={0.05}
                              value={preEdit.neural_lut?.strength ?? 0.8}
                              onChange={e => {
                                const cur = preEdit.neural_lut || { enabled: true, strength: 0.8, fallback_lut: 'warm_golden' };
                                handlePreEditChange('neural_lut', { ...cur, strength: parseFloat(e.target.value) });
                              }} />
                            <span style={{ width: '45px', textAlign: 'right' }}>
                              {Math.round((preEdit.neural_lut?.strength ?? 0.8) * 100)}%
                            </span>
                          </div>
                        </Fila>
                        <Fila titulo="Perfil Base / Fallback" ayuda="Se usa cuando aún no hay historial suficiente para un tipo de escena">
                          <select
                            value={preEdit.neural_lut?.fallback_lut || 'warm_golden'}
                            style={selStyle}
                            onChange={e => {
                              const cur = preEdit.neural_lut || { enabled: true, strength: 0.8, fallback_lut: 'warm_golden' };
                              handlePreEditChange('neural_lut', { ...cur, fallback_lut: e.target.value });
                            }}
                          >
                            <option value="warm_golden">Cálido / Golden Hour</option>
                            <option value="cool_indoor">Interior / Tungsteno Frío</option>
                            <option value="flat_matte">Editorial / Flat Matte</option>
                            <option value="vivid_outdoor">Exterior Vívido</option>
                            <option value="neutral">Neutro / Sin Alteración</option>
                          </select>
                        </Fila>
                      </div>
                    )}
                  </div>

                  {/* Rescate Tonal Automático */}
                  <Check
                    checked={preEdit.tonal_rescue?.enabled !== false}
                    onChange={v => {
                      const cur = preEdit.tonal_rescue || { enabled: true, highlights_threshold: 0.05, shadows_threshold: 0.10 };
                      handlePreEditChange('tonal_rescue', { ...cur, enabled: v });
                    }}
                    titulo="Rescate Tonal Automático"
                    ayuda="Recupera automáticamente detalle en fotos con altas luces quemadas (>5%) o sombras empastadas (>10%)"
                  />
                </>
              )}

              <Fila titulo="Auto-encuadre"
                ayuda="Recorte propuesto (reversible en Lightroom). En grupos: solo nivelado.">
                <select value={prefs.auto_crop || 'off'} style={selStyle}
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
