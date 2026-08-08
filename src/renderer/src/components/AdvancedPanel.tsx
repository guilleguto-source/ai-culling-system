import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { LutProfile, LutStatusResponse } from '../types/api';

interface AdvancedPanelProps {
  isOpen: boolean;
  onClose: () => void;
  selectedPhotoPath?: string;
  onRefreshResults?: () => void;
}

export const AdvancedPanel: React.FC<AdvancedPanelProps> = ({
  isOpen,
  onClose,
  selectedPhotoPath,
  onRefreshResults
}) => {
  const [lutStatus, setLutStatus] = useState<LutStatusResponse | null>(null);
  const [luts, setLuts] = useState<LutProfile[]>([]);
  const [selectedLut, setSelectedLut] = useState<string>('warm_golden');
  const [lutStrength, setLutStrength] = useState<number>(0.8);

  const [relightIntensity, setRelightIntensity] = useState<number>(0.5);
  const [skinSmoothness, setSkinSmoothness] = useState<number>(0.5);

  const [isApplying, setIsApplying] = useState<string | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen]);

  const loadData = async () => {
    try {
      const [statusRes, lutsRes] = await Promise.all([
        apiClient.getLutStatus(),
        apiClient.getLuts()
      ]);
      setLutStatus(statusRes);
      setLuts(lutsRes.luts || []);
      if (statusRes.current_config?.fallback_lut) {
        setSelectedLut(statusRes.current_config.fallback_lut);
      }
      if (statusRes.current_config?.strength !== undefined) {
        setLutStrength(statusRes.current_config.strength);
      }
    } catch (err: any) {
      console.error('Error cargando estado de LUTs:', err);
    }
  };

  const showToast = (type: 'success' | 'error', text: string) => {
    setFeedbackMessage({ type, text });
    setTimeout(() => setFeedbackMessage(null), 4000);
  };

  const handleApplyLut = async (allSelected: boolean) => {
    setIsApplying('lut');
    try {
      const paths = !allSelected && selectedPhotoPath ? [selectedPhotoPath] : undefined;
      const res = await apiClient.applyLut({
        lut_id: selectedLut,
        strength: lutStrength,
        image_paths: paths
      });
      showToast('success', `Color Grading aplicado a ${res.applied_count} foto(s).`);
      onRefreshResults?.();
    } catch (err: any) {
      showToast('error', `Error al aplicar LUT: ${err.message || err}`);
    } finally {
      setIsApplying(null);
    }
  };

  const handleApplyRelight = async (allSelected: boolean) => {
    setIsApplying('relight');
    try {
      const paths = !allSelected && selectedPhotoPath ? [selectedPhotoPath] : undefined;
      const res = await apiClient.relightFaces({
        intensity: relightIntensity,
        image_paths: paths
      });
      showToast('success', `Re-iluminación aplicada a ${res.applied_count} foto(s) con rostros.`);
      onRefreshResults?.();
    } catch (err: any) {
      showToast('error', `Error al re-iluminar: ${err.message || err}`);
    } finally {
      setIsApplying(null);
    }
  };

  const handleApplySkin = async (allSelected: boolean) => {
    setIsApplying('skin');
    try {
      const paths = !allSelected && selectedPhotoPath ? [selectedPhotoPath] : undefined;
      const res = await apiClient.skinRetouch({
        smoothness: skinSmoothness,
        image_paths: paths
      });
      showToast('success', `Retoque de piel aplicado a ${res.applied_count} foto(s).`);
      onRefreshResults?.();
    } catch (err: any) {
      showToast('error', `Error al retocar piel: ${err.message || err}`);
    } finally {
      setIsApplying(null);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(6px)',
        zIndex: 1050,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}
      onClick={e => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          width: '560px',
          maxWidth: '92vw',
          maxHeight: '88vh',
          backgroundColor: '#18181b',
          borderRadius: '12px',
          border: '1px solid #27272a',
          boxShadow: '0 20px 40px rgba(0,0,0,0.6)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          color: '#e4e4e7'
        }}
      >
        {/* Cabecera */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid #27272a',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600, color: '#f4f4f5' }}>
              Revelado Avanzado & Retoque
            </h2>
            <p style={{ margin: '4px 0 0 0', fontSize: '0.75rem', color: '#a1a1aa' }}>
              Módulos optativos post-culling. Ajustes no destructivos guardados en XMP.
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#a1a1aa',
              fontSize: '1.2rem',
              cursor: 'pointer',
              padding: '4px 8px'
            }}
          >
            ✕
          </button>
        </div>

        {/* Feedback Toast */}
        {feedbackMessage && (
          <div
            style={{
              padding: '10px 20px',
              backgroundColor: feedbackMessage.type === 'success' ? '#064e3b' : '#7f1d1d',
              color: feedbackMessage.type === 'success' ? '#a7f3d0' : '#fecaca',
              fontSize: '0.8rem',
              borderBottom: '1px solid rgba(255,255,255,0.1)'
            }}
          >
            {feedbackMessage.text}
          </div>
        )}

        {/* Contenido con scroll */}
        <div
          style={{
            padding: '20px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '20px'
          }}
        >
          {/* MÓDULO 1: Neural 3D-LUT & Color Grading */}
          <div
            style={{
              backgroundColor: '#27272a',
              borderRadius: '8px',
              padding: '16px',
              border: '1px solid #3f3f46'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.9rem', color: '#38bdf8' }}>
                Neural 3D-LUT (Look de Color)
              </span>
              {lutStatus && (
                <span
                  style={{
                    fontSize: '0.7rem',
                    padding: '2px 8px',
                    borderRadius: '10px',
                    backgroundColor: lutStatus.total_learned_scenes > 0 ? '#14532d' : '#3f3f46',
                    color: lutStatus.total_learned_scenes > 0 ? '#86efac' : '#d4d4d8'
                  }}
                >
                  {lutStatus.total_learned_scenes > 0
                    ? `${lutStatus.total_learned_scenes} escenas aprendidas`
                    : 'Usando perfiles base'}
                </span>
              )}
            </div>
            <p style={{ margin: '0 0 12px 0', fontSize: '0.75rem', color: '#a1a1aa' }}>
              Aplica un look de color adaptado a la escena, respetando el preset base y rescatando tonos de piel.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label style={{ fontSize: '0.78rem', color: '#d4d4d8' }}>Perfil / Estilo:</label>
                <select
                  value={selectedLut}
                  onChange={e => setSelectedLut(e.target.value)}
                  style={{
                    backgroundColor: '#18181b',
                    color: '#f4f4f5',
                    border: '1px solid #52525b',
                    borderRadius: '6px',
                    padding: '6px 10px',
                    fontSize: '0.78rem',
                    width: '220px'
                  }}
                >
                  {luts.map(l => (
                    <option key={l.id} value={l.id}>
                      {l.display_name}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label style={{ fontSize: '0.78rem', color: '#d4d4d8' }}>Intensidad:</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <input
                    type="range"
                    min="0.1"
                    max="1.0"
                    step="0.05"
                    value={lutStrength}
                    onChange={e => setLutStrength(parseFloat(e.target.value))}
                    style={{ width: '130px', accentColor: '#38bdf8' }}
                  />
                  <span style={{ fontSize: '0.78rem', width: '40px', textAlign: 'right' }}>
                    {Math.round(lutStrength * 100)}%
                  </span>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
                <button
                  disabled={isApplying !== null}
                  onClick={() => handleApplyLut(true)}
                  style={{
                    flex: 1,
                    padding: '8px 12px',
                    backgroundColor: '#0284c7',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#ffffff',
                    fontWeight: 500,
                    fontSize: '0.78rem',
                    cursor: isApplying ? 'not-allowed' : 'pointer'
                  }}
                >
                  {isApplying === 'lut' ? 'Aplicando...' : 'Aplicar a Seleccionadas'}
                </button>
                {selectedPhotoPath && (
                  <button
                    disabled={isApplying !== null}
                    onClick={() => handleApplyLut(false)}
                    style={{
                      padding: '8px 12px',
                      backgroundColor: '#3f3f46',
                      border: 'none',
                      borderRadius: '6px',
                      color: '#ffffff',
                      fontSize: '0.78rem',
                      cursor: isApplying ? 'not-allowed' : 'pointer'
                    }}
                  >
                    Solo esta foto
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* MÓDULO 2: Re-iluminación Facial */}
          <div
            style={{
              backgroundColor: '#27272a',
              borderRadius: '8px',
              padding: '16px',
              border: '1px solid #3f3f46'
            }}
          >
            <span style={{ fontWeight: 600, fontSize: '0.9rem', color: '#f59e0b', display: 'block', marginBottom: '8px' }}>
              Re-iluminación Facial (Portrait Relighting)
            </span>
            <p style={{ margin: '0 0 12px 0', fontSize: '0.75rem', color: '#a1a1aa' }}>
              Realza sutilmente las sombras y exposición sobre los rostros sin quemar el fondo.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label style={{ fontSize: '0.78rem', color: '#d4d4d8' }}>Intensidad del realce:</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <input
                    type="range"
                    min="0.1"
                    max="1.0"
                    step="0.05"
                    value={relightIntensity}
                    onChange={e => setRelightIntensity(parseFloat(e.target.value))}
                    style={{ width: '130px', accentColor: '#f59e0b' }}
                  />
                  <span style={{ fontSize: '0.78rem', width: '40px', textAlign: 'right' }}>
                    {Math.round(relightIntensity * 100)}%
                  </span>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
                <button
                  disabled={isApplying !== null}
                  onClick={() => handleApplyRelight(true)}
                  style={{
                    flex: 1,
                    padding: '8px 12px',
                    backgroundColor: '#d97706',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#ffffff',
                    fontWeight: 500,
                    fontSize: '0.78rem',
                    cursor: isApplying ? 'not-allowed' : 'pointer'
                  }}
                >
                  {isApplying === 'relight' ? 'Procesando...' : 'Re-iluminar Seleccionadas'}
                </button>
                {selectedPhotoPath && (
                  <button
                    disabled={isApplying !== null}
                    onClick={() => handleApplyRelight(false)}
                    style={{
                      padding: '8px 12px',
                      backgroundColor: '#3f3f46',
                      border: 'none',
                      borderRadius: '6px',
                      color: '#ffffff',
                      fontSize: '0.78rem',
                      cursor: isApplying ? 'not-allowed' : 'pointer'
                    }}
                  >
                    Solo esta foto
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* MÓDULO 3: Retoque de Piel */}
          <div
            style={{
              backgroundColor: '#27272a',
              borderRadius: '8px',
              padding: '16px',
              border: '1px solid #3f3f46'
            }}
          >
            <span style={{ fontWeight: 600, fontSize: '0.9rem', color: '#ec4899', display: 'block', marginBottom: '8px' }}>
              Retoque de Piel Suave (Skin Retouch)
            </span>
            <p style={{ margin: '0 0 12px 0', fontSize: '0.75rem', color: '#a1a1aa' }}>
              Micro-suavizado paramétrico no destructivo que preserva los detalles naturales de los poros.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label style={{ fontSize: '0.78rem', color: '#d4d4d8' }}>Suavidad:</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <input
                    type="range"
                    min="0.1"
                    max="1.0"
                    step="0.05"
                    value={skinSmoothness}
                    onChange={e => setSkinSmoothness(parseFloat(e.target.value))}
                    style={{ width: '130px', accentColor: '#ec4899' }}
                  />
                  <span style={{ fontSize: '0.78rem', width: '40px', textAlign: 'right' }}>
                    {Math.round(skinSmoothness * 100)}%
                  </span>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
                <button
                  disabled={isApplying !== null}
                  onClick={() => handleApplySkin(true)}
                  style={{
                    flex: 1,
                    padding: '8px 12px',
                    backgroundColor: '#db2777',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#ffffff',
                    fontWeight: 500,
                    fontSize: '0.78rem',
                    cursor: isApplying ? 'not-allowed' : 'pointer'
                  }}
                >
                  {isApplying === 'skin' ? 'Procesando...' : 'Retocar Seleccionadas'}
                </button>
                {selectedPhotoPath && (
                  <button
                    disabled={isApplying !== null}
                    onClick={() => handleApplySkin(false)}
                    style={{
                      padding: '8px 12px',
                      backgroundColor: '#3f3f46',
                      border: 'none',
                      borderRadius: '6px',
                      color: '#ffffff',
                      fontSize: '0.78rem',
                      cursor: isApplying ? 'not-allowed' : 'pointer'
                    }}
                  >
                    Solo esta foto
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '12px 20px',
            borderTop: '1px solid #27272a',
            display: 'flex',
            justifyContent: 'flex-end'
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '6px 16px',
              backgroundColor: '#3f3f46',
              border: 'none',
              borderRadius: '6px',
              color: '#ffffff',
              fontSize: '0.8rem',
              cursor: 'pointer'
            }}
          >
            Cerrar
          </button>
        </div>
      </div>
    </div>
  );
};
