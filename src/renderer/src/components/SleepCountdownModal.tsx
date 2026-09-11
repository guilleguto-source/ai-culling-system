import React, { useState, useEffect } from 'react';

interface SleepCountdownModalProps {
  isOpen: boolean;
  onCancel: () => void;
}

export const SleepCountdownModal: React.FC<SleepCountdownModalProps> = ({ isOpen, onCancel }) => {
  const [secondsLeft, setSecondsLeft] = useState(180); // 3 minutos

  useEffect(() => {
    if (!isOpen) {
      setSecondsLeft(180);
      return;
    }

    const timer = setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          handleSuspend();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [isOpen]);

  const handleSuspend = async () => {
    try {
      if (window.api?.suspendPC) {
        await window.api.suspendPC();
      }
    } catch (e) {
      console.error('Error invocando suspendPC:', e);
    }
  };

  if (!isOpen) return null;

  const minutes = Math.floor(secondsLeft / 60);
  const seconds = secondsLeft % 60;
  const progressPercent = ((180 - secondsLeft) / 180) * 100;

  const overlayStyle: React.CSSProperties = {
    position: 'fixed',
    top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(5, 7, 10, 0.85)',
    backdropFilter: 'blur(8px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 9999,
  };

  const modalStyle: React.CSSProperties = {
    backgroundColor: 'var(--color-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-xl)',
    boxShadow: 'var(--shadow-xl)',
    padding: '32px',
    width: '100%',
    maxWidth: '420px',
    textAlign: 'center',
    display: 'flex',
    flexDirection: 'col',
    gap: '24px'
  };

  return (
    <div style={overlayStyle}>
      <div style={modalStyle}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>💤</div>
          <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)', margin: '0 0 8px 0' }}>
            Lote Completado
          </h3>
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.5 }}>
            El equipo se suspenderá automáticamente para permitir que el NAS finalice el guardado seguro de metadatos.
          </p>
        </div>

        <div style={{ margin: '24px 0' }}>
          <div style={{ fontSize: '42px', fontFamily: 'var(--font-mono)', fontWeight: 'var(--fw-bold)', color: 'var(--accent-primary)', letterSpacing: '2px', marginBottom: '16px' }}>
            {String(minutes).padStart(2, '0')}:{String(seconds).padStart(2, '0')}
          </div>
          <div style={{ width: '100%', height: '6px', backgroundColor: 'var(--color-surface-elevated)', borderRadius: '999px', overflow: 'hidden' }}>
            <div
              style={{
                height: '100%',
                backgroundColor: 'var(--accent-primary)',
                width: `${progressPercent}%`,
                transition: 'width 1s linear'
              }}
            />
          </div>
        </div>

        <div style={{ display: 'flex', gap: '12px' }}>
          <button
            onClick={onCancel}
            style={{
              flex: 1,
              padding: '12px',
              backgroundColor: 'var(--color-surface-elevated)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              fontSize: 'var(--text-sm)',
              fontWeight: 'var(--fw-medium)',
              cursor: 'pointer'
            }}
          >
            Cancelar Suspensión
          </button>
          <button
            onClick={handleSuspend}
            style={{
              flex: 1,
              padding: '12px',
              backgroundColor: 'var(--accent-primary)',
              color: 'var(--color-bg)',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              fontSize: 'var(--text-sm)',
              fontWeight: 'var(--fw-bold)',
              cursor: 'pointer',
              boxShadow: 'var(--shadow-glow-amber)'
            }}
          >
            Suspender Ahora
          </button>
        </div>
      </div>
    </div>
  );
};

