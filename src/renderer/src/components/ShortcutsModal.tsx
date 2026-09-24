import React from 'react';
import { Button } from './ui/Button';
import { IconX } from './icons';

interface ShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ShortcutsModal: React.FC<ShortcutsModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  const shortcutGroups = [
    {
      title: 'Cuadrícula y Culling',
      shortcuts: [
        { key: 'P / A', desc: 'Elegir fotografía (Pick / Selected)' },
        { key: 'X / D', desc: 'Descartar fotografía (Reject)' },
        { key: '1 — 5', desc: 'Asignar calificación de estrellas' },
        { key: 'Enter', desc: 'Abrir visor detallado' },
        { key: 'Esc', desc: 'Cerrar visor o modal activo' }
      ]
    },
    {
      title: 'Comparador de Ráfagas (Duelos)',
      shortcuts: [
        { key: '← / →', desc: 'Navegar a la ráfaga anterior / siguiente' },
        { key: 'P / Enter', desc: 'Aprobar Candidato IA' },
        { key: 'X', desc: 'Seleccionar foto alternativa' },
        { key: 'F', desc: 'Alternar cuadrícula de rostros alineados' }
      ]
    },
    {
      title: 'General',
      shortcuts: [
        { key: '?', desc: 'Abrir este panel de atajos' }
      ]
    }
  ];

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(11, 13, 16, 0.8)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: 'var(--space-4)'
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '520px',
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-xl)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column'
        }}
      >
        <header
          style={{
            height: '52px',
            padding: '0 var(--space-5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid var(--border-subtle)'
          }}
        >
          <span style={{ fontSize: 'var(--text-base)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
            Atajos de Teclado
          </span>
          <button onClick={onClose} className="gf-btn gf-btn-ghost gf-btn-sm" style={{ padding: '6px' }}>
            <IconX size={16} />
          </button>
        </header>

        <div style={{ padding: 'var(--space-5)', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', maxHeight: '420px', overflowY: 'auto' }}>
          {shortcutGroups.map((group) => (
            <div key={group.title} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <span className="sidebar-section-title" style={{ padding: 0 }}>
                {group.title}
              </span>
              <div
                style={{
                  backgroundColor: 'var(--color-surface-elevated)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  padding: 'var(--space-2) var(--space-3)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 'var(--space-2)'
                }}
              >
                {group.shortcuts.map((s) => (
                  <div key={s.key} className="flex justify-between items-center" style={{ fontSize: 'var(--text-xs)' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>{s.desc}</span>
                    <kbd
                      className="text-mono"
                      style={{
                        padding: '2px 6px',
                        borderRadius: 'var(--radius-xs)',
                        backgroundColor: 'var(--color-surface)',
                        border: '1px solid var(--border-default)',
                        color: 'var(--accent-primary)',
                        fontSize: '11px',
                        fontWeight: 'var(--fw-semibold)'
                      }}
                    >
                      {s.key}
                    </kbd>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <footer
          style={{
            height: '48px',
            padding: '0 var(--space-5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            borderTop: '1px solid var(--border-subtle)'
          }}
        >
          <Button variant="secondary" size="sm" onClick={onClose}>
            Entendido
          </Button>
        </footer>
      </div>
    </div>
  );
};

export default ShortcutsModal;
