import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';

/**
 * Perfiles de workflow: bodas, infantil, corporativo…
 */
export default function ProfilesBar() {
  const [perfiles, setPerfiles] = useState<string[]>([]);
  const [msg, setMsg] = useState('');
  const [ocupado, setOcupado] = useState(false);

  const cargar = async () => {
    try {
      const data = await apiClient.getProfiles();
      setPerfiles(data.perfiles || []);
    } catch { /* backend caído */ }
  };
  useEffect(() => { cargar(); }, []);

  const guardar = async () => {
    const nombre = window.prompt('Nombre del perfil (p. ej. "Bodas", "Infantil"):');
    if (!nombre?.trim()) return;
    setOcupado(true);
    try {
      await apiClient.saveProfile(nombre.trim());
      setMsg(`Perfil "${nombre.trim()}" guardado`);
      await cargar();
    } catch (e: any) {
      setMsg(e.message || 'Error guardando perfil');
    } finally {
      setOcupado(false);
    }
  };

  const aplicar = async (nombre: string) => {
    if (!nombre) return;
    setOcupado(true);
    try {
      await apiClient.applyProfile(nombre);
      setMsg(`Perfil "${nombre}" aplicado — reabrí Ajustes para verlo`);
      await cargar();
    } catch (e: any) {
      setMsg(e.message || 'Error aplicando perfil');
    } finally {
      setOcupado(false);
    }
  };

  return (
    <div style={{
      border: '1px solid var(--border-subtle)', borderRadius: '6px',
      padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: '8px',
    }}>
      <div className="flex-between">
        <div>
          <div style={{ fontWeight: 500 }}>Perfiles de workflow</div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
            Guarda esta configuración con un nombre y reutilízala por tipo de evento
          </div>
        </div>
        <button className="btn btn-secondary" style={{ padding: '4px 10px' }}
          onClick={guardar} disabled={ocupado}>
          Guardar actual
        </button>
      </div>

      {perfiles.length > 0 && (
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {perfiles.map(p => (
            <button key={p} className="btn btn-secondary"
              style={{ padding: '4px 10px' }}
              onClick={() => aplicar(p)} disabled={ocupado}
              title="Aplicar este perfil a las preferencias actuales">
              {p}
            </button>
          ))}
        </div>
      )}

      {msg && <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>{msg}</div>}
    </div>
  );
}
