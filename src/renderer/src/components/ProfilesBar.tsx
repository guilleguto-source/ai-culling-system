import React, { useState, useEffect } from 'react';

const API = 'http://127.0.0.1:8000';

/**
 * Perfiles de workflow: bodas, infantil, corporativo…
 *
 * Un perfil empaqueta las preferencias de TRABAJO (selectividad, recorte,
 * detectores, pre-edición). No incluye el mapeo a estrellas/colores de
 * Lightroom: eso es del fotógrafo, no del tipo de evento.
 */
export default function ProfilesBar() {
  const [perfiles, setPerfiles] = useState<string[]>([]);
  const [msg, setMsg] = useState('');
  const [ocupado, setOcupado] = useState(false);

  const cargar = async () => {
    try {
      const r = await fetch(`${API}/profiles`);
      if (r.ok) setPerfiles((await r.json()).perfiles || []);
    } catch { /* backend caído */ }
  };
  useEffect(() => { cargar(); }, []);

  const llamar = async (ruta: string, nombre: string, exito: string) => {
    setOcupado(true);
    try {
      const r = await fetch(`${API}/profiles/${ruta}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre }),
      });
      const d = await r.json();
      setMsg(r.ok ? exito : (d.detail || 'No se pudo completar'));
      await cargar();
    } catch {
      setMsg('Error de conexión');
    } finally {
      setOcupado(false);
    }
  };

  const guardar = () => {
    const nombre = window.prompt('Nombre del perfil (p. ej. "Bodas", "Infantil"):');
    if (nombre?.trim()) llamar('save', nombre.trim(), `Perfil "${nombre.trim()}" guardado`);
  };

  const aplicar = (nombre: string) => {
    if (!nombre) return;
    llamar('apply', nombre, `Perfil "${nombre}" aplicado — reabrí Ajustes para verlo`);
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
