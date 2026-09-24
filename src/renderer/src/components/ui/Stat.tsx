import React from 'react';
import { useCountUp } from '../../utils/useCountUp';

export interface StatProps {
  value: number | string;
  label: string;
  animate?: boolean;
  suffix?: string;
  className?: string;
}

export const Stat: React.FC<StatProps> = ({
  value,
  label,
  animate = true,
  suffix = '',
  className = ''
}) => {
  const numericValue = typeof value === 'number' ? value : parseFloat(String(value));
  const isNumber = !isNaN(numericValue) && typeof value === 'number';
  const animatedNumber = useCountUp(isNumber && animate ? numericValue : 0);

  const displayValue = isNumber && animate
    ? `${animatedNumber.toLocaleString()}${suffix}`
    : `${value}${suffix}`;

  return (
    <div className={`gf-stat-box ${className}`.trim()}>
      <span className="gf-stat-value">{displayValue}</span>
      <span className="gf-stat-label">{label}</span>
    </div>
  );
};
