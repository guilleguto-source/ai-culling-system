import React, { useState } from 'react';

interface SettingsModalProps {
  settings: any;
  onClose: () => void;
  onSave: (newSettings: any) => void;
}

export default function SettingsModal({ settings, onClose, onSave }: SettingsModalProps) {
  // Use a local copy of settings for editing
  const [localSettings, setLocalSettings] = useState(() => JSON.parse(JSON.stringify(settings || {})));

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
      if (!window.confirm('¿Marcar las fotos Trash como RECHAZADAS (banderín negro) en Lightroom?')) {
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
      <div className="glass-panel" style={{ width: '500px', backgroundColor: 'var(--bg-secondary)', padding: '0' }}>
        
        {/* Header */}
        <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontSize: '1.2rem' }}>Culling Preferences</h2>
          <button 
            onClick={onClose} 
            style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '1.2rem' }}
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 500 }}>Selectivity Target</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>How aggressively should the AI cull?</div>
            </div>
            <select 
              value={prefs.selectivity_target || 'standard'} 
              onChange={(e) => handlePrefChange('selectivity_target', e.target.value)}
              style={{ padding: '8px', borderRadius: '4px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--border-strong)' }}
            >
              <option value="few">Few (Aggressive)</option>
              <option value="standard">Standard</option>
              <option value="more">More (Lenient)</option>
            </select>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 500 }}>Blurry Sensitivity</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Tolerance for out of focus shots</div>
            </div>
            <select 
              value={prefs.blurry_sensitivity || 'moderate'} 
              onChange={(e) => handlePrefChange('blurry_sensitivity', e.target.value)}
              style={{ padding: '8px', borderRadius: '4px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--border-strong)' }}
            >
              <option value="lenient">Lenient</option>
              <option value="moderate">Moderate</option>
              <option value="strict">Strict</option>
            </select>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 500 }}>Auto-encuadre</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Recorte propuesto (reversible en Lightroom). Grupos: solo nivelado.</div>
            </div>
            <select
              value={prefs.auto_crop || 'minimo'}
              onChange={(e) => handlePrefChange('auto_crop', e.target.value)}
              style={{ padding: '8px', borderRadius: '4px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--border-strong)' }}
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
              style={{ width: '16px', height: '16px' }}
            />
            <div>
              <div style={{ fontWeight: 500 }}>Detect Duplicates</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Group similar photos and select the best</div>
            </div>
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
            <input 
              type="checkbox" 
              checked={prefs.detect_closed_eyes !== false} 
              onChange={(e) => handlePrefChange('detect_closed_eyes', e.target.checked)}
              style={{ width: '16px', height: '16px' }}
            />
            <div>
              <div style={{ fontWeight: 500 }}>Detect Closed Eyes</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Flag portraits with closed eyes</div>
            </div>
          </label>
          
          {/* --- Calificación de estrellas, colores y banderines --- */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '16px' }}>
            <div style={{ fontWeight: 600, marginBottom: '12px' }}>Calificación de estrellas y colores</div>
            {([
              ['Selecciones de IA', [
                ['selected', 'Seleccionadas'],
                ['highlighted', 'Destacadas'],
              ]],
              ['Para revisión', [
                ['blurry', 'Borrosas'],
                ['closed_eyes', 'Ojos cerrados'],
                ['duplicates', 'Trash'],
              ]],
            ] as [string, [string, string][]][]).map(([groupTitle, rows]) => (
              <div key={groupTitle} style={{ marginBottom: '12px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                  {groupTitle}
                </div>
                {rows.map(([label, name]) => {
                  const r = ratings[label] || { stars: 0, color: '', flag: 'none' };
                  const selStyle = { padding: '6px', borderRadius: '4px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--border-strong)' };
                  return (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                      <span style={{ flex: 1 }}>{name}</span>
                      <select value={r.stars ?? 0} style={selStyle}
                        onChange={(e) => handleRatingChange(label, 'stars', parseInt(e.target.value))}>
                        {[0, 1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}★</option>)}
                      </select>
                      <select value={r.color || ''} style={selStyle}
                        onChange={(e) => handleRatingChange(label, 'color', e.target.value)}>
                        <option value="">Sin color</option>
                        {['Roja', 'Amarilla', 'Verde', 'Azul', 'Morada'].map(c =>
                          <option key={c} value={c}>{c}</option>)}
                      </select>
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
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              El color debe coincidir exactamente con tu conjunto de etiquetas de Lightroom.
            </div>
          </div>

          {/* --- Pre-edición --- */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={preEdit.enabled !== false}
                onChange={(e) => handlePreEditChange('enabled', e.target.checked)}
                style={{ width: '16px', height: '16px' }}
              />
              <div>
                <div style={{ fontWeight: 500 }}>Pre-edición (preset + WB + exposición)</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
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
                  style={{ border: '1px dashed var(--border-strong)', borderRadius: '6px', padding: '12px', textAlign: 'center', fontSize: '0.85rem', color: 'var(--text-muted)' }}
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
                  <div style={{ marginTop: '4px', fontSize: '0.75rem' }}>
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
                    style={{ padding: '8px', borderRadius: '4px', background: 'var(--bg-tertiary)', color: 'white', border: '1px solid var(--border-strong)', maxWidth: '260px' }}
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
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
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
              style={{ width: '16px', height: '16px' }}
            />
            <div>
              <div style={{ fontWeight: 500 }}>Overwrite XMP Ratings</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Warning: This will overwrite existing Lightroom ratings</div>
            </div>
          </label>

        </div>

        {/* Footer */}
        <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'flex-end', gap: '12px', backgroundColor: 'var(--bg-primary)', borderBottomLeftRadius: '12px', borderBottomRightRadius: '12px' }}>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSave}>Save Preferences</button>
        </div>
        
      </div>
    </div>
  );
}
