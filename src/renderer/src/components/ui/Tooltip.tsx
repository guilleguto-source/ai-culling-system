import React, { useState } from 'react';

export interface TooltipProps {
  content: string;
  children: React.ReactNode;
  position?: 'top' | 'bottom' | 'left' | 'right';
}

export const Tooltip: React.FC<TooltipProps> = ({
  content,
  children,
  position = 'top'
}) => {
  const [visible, setVisible] = useState(false);

  return (
    <div
      style={{ position: 'relative', display: 'inline-flex' }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      {children}
      {visible && (
        <div
          role="tooltip"
          style={{
            position: 'absolute',
            zIndex: 100,
            ...(position === 'top' && { bottom: 'calc(100% + 6px)', left: '50%', transform: 'translateX(-50%)' }),
            ...(position === 'bottom' && { top: 'calc(100% + 6px)', left: '50%', transform: 'translateX(-50%)' }),
            ...(position === 'left' && { right: 'calc(100% + 6px)', top: '50%', transform: 'translateY(-50%)' }),
            ...(position === 'right' && { left: 'calc(100% + 6px)', top: '50%', transform: 'translateY(-50%)' }),
            backgroundColor: 'var(--color-surface-hover)',
            color: 'var(--text-primary)',
            fontSize: 'var(--text-xs)',
            padding: '4px 8px',
            borderRadius: 'var(--radius-xs)',
            border: '1px solid var(--border-default)',
            boxShadow: 'var(--shadow-md)',
            whiteSpace: 'nowrap',
            pointerEvents: 'none',
            animation: 'fadeIn var(--transition-fast)'
          }}
        >
          {content}
        </div>
      )}
    </div>
  );
};
