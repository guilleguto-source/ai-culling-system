import React, { useState, useEffect } from 'react';

const API = 'http://127.0.0.1:8000';

const fmt = (n: number) => n.toLocaleString('es');

/**
 * Panel "Tu estilo": lo que la IA aprendió de ESTE fotógrafo.
 *
 * Sustituye al indicador de "Backend Engine", que hablaba de infraestructura
 * donde debe estar el diferencial del producto. Solo muestra cifras reales:
 * si un dato no existe (p.ej. sin historial), esa fila no aparece.
 */
export default function LearningPanel({ active }: { active: boolean }) {
  const [d, setD] = useState<any>(null);

  useEffect(() => {
    if (!active) return;
    (async () => {
      try {
        const r = await fetch(`${API}/learning/summary`);
        if (r.ok) setD(await r.json());
      } catch { /* backend caído: el estado ya se muestra aparte */ }
    })();
  }, [active]);

  if (!d) return null;

  const filas: [string, string][] = [];
  if (d.seleccionadas_aprendidas)
    filas.push(['Tus elecciones', fmt(d.seleccionadas_aprendidas)]);
  if (d.decisiones_gusto)
    filas.push(['Decisiones aprendidas', fmt(d.decisiones_gusto)]);
  if (d.escenas)
    filas.push(['Escenas descubiertas', String(d.escenas)]);
  if (d.recorte_habitual_pct)
    filas.push(['Tu recorte habitual', `${d.recorte_habitual_pct}% del cuadro`]);
  if (d.caras_calibradas)
    filas.push(['Rostros calibrados', fmt(d.caras_calibradas)]);

  if (filas.length === 0) return null;

  return (
    <div className="glass-panel" style={{ padding: '12px 14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '10px' }}>
        <span style={{ fontSize: '0.95rem' }}>🧠</span>
        <strong style={{ fontSize: '0.85rem' }}>Tu estilo</strong>
      </div>

      {filas.map(([etiqueta, valor]) => (
        <div key={etiqueta} className="flex-between" style={{ fontSize: '0.75rem', padding: '3px 0' }}>
          <span style={{ color: 'var(--text-muted)' }}>{etiqueta}</span>
          <strong style={{ color: 'var(--text-primary)' }}>{valor}</strong>
        </div>
      ))}

      {d.reconocimiento_personas && (
        <div style={{ fontSize: '0.7rem', color: 'var(--status-selected-text)', marginTop: '8px' }}>
          ✔ Reconocimiento de personas activo
        </div>
      )}
      {d.eventos_pendientes_sync > 0 && (
        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '6px' }}>
          {d.eventos_pendientes_sync} evento(s) sin sincronizar
        </div>
      )}
    </div>
  );
}
