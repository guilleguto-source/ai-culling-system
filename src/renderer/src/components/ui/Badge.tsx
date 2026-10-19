import React from 'react';

export interface BadgeProps {
  variant?: 'pick' | 'reject' | 'ai' | 'info' | 'default';
  children?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  variant = 'default',
  children,
  icon,
  className = ''
}) => {
  const variantClass = variant !== 'default' ? `gf-badge-${variant}` : '';
  return (
    <span className={`gf-badge ${variantClass} ${className}`.trim()}>
      {icon && <span className="flex-center">{icon}</span>}
      {children}
    </span>
  );
};
