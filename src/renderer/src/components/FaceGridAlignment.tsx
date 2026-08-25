import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';

interface FaceCrop {
  person_id: string;
  photo_path: string;
  face_index: number;
  face_bbox: [number, number, number, number];
  is_representative: boolean;
  score: number;
  is_eyes_open: boolean;
  is_smiling: boolean;
  is_looking_at_camera: boolean;
  blur_score: number;
}

interface PersonGroup {
  person_id: string;
  crops: FaceCrop[];
}

interface FaceGridProps {
  clusterId: number;
  selectedPhotoPath: string;
  onSelectPhoto: (photoPath: string) => void;
}

export default function FaceGridAlignment({ clusterId, selectedPhotoPath, onSelectPhoto }: FaceGridProps) {
  const [people, setPeople] = useState<PersonGroup[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const fetchCrops = async () => {
      setLoading(true);
      try {
        const data = await apiClient.getBurstFaceCrops(clusterId);
        if (active) setPeople(data.people || []);
      } catch (err) {
        console.error('Error fetching face crops:', err);
      } finally {
        if (active) setLoading(false);
      }
    };
    fetchCrops();
    return () => { active = false; };
  }, [clusterId]);

  if (loading) {
    return (
      <div style={{ padding: '8px 12px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
        Cargando alineación de rostros...
      </div>
    );
  }

  if (people.length === 0) {
    return null;
  }

  return (
    <div
      className="glass-panel"
      style={{
        padding: '10px 14px',
        borderRadius: '8px',
        border: '1px solid var(--border-subtle)',
        background: 'rgba(18, 18, 22, 0.85)',
        backdropFilter: 'blur(10px)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--accent-primary)' }}>
          🔍 Alineación de Rostros por Sujeto (Haz clic en una cara para elegir la foto)
        </span>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
          {people.length} sujeto(s) detectado(s)
        </span>
      </div>

      {/* Disposición Horizontal lado a lado */}
      <div style={{ display: 'flex', gap: '20px', overflowX: 'auto', paddingBottom: '6px' }}>
        {people.map((person, pIdx) => (
          <div
            key={person.person_id || pIdx}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
              backgroundColor: 'rgba(255, 255, 255, 0.03)',
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid rgba(255, 255, 255, 0.06)',
              flexShrink: 0,
            }}
          >
            <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
              Sujeto {pIdx + 1}
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              {person.crops.map((crop, cIdx) => {
                const isCurrent = crop.photo_path === selectedPhotoPath;
                const [x, y, w, h] = crop.face_bbox;
                const imgUrl = apiClient.getFaceCropUrl(crop.photo_path, [x, y, w, h], 260);

                return (
                  <div
                    key={`${crop.photo_path}-${cIdx}`}
                    onClick={() => onSelectPhoto(crop.photo_path)}
                    style={{
                      position: 'relative',
                      width: '120px',
                      height: '120px',
                      borderRadius: '8px',
                      overflow: 'hidden',
                      cursor: 'pointer',
                      border: isCurrent
                        ? '2px solid var(--accent-primary)'
                        : '1px solid var(--border-subtle)',
                      boxShadow: isCurrent ? '0 0 12px rgba(79, 138, 247, 0.6)' : 'none',
                      transition: 'transform 0.15s ease',
                      flexShrink: 0,
                    }}
                    title={`Click para elegir foto. Ojos: ${crop.is_eyes_open ? 'Abiertos' : 'Cerrados'}`}
                  >
                    <img
                      src={imgUrl}
                      alt="Rostro"
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      loading="lazy"
                    />

                    {/* Badges de estado en el micro-crop */}
                    <div
                      style={{
                        position: 'absolute',
                        bottom: '2px',
                        left: '2px',
                        right: '2px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        background: 'rgba(0, 0, 0, 0.75)',
                        padding: '2px 4px',
                        borderRadius: '3px',
                        fontSize: '0.68rem',
                      }}
                    >
                      <span>{crop.is_eyes_open ? '👁️' : '❌'}</span>
                      {crop.is_smiling && <span>😊</span>}
                      <span style={{ color: crop.blur_score > 200 ? '#4ade80' : '#f87171', fontWeight: 600 }}>
                        {Math.round(crop.blur_score)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
