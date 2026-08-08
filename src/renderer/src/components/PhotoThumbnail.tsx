import React, { useState } from 'react';
import { apiClient } from '../api/client';
import { getDynamicStyles } from '../utils/dynamicStyles';
import { IconCheck, IconX } from './icons';

export interface PhotoThumbnailProps {
  photo: any;
  isActive?: boolean;
  size?: 'compact' | 'normal' | 'large';
  onClick?: () => void;
  onPick?: (e: React.MouseEvent) => void;
  onReject?: (e: React.MouseEvent) => void;
}

const LABEL_LABELS: Record<string, string> = {
  selected: 'Elegida',
  highlighted: 'Destacada',
  duplicates: 'Repetida',
  closed_eyes: 'Ojos cerrados',
  blurry: 'Descarte',
};

export const PhotoThumbnail: React.FC<PhotoThumbnailProps> = ({
  photo,
  isActive = false,
  size = 'normal',
  onClick,
  onPick,
  onReject
}) => {
  const [isHovered, setIsHovered] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);

  const isPick = photo.label === 'selected' || photo.label === 'highlighted';
  const isReject = photo.label === 'blurry' || photo.label === 'closed_eyes';
  const isDuplicate = photo.label === 'duplicates';

  // Dimension presets
  const widthByPreset = {
    compact: '170px',
    normal: '230px',
    large: '310px'
  }[size];

  const getBorderColor = () => {
    if (isActive) return 'var(--accent-primary)';
    if (isPick) return 'rgba(53, 201, 149, 0.45)';
    if (isReject) return 'rgba(226, 103, 115, 0.3)';
    return 'var(--border-subtle)';
  };

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        width: widthByPreset,
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--color-surface)',
        borderRadius: 'var(--radius-sm)',
        border: `1px solid ${getBorderColor()}`,
        overflow: 'hidden',
        cursor: 'pointer',
        position: 'relative',
        opacity: isReject ? 0.55 : 1,
        transition: 'border-color var(--transition-fast), transform var(--transition-fast), opacity var(--transition-fast)',
        boxShadow: isActive ? '0 0 0 1px var(--accent-primary), var(--shadow-md)' : 'var(--shadow-sm)',
        transform: isHovered && !isActive ? 'translateY(-2px)' : 'none'
      }}
    >
      {/* Aspect Container */}
      <div
        style={{
          width: '100%',
          aspectRatio: '3 / 2',
          backgroundColor: 'var(--color-bg)',
          position: 'relative',
          overflow: 'hidden'
        }}
      >
        {/* Placeholder shimmer before load */}
        {!isLoaded && (
          <div
            className="skeleton-shimmer"
            style={{ position: 'absolute', inset: 0 }}
          />
        )}

        <img
          src={apiClient.getThumbnailUrl(photo.path)}
          alt={photo.filename}
          onLoad={() => setIsLoaded(true)}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            display: 'block',
            opacity: isLoaded ? 1 : 0,
            transition: 'opacity var(--transition-fast)',
            ...getDynamicStyles(photo)
          }}
          loading="lazy"
        />

        {/* Status Badge (Top Left) */}
        {photo.label && (
          <div
            style={{
              position: 'absolute',
              top: '6px',
              left: '6px',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 6px',
              borderRadius: 'var(--radius-xs)',
              fontSize: '10px',
              fontWeight: 'var(--fw-semibold)',
              letterSpacing: '0.3px',
              backgroundColor: isPick
                ? 'rgba(53, 201, 149, 0.85)'
                : isReject
                ? 'rgba(226, 103, 115, 0.85)'
                : isDuplicate
                ? 'rgba(231, 161, 58, 0.85)'
                : 'rgba(21, 25, 31, 0.85)',
              color: '#FFFFFF',
              backdropFilter: 'blur(4px)',
              zIndex: 2
            }}
          >
            {isPick && <IconCheck size={10} />}
            {isReject && <IconX size={10} />}
            <span>{LABEL_LABELS[photo.label] || photo.label}</span>
          </div>
        )}

        {/* AI Score Badge (Top Right) */}
        {photo.score !== undefined && (
          <div
            className="text-mono"
            style={{
              position: 'absolute',
              top: '6px',
              right: '6px',
              padding: '2px 6px',
              borderRadius: 'var(--radius-xs)',
              fontSize: '10px',
              fontWeight: 'var(--fw-bold)',
              backgroundColor: 'rgba(16, 19, 24, 0.85)',
              color: 'var(--accent-primary)',
              border: '1px solid rgba(231, 161, 58, 0.3)',
              backdropFilter: 'blur(4px)',
              zIndex: 2
            }}
          >
            {(photo.score * 10).toFixed(1)}
          </div>
        )}

        {/* Crop Proposed Indicator */}
        {photo.has_crop && (
          <div
            title="Reencuadre propuesto"
            style={{
              position: 'absolute',
              bottom: '6px',
              right: '6px',
              backgroundColor: 'rgba(16, 19, 24, 0.8)',
              borderRadius: 'var(--radius-xs)',
              padding: '2px 5px',
              fontSize: '11px',
              zIndex: 2
            }}
          >
            ✂
          </div>
        )}

        {/* Hover Quick Actions */}
        {isHovered && (
          <div
            style={{
              position: 'absolute',
              bottom: '6px',
              left: '6px',
              display: 'flex',
              gap: '4px',
              zIndex: 3
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {onPick && (
              <button
                className="gf-btn gf-btn-sm"
                onClick={onPick}
                style={{
                  padding: '3px 8px',
                  fontSize: '10px',
                  backgroundColor: 'rgba(53, 201, 149, 0.9)',
                  color: '#0B0D10',
                  fontWeight: 'var(--fw-bold)',
                  borderRadius: 'var(--radius-xs)'
                }}
                title="Elegir foto (P)"
              >
                <IconCheck size={12} /> Pick
              </button>
            )}
            {onReject && (
              <button
                className="gf-btn gf-btn-sm"
                onClick={onReject}
                style={{
                  padding: '3px 8px',
                  fontSize: '10px',
                  backgroundColor: 'rgba(226, 103, 115, 0.9)',
                  color: '#FFFFFF',
                  fontWeight: 'var(--fw-bold)',
                  borderRadius: 'var(--radius-xs)'
                }}
                title="Descartar foto (X)"
              >
                <IconX size={12} /> Reject
              </button>
            )}
          </div>
        )}
      </div>

      {/* Footer Info */}
      <div
        style={{
          padding: '6px 10px',
          display: 'flex',
          flexDirection: 'column',
          gap: '2px',
          backgroundColor: 'var(--color-surface)'
        }}
      >
        <span
          className="truncate"
          style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 'var(--fw-medium)',
            color: 'var(--text-primary)'
          }}
          title={photo.filename}
        >
          {photo.filename}
        </span>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '10px',
            color: 'var(--text-muted)'
          }}
        >
          <span>{photo.scene_type === 'portrait' ? 'Retrato' : 'Detalle'}</span>
          {photo.blur_score !== undefined && (
            <span className="text-mono">
              Nitidez {Math.round(Math.min(1, photo.blur_score / 500) * 100)}%
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

export default PhotoThumbnail;
