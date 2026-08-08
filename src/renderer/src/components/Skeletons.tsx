import React from 'react';

export const SkeletonCard: React.FC<{ aspectRatio?: string }> = ({ aspectRatio = '3/2' }) => (
  <div
    className="skeleton-shimmer"
    style={{
      width: '100%',
      aspectRatio,
      borderRadius: 'var(--radius-photo)',
      border: '1px solid var(--border-subtle)'
    }}
  />
);

export const SkeletonStat: React.FC = () => (
  <div
    className="skeleton-shimmer"
    style={{
      height: '64px',
      borderRadius: 'var(--radius-sm)',
      border: '1px solid var(--border-subtle)'
    }}
  />
);

export const SkeletonList: React.FC<{ count?: number }> = ({ count = 6 }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
    {Array.from({ length: count }).map((_, i) => (
      <div
        key={i}
        className="skeleton-shimmer"
        style={{
          height: '40px',
          borderRadius: 'var(--radius-xs)',
          border: '1px solid var(--border-subtle)'
        }}
      />
    ))}
  </div>
);
