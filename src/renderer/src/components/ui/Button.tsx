import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  icon?: React.ReactNode;
  loading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'secondary',
  size = 'md',
  icon,
  loading = false,
  className = '',
  disabled,
  ...props
}) => {
  const variantClass = `gf-btn-${variant}`;
  const sizeClass = size !== 'md' ? `gf-btn-${size}` : '';

  return (
    <button
      className={`gf-btn ${variantClass} ${sizeClass} ${className}`.trim()}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <span className="gf-dot gf-dot-warning" />
      ) : (
        icon && <span className="flex-center">{icon}</span>
      )}
      {children}
    </button>
  );
};
