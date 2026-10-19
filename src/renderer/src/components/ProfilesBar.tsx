import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { Button } from './ui/Button';

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
    <div
      style={{
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-sm)',
        backgroundColor: 'var(--color-surface-elevated)',
        padding: '12px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3)'
      }}
    >
      <div className="flex-between">
        <div>
          <div style={{ fontWeight: 'var(--fw-medium)', fontSize: 'var(--text-xs)', color: 'var(--text-primary)' }}>
            Perfiles de workflow
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
            Guarda esta configuración con un nombre y reutilízala por tipo de evento
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={guardar} disabled={ocupado}>
          Guardar actual
        </Button>
      </div>

      {perfiles.length > 0 && (
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          {perfiles.map(p => (
            <Button
              key={p}
              variant="secondary"
              size="sm"
              onClick={() => aplicar(p)}
              disabled={ocupado}
              title="Aplicar este perfil a las preferencias actuales"
            >
              {p}
            </Button>
          ))}
        </div>
      )}

      {msg && (
        <div style={{ fontSize: '11px', color: 'var(--accent-primary)', fontFamily: 'var(--font-mono)' }}>
          {msg}
        </div>
      )}
    </div>
  );
}
