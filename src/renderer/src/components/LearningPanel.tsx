import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';

const fmt = (n: number) => n.toLocaleString('es');

/**
 * Panel "Tu estilo": lo que la IA aprendió de ESTE fotógrafo.
 */
export default function LearningPanel({ active }: { active: boolean }) {
  const [d, setD] = useState<any>(null);

  useEffect(() => {
    if (!active) return;
    (async () => {
      try {
        const data = await apiClient.getLearningSummary();
        setD(data);
      } catch { }
    })();
  }, [active]);

  if (!d) return null;

  const filas: [string, string][] = [];
  if (d.fotos_analizadas_ia)
    filas.push(['Fotos analizadas (Fase Q)', fmt(d.fotos_analizadas_ia)]);
  if (d.vectores_estilo)
    filas.push(['Vectores CLIP (Estilo)', fmt(d.vectores_estilo)]);
  if (d.seleccionadas_aprendidas)
    filas.push(['Tus elecciones', fmt(d.seleccionadas_aprendidas)]);
  if (d.decisiones_gusto)
    filas.push(['Decisiones aprendidas', fmt(d.decisiones_gusto)]);
  if (d.escenas)
    filas.push(['Escenas descubiertas', String(d.escenas)]);
  if (d.caras_calibradas)
    filas.push(['Rostros calibrados', fmt(d.caras_calibradas)]);

  if (filas.length === 0) return null;

  const madurez = Math.min(100, Math.max(5, (d.decisiones_gusto || d.seleccionadas_aprendidas || 0) / 50));

  return (
    <div style={{
      backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-lg)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{
          width: '36px', height: '36px', borderRadius: '50%', background: 'linear-gradient(135deg, var(--accent-amber), var(--accent-active))',
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--bg-deep)', fontSize: '1.2rem', fontWeight: 'bold'
        }}>
          🧠
        </div>
        <div>
          <strong style={{ fontSize: '0.9rem', color: 'var(--text-primary)', display: 'block' }}>Tu Estilo</strong>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Perfil IA de Culling</span>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {filas.map(([etiqueta, valor]) => (
          <div key={etiqueta} className="flex-between" style={{ fontSize: '0.75rem' }}>
            <span style={{ color: 'var(--text-secondary)' }}>{etiqueta}</span>
            <strong style={{ color: 'var(--text-primary)' }}>{valor}</strong>
          </div>
        ))}
      </div>

      <div style={{ marginTop: '4px' }}>
        <div className="flex-between" style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
          <span>Madurez del modelo</span>
          <span>{Math.round(madurez)}%</span>
        </div>
        <div style={{ height: '4px', backgroundColor: 'var(--bg-surface)', borderRadius: '2px', overflow: 'hidden' }}>
          <div style={{ width: `${madurez}%`, height: '100%', background: 'linear-gradient(90deg, var(--accent-amber), var(--accent-hover))' }} />
        </div>
      </div>
    </div>
  );
}
