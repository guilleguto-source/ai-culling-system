import React, { useState, useEffect } from 'react';
import ProfilesBar from './ProfilesBar';

interface SettingsModalProps {
  settings: any;
  onClose: () => void;
  onSave: (newSettings: any) => void;
}

export default function SettingsModal({ settings, onClose, onSave }: SettingsModalProps) {
  // Use a local copy of settings for editing
  const [localSettings, setLocalSettings] = useState(() => JSON.parse(JSON.stringify(settings || {})));
  const [cachedProjects, setCachedProjects] = useState<any[]>([]);

  useEffect(() => {
    fetch('http://127.0.0.1:8000/cache/projects')
      .then(res => res.json())
      .then(data => setCachedProjects(data))
      .catch(err => console.error("Error fetching cache projects:", err));
  }, []);

  const handleClearCache = async (directory: string) => {
    try {
      const res = await fetch('http://127.0.0.1:8000/cache/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory })
      });
      if (res.ok) {
        setCachedProjects(prev => prev.filter(p => p.directory !== directory));
      }
    } catch (e) {
      console.error("Error clearing cache:", e);
    }
  };

  const handleOpenCacheFolder = async () => {
    try {
      await fetch('http://127.0.0.1:8000/cache/open', { method: 'POST' });
    } catch (e) {
      console.error("Error opening cache folder:", e);
    }
  };

  const handleSave = () => {
    onSave(localSettings);
  };

  const handlePrefChange = (key: string, value: any) => {
    setLocalSettings((prev: any) => ({
      ...prev,
      selection_preferences: {
        ...prev.selection_preferences,
        [key]: value
      }
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
      )) {
        return;
      }
    }
    setLocalSettings((prev: any) => ({
      ...prev,
      ratings_mapping: {
        ...prev.ratings_mapping,
        [label]: { ...prev.ratings_mapping?.[label], [field]: value }
      }
    }));
  };

  const handlePreEditChange = (key: string, value: any) => {
    handlePrefChange('pre_edit', { ...preEdit, [key]: value });
  };

  const usePresetFile = async (path: string) => {
    try {
      const res = await fetch('http://127.0.0.1:8000/presets/use', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      });
      const data = await res.json();
      if (res.ok) {
        handlePrefChange('pre_edit', {
          ...preEdit,
          preset_path: data.active,
          recent_presets: data.recent
        });
      } else {
        alert(data.detail || 'Preset no válido');
      }
    } catch (e) {
      alert('Error de conexión con el backend');
    }
  };

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 50,
      backdropFilter: 'blur(4px)'
    }}>
      <div className="glass-panel" style={{ width: '460px', maxHeight: '92vh', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg-secondary)', padding: '0', fontSize: '0.62rem' }}>

        {/* Header */}
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
          <h2 style={{ margin: 0, fontSize: '0.95rem' }}>Preferencias de culling</h2>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.95rem' }}
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px', overflowY: 'auto', flex: 1 }}>

          <ProfilesBar />

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 500 }}>Selectividad</div>
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>¿Qué tan exigente al descartar?</div>
            </div>
            <select 
              value={prefs.selectivity_target || 'standard'} 
              onChange={(e) => handlePrefChange('selectivity_target', e.target.value)}
              style={{ padding: '4px 6px', borderRadius: '4px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--border-strong)' }}
            >
              <option value="few">Few (Aggressive)</option>
              <option value="standard">Standard</option>
              <option value="more">More (Lenient)</option>
            </select>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 500 }}>Blurry Sensitivity</div>
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Tolerance for out of focus shots</div>
            </div>
            <select 
              value={prefs.blurry_sensitivity || 'moderate'} 
              onChange={(e) => handlePrefChange('blurry_sensitivity', e.target.value)}
              style={{ padding: '4px 6px', borderRadius: '4px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--border-strong)' }}
            >
              <option value="lenient">Lenient</option>
              <option value="moderate">Moderate</option>
              <option value="strict">Strict</option>
            </select>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 500 }}>Auto-encuadre</div>
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Recorte propuesto (reversible en Lightroom). Grupos: solo nivelado.</div>
            </div>
            <select
              value={prefs.auto_crop || 'minimo'}
              onChange={(e) => handlePrefChange('auto_crop', e.target.value)}
              style={{ padding: '4px 6px', borderRadius: '4px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--border-strong)' }}
            >
              <option value="off">Desactivado</option>
              <option value="minimo">Mínimo (10%)</option>
              <option value="medio">Medio (20%)</option>
              <option value="agresivo">Agresivo (35%)</option>
            </select>
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={prefs.detect_duplicates !== false}
              onChange={(e) => handlePrefChange('detect_duplicates', e.target.checked)}
              style={{ width: '13px', height: '13px' }}
            />
            <div>
              <div style={{ fontWeight: 500 }}>Detectar repetidas</div>
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Group similar photos and select the best</div>
            </div>
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
            <input 
              type="checkbox" 
              checked={prefs.detect_closed_eyes !== false} 
              onChange={(e) => handlePrefChange('detect_closed_eyes', e.target.checked)}
              style={{ width: '13px', height: '13px' }}
            />
            <div>
              <div style={{ fontWeight: 500 }}>Detectar ojos cerrados</div>
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Flag portraits with closed eyes</div>
            </div>
          </label>
          
          {/* --- Calificación de estrellas, colores y banderines --- */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '10px' }}>
            <div style={{ fontWeight: 600, marginBottom: '8px' }}>Calificación de estrellas y colores</div>
            {([
              ['Selecciones de IA', [
                ['selected', 'Seleccionadas', 'La mejor de cada grupo similar'],
                ['highlighted', 'Destacadas', 'El top 10% de las seleccionadas'],
              ]],
              ['Descartes', [
                ['blurry', 'Pérdida total', 'Quemada, negra o movida sin NADA enfocado — para borrar'],
                ['closed_eyes', 'Ojos cerrados', 'Retrato con ojos cerrados que no ganó su grupo'],
                ['duplicates', 'Duplicadas', 'Fotos BUENAS que perdieron contra una hermana mejor'],
              ]],
            ] as [string, [string, string, string][]][]).map(([groupTitle, rows]) => (
              <div key={groupTitle} style={{ marginBottom: '8px' }}>
                <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                  {groupTitle}
                </div>
                {rows.map(([label, name, hint]) => {
                  const r = ratings[label] || { stars: 0, color: '', flag: 'none' };
                  const selStyle = { padding: '3px 5px', borderRadius: '4px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--border-strong)' };
                  return (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                      <span style={{ flex: 1 }} title={hint}>
                        {name}
                        <div style={{ fontSize: '0.58rem', color: 'var(--text-muted)', lineHeight: 1.25 }}>{hint}</div>
                      </span>
                      <select value={r.stars ?? 0} style={selStyle}
                        onChange={(e) => handleRatingChange(label, 'stars', parseInt(e.target.value))}>
                        {[0, 1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}★</option>)}
                      </select>
                      <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                        {(['', 'Rojo', 'Amarillo', 'Verde', 'Azul', 'Morado'] as string[]).map(c => {
                          const hex: Record<string, string> = {
                            Rojo: '#e5484d', Amarillo: '#f0c000', Verde: '#46a758',
                            Azul: '#0091ff', Morado: '#8e4ec6'
                          };
                          const active = (r.color || '') === c;
                          return (
                            <div
                              key={c || 'none'}
                              title={c || 'Sin color'}
                              onClick={() => handleRatingChange(label, 'color', c)}
                              style={{
                                width: '14px', height: '14px', borderRadius: '50%',
                                cursor: 'pointer', boxSizing: 'border-box',
                                background: c
                                  ? hex[c]
                                  : 'linear-gradient(135deg, transparent 42%, #888 42%, #888 58%, transparent 58%)',
                                border: active ? '2px solid white' : '1px solid var(--border-strong)',
                                transform: active ? 'scale(1.2)' : 'none',
                              }}
                            />
                          );
                        })}
                      </div>
                      <select value={r.flag || 'none'} style={selStyle}
                        onChange={(e) => handleRatingChange(label, 'flag', e.target.value)}>
                        <option value="none">Sin banderín</option>
                        <option value="pick">⚑ Seleccionada</option>
                        <option value="reject">⚐ Rechazada</option>
                      </select>
                    </div>
                  );
                })}
              </div>
            ))}
            <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)' }}>
              El color debe coincidir exactamente con tu conjunto de etiquetas de Lightroom.
            </div>
          </div>

          {/* --- Pre-edición --- */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '10px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={preEdit.enabled !== false}
                onChange={(e) => handlePreEditChange('enabled', e.target.checked)}
                style={{ width: '13px', height: '13px' }}
              />
              <div>
                <div style={{ fontWeight: 500 }}>Pre-edición (preset + WB + exposición)</div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                  Escribe ajustes de revelado reversibles en el XMP de las fotos elegidas
                </div>
              </div>
            </label>

            {preEdit.enabled !== false && (
              <>
                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const f = e.dataTransfer.files?.[0] as any;
                    if (f?.path) usePresetFile(f.path);
                  }}
                  style={{ border: '1px dashed var(--border-strong)', borderRadius: '6px', padding: '8px', textAlign: 'center', fontSize: '0.7rem', color: 'var(--text-muted)' }}
                >
                  Arrastra aquí tu preset .xmp de Lightroom, o{' '}
                  <label style={{ color: 'var(--accent-primary)', cursor: 'pointer', textDecoration: 'underline' }}>
                    búscalo
                    <input
                      type="file"
                      accept=".xmp"
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        const f = e.target.files?.[0] as any;
                        if (f?.path) usePresetFile(f.path);
                        e.target.value = '';
                      }}
                    />
                  </label>
                  <div style={{ marginTop: '4px', fontSize: '0.62rem' }}>
                    Nota: las máscaras IA del preset pueden pedir "Actualizar ajustes de IA" en Lightroom
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontWeight: 500 }}>Preset activo</div>
                  <select
                    value={preEdit.preset_path || ''}
                    onChange={(e) => {
                      if (e.target.value === '') {
                        usePresetFile('');
                        handlePreEditChange('preset_path', '');
                      } else {
                        usePresetFile(e.target.value);
                      }
                    }}
                    style={{ padding: '4px 6px', borderRadius: '4px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--border-strong)', maxWidth: '260px' }}
                  >
                    <option value="">Ninguno (solo WB + exposición)</option>
                    {(preEdit.recent_presets || []).map((p: any) => (
                      <option key={p.path} value={p.path}>{p.name}</option>
                    ))}
                  </select>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontWeight: 500 }}>Sesgo de exposición</div>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                      Se suma a la exposición medida en las personas
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <input
                      type="range"
                      min={-0.5}
                      max={0.5}
                      step={0.05}
                      value={preEdit.exposure_bias ?? 0.3}
                      onChange={(e) => handlePreEditChange('exposure_bias', parseFloat(e.target.value))}
                    />
                    <span style={{ width: '48px', textAlign: 'right' }}>
                      {(preEdit.exposure_bias ?? 0.3) >= 0 ? '+' : ''}{(preEdit.exposure_bias ?? 0.3).toFixed(2)} EV
                    </span>
                  </div>
                </div>
              </>
            )}
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={prefs.overwrite_xmp_ratings === true}
              onChange={(e) => handlePrefChange('overwrite_xmp_ratings', e.target.checked)}
              style={{ width: '13px', height: '13px' }}
            />
            <div>
              <div style={{ fontWeight: 500 }}>Overwrite XMP Ratings</div>
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Cuidado: sobrescribe las estrellas que ya tengas en Lightroom</div>
            </div>
          </label>

          <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)', margin: '16px 0' }} />
          
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <div style={{ fontWeight: 600, fontSize: '0.8rem' }}>Administración de Caché e Historial</div>
            <button className="btn btn-secondary" onClick={handleOpenCacheFolder} style={{ padding: '4px 8px', fontSize: '0.65rem' }}>
              Abrir Carpeta de Caché
            </button>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '150px', overflowY: 'auto' }}>
            {cachedProjects.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>No hay proyectos en caché.</div>
            ) : (
              cachedProjects.map((proj) => (
                <div key={proj.directory} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px', backgroundColor: 'var(--bg-tertiary)', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, marginRight: '8px' }}>
                    <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis' }} title={proj.directory}>
                      {proj.directory.split(/[/\\]/).pop() || proj.directory}
                    </div>
                    <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)' }}>
                      {new Date(proj.last_accessed * 1000).toLocaleDateString()} • {proj.size_mb} MB
                    </div>
                  </div>
                  <button 
                    onClick={() => handleClearCache(proj.directory)}
                    style={{ background: 'transparent', border: '1px solid var(--status-error-border)', color: 'var(--status-error-text)', borderRadius: '4px', padding: '4px 8px', cursor: 'pointer', fontSize: '0.65rem' }}
                  >
                    Eliminar
                  </button>
                </div>
              ))
            )}
          </div>

        </div>

        {/* Footer */}
        <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'flex-end', gap: '12px', backgroundColor: 'var(--bg-primary)', borderBottomLeftRadius: '12px', borderBottomRightRadius: '12px' }}>
          <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
          <button className="btn btn-primary" onClick={handleSave}>Guardar preferencias</button>
        </div>
        
      </div>
    </div>
  );
}
