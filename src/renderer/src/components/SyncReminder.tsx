import React, { useState, useEffect, useCallback } from 'react';

const API = 'http://127.0.0.1:8000';

interface Evento {
  directory: string;
  folder_name: string;
  exported_at: string;
  last_synced_at: string;
  _status?: 'pending' | 'done';
  _msg?: string;
}

/**
 * Recordatorio al abrir la app: eventos culleados que faltan sincronizar con
 * Lightroom. Cada uno se puede sincronizar en el momento, posponer 8 h (vuelve
 * a recordar la próxima vez que se abra la app) o descartar ("ya terminé").
 */
export default function SyncReminder({ active }: { active: boolean }) {
  const [eventos, setEventos] = useState<Evento[]>([]);
  const [busy, setBusy] = useState<string>('');

  const cargar = useCallback(async () => {
    try {
      const r = await fetch(`${API}/sync/pending`);
      if (r.ok) setEventos((await r.json()).events || []);
    } catch { /* backend caído: no bloquea la app */ }
  }, []);

  // Al abrir la app (backend arriba). Solo una vez por arranque.
  useEffect(() => { if (active) cargar(); }, [active, cargar]);

  const quitar = (dir: string) => setEventos(evs => evs.filter(e => e.directory !== dir));

  const sincronizar = async (ev: Evento) => {
    setBusy(ev.directory);
    try {
      const r = await fetch(`${API}/reimport_xmp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory: ev.directory }),
      });
      const d = await r.json();
      const guardadas = d.estilo_aprendido?.guardadas || 0;
      const estilo = guardadas ? ` · ${guardadas} ediciones aprendidas` : '';
      const msg = !r.ok
        ? (d.detail || 'Error al sincronizar')
        : d.corrections === 0 && !guardadas
          ? (d.hint || 'Sin cambios nuevos en Lightroom')
          : `${d.corrections} correcciones (↑${d.upgraded} ↓${d.downgraded})` +
            (d.embeddings_available ? ` · ${d.total_examples} ejemplos aprendidos` : '') + estilo;
      setEventos(evs => evs.map(e =>
        e.directory === ev.directory ? { ...e, _status: 'done', _msg: msg } : e));
    } catch {
      setEventos(evs => evs.map(e =>
        e.directory === ev.directory ? { ...e, _status: 'done', _msg: 'Error de conexión con el backend' } : e));
    } finally {
      setBusy('');
    }
  };

  const posponer = async (ev: Evento) => {
    try {
      await fetch(`${API}/sync/snooze`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory: ev.directory, hours: 8 }),
      });
    } catch { /* si falla, igual lo ocultamos esta sesión */ }
    quitar(ev.directory);
  };

  const terminar = async (ev: Evento) => {
    try {
      await fetch(`${API}/sync/dismiss`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory: ev.directory }),
      });
    } catch { /* idem */ }
    quitar(ev.directory);
  };

  if (eventos.length === 0) return null;

  return (
    <div style={{
      backgroundColor: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--border-subtle)',
      padding: '8px 16px', display: 'flex', flexDirection: 'column', gap: '6px',
    }}>
      {eventos.map(ev => (
        <div key={ev.directory} style={{
          display: 'flex', alignItems: 'center', gap: '12px', fontSize: '0.85rem',
        }}>
          <span style={{ fontSize: '1rem' }}>🔄</span>
          {ev._status === 'done' ? (
            <>
              <span style={{ flex: 1, color: 'var(--text-secondary)' }}>
                <strong style={{ color: 'var(--text-primary)' }}>{ev.folder_name}</strong> — {ev._msg}
              </span>
              <button className="btn btn-secondary" style={btnMini} onClick={() => quitar(ev.directory)}>
                Cerrar
              </button>
            </>
          ) : (
            <>
              <span style={{ flex: 1, color: 'var(--text-secondary)' }}>
                <strong style={{ color: 'var(--text-primary)' }}>{ev.folder_name}</strong>
                {' — culleada, falta sincronizar tus cambios de Lightroom.'}
                {ev.last_synced_at && (
                  <span style={{ color: 'var(--text-muted)' }}>
                    {' '}(último sync {new Date(ev.last_synced_at).toLocaleString()})
                  </span>
                )}
              </span>
              <button className="btn btn-primary" style={btnMini}
                disabled={busy === ev.directory} onClick={() => sincronizar(ev)}>
                {busy === ev.directory ? 'Sincronizando…' : 'Sincronizar ahora'}
              </button>
              <button className="btn btn-secondary" style={btnMini}
                title="Volver a recordar la próxima vez que abras la app (en ~8 h)"
                onClick={() => posponer(ev)}>
                Recordar en 8 h
              </button>
              <button className="btn btn-secondary" style={btnMini}
                title="No volver a recordar este evento" onClick={() => terminar(ev)}>
                Ya terminé
              </button>
            </>
          )}
        </div>
      ))}
    </div>
  );
}

const btnMini: React.CSSProperties = { fontSize: '0.78rem', padding: '4px 10px' };
