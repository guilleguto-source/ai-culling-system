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
