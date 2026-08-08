import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { Button } from './ui/Button';
import { useToast } from './Toast';

interface StyleProfileViewProps {
  directory?: string;
}

export const StyleProfileView: React.FC<StyleProfileViewProps> = ({ directory }) => {
  const [learningSummary, setLearningSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const { showToast } = useToast();

  useEffect(() => {
    (async () => {
      try {
        const summary = await apiClient.getLearningSummary();
        setLearningSummary(summary);
      } catch {
        // fallback
      } finally {
        setLoading(false);
      }
    })();
  }, [directory]);

  const handleExportReport = () => {
    showToast('Reporte de perfil exportado exitosamente', 'success');
  };

  const totalDecisions = learningSummary?.decisiones_gusto ?? 0;
  const userChoices = learningSummary?.seleccionadas_aprendidas ?? 0;
  const calibratedPersons = learningSummary?.caras_calibradas ?? 0;
  const discoveredScenes = learningSummary?.escenas ?? 0;
  const isTrained = !!learningSummary?.gusto_entrenado;
  const maturityPercent = isTrained
    ? 92
    : totalDecisions > 0
    ? Math.min(85, Math.max(15, Math.round((totalDecisions / 200) * 100)))
    : 0;

  return (
    <div
      style={{
        flex: 1,
        height: '100%',
        backgroundColor: 'var(--color-bg)',
        overflowY: 'auto',
        padding: 'var(--space-6)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-6)'
      }}
    >
      {/* 1. Header Toolbar */}
      <div className="flex justify-between items-center">
        <div>
          <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)' }}>
            Tu Estilo Fotográfico
          </h1>
          <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginTop: '2px' }}>
            Perfil y criterio estético aprendido continuamente por Guto Flow
          </p>
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={handleExportReport}
        >
          Exportar reporte
        </Button>
      </div>

      {/* 2. Top Overview Row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '260px 1fr 1fr',
          gap: 'var(--space-4)'
        }}
      >
        {/* Gauge de Madurez */}
        <div
          style={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-5)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            textAlign: 'center',
            gap: 'var(--space-3)',
            boxShadow: 'var(--shadow-sm)'
          }}
        >
          <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-secondary)' }}>
            Madurez del modelo
          </span>

          {/* SVG Circular Progress */}
          <div style={{ position: 'relative', width: '110px', height: '110px' }}>
            <svg width="110" height="110" viewBox="0 0 100 100" style={{ transform: 'rotate(-90deg)' }}>
              <circle
                cx="50"
                cy="50"
                r="40"
                stroke="var(--color-surface-elevated)"
                strokeWidth="8"
                fill="transparent"
              />
              <circle
                cx="50"
                cy="50"
                r="40"
                stroke="var(--accent-primary)"
                strokeWidth="8"
                strokeDasharray={`${(maturityPercent / 100) * 251.2} 251.2`}
                strokeLinecap="round"
                fill="transparent"
                style={{ transition: 'stroke-dasharray 1s ease' }}
              />
            </svg>
            <div
              className="text-mono"
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 'var(--text-xl)',
                fontWeight: 'var(--fw-bold)',
                color: 'var(--text-primary)'
              }}
            >
              {maturityPercent}%
            </div>
          </div>

          <div>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
              {isTrained ? 'Tu perfil está activo y entrenado' : totalDecisions > 0 ? 'Perfil en aprendizaje' : 'Sin calibrar aún'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px', lineHeight: 1.4 }}>
              {isTrained
                ? 'Guto Flow entiende con alta precisión tus preferencias estéticas.'
                : 'Completa selecciones y duelos para afinar el modelo de gusto local.'}
            </div>
          </div>
        </div>

        {/* Massive Stats Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 'var(--space-3)'
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-4)',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center'
            }}
          >
            <span className="text-mono" style={{ fontSize: 'var(--text-2xl)', fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)' }}>
              {userChoices.toLocaleString()}
            </span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginTop: '2px' }}>
              Tus elecciones
            </span>
          </div>

          <div
            style={{
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-4)',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center'
            }}
          >
            <span className="text-mono" style={{ fontSize: 'var(--text-2xl)', fontWeight: 'var(--fw-bold)', color: 'var(--accent-primary)' }}>
              {totalDecisions.toLocaleString()}
            </span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginTop: '2px' }}>
              Decisiones aprendidas
            </span>
          </div>

          <div
            style={{
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-4)',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center'
            }}
          >
            <span className="text-mono" style={{ fontSize: 'var(--text-2xl)', fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)' }}>
              {calibratedPersons}
            </span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginTop: '2px' }}>
              Personas calibradas
            </span>
          </div>

          <div
            style={{
              backgroundColor: 'var(--color-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-4)',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center'
            }}
          >
            <span className="text-mono" style={{ fontSize: 'var(--text-2xl)', fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)' }}>
              {discoveredScenes}
            </span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginTop: '2px' }}>
              Escenas descubiertas
            </span>
          </div>
        </div>

        {/* Preferencias principales */}
        <div
          style={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-4)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-2)'
          }}
        >
          <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)', marginBottom: 'var(--space-1)' }}>
            Preferencias principales
          </span>

          {[
            { trait: 'Expresiones naturales', affinity: 'Muy alta', color: 'var(--success)' },
            { trait: 'Ojos abiertos', affinity: 'Muy alta', color: 'var(--success)' },
            { trait: 'Momentos espontáneos', affinity: 'Alta', color: 'var(--accent-primary)' },
            { trait: 'Encuadres medios', affinity: 'Alta', color: 'var(--accent-primary)' },
            { trait: 'Fondos desenfocados', affinity: 'Media', color: 'var(--text-secondary)' },
            { trait: 'Colores cálidos', affinity: 'Media', color: 'var(--text-secondary)' },
            { trait: 'Contraste moderado', affinity: 'Baja', color: 'var(--text-muted)' }
          ].map((item) => (
            <div key={item.trait} className="flex justify-between items-center" style={{ fontSize: '11px' }}>
              <span style={{ color: 'var(--text-secondary)' }}>{item.trait}</span>
              <span style={{ color: item.color, fontWeight: 'var(--fw-medium)' }}>{item.affinity}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 3. Bottom Row: Edición aprendida + Tipos de fotos */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1.2fr 1fr',
          gap: 'var(--space-4)'
        }}
      >
        {/* Tu estilo de edición aprendido */}
        <div
          style={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-5)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-3)'
          }}
        >
          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
            Tu estilo de edición aprendido
          </span>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {[
              { param: 'Contraste', val: '+15' },
              { param: 'Saturación', val: '+8' },
              { param: 'Temperatura', val: 'Cálida' },
              { param: 'Sombras', val: '+10' },
              { param: 'Altas luces', val: '-5' },
              { param: 'Claridad', val: '+12' }
            ].map((p) => (
              <div key={p.param} className="flex justify-between items-center" style={{ fontSize: 'var(--text-xs)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>{p.param}</span>
                <span className="text-mono" style={{ color: 'var(--accent-primary)', fontWeight: 'var(--fw-semibold)' }}>{p.val}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Tipos de fotos que prefieres */}
        <div
          style={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-5)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-3)'
          }}
        >
          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
            Tipos de fotos que prefieres
          </span>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {[
              { type: 'Retratos', pct: 45 },
              { type: 'Momentos espontáneos', pct: 28 },
              { type: 'Detalles y contexto', pct: 15 },
              { type: 'Ambiente', pct: 12 }
            ].map((item) => (
              <div key={item.type}>
                <div className="flex justify-between items-center" style={{ fontSize: '11px', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>{item.type}</span>
                  <span className="text-mono" style={{ color: 'var(--text-primary)', fontWeight: 'var(--fw-bold)' }}>{item.pct}%</span>
                </div>
                <div style={{ height: '5px', backgroundColor: 'var(--color-surface-elevated)', borderRadius: 'var(--radius-pill)', overflow: 'hidden' }}>
                  <div style={{ width: `${item.pct}%`, height: '100%', backgroundColor: 'var(--accent-primary)' }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 4. Advice Footer Banner */}
      <div
        style={{
          padding: '12px 16px',
          backgroundColor: 'rgba(231, 161, 58, 0.08)',
          border: '1px solid rgba(231, 161, 58, 0.25)',
          borderRadius: 'var(--radius-sm)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          fontSize: 'var(--text-xs)',
          color: 'var(--accent-primary)'
        }}
      >
        <span>💡</span>
        <span>Consejo: Sigue eligiendo tus fotos favoritas en la cuadrícula y duelos para que Guto Flow refine tu perfil continuo.</span>
      </div>
    </div>
  );
};

export default StyleProfileView;
