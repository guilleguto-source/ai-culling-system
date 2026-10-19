import { useState, useEffect } from 'react';

/**
 * Anima un valor numérico desde 0 hasta targetValue con curva easeOutExpo
 */
export function useCountUp(targetValue: number, duration: number = 800): number {
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    if (!targetValue || isNaN(targetValue)) {
      setCurrent(0);
      return;
    }

    let startTimestamp: number | null = null;
    let animationFrameId: number;

    const step = (timestamp: number) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / duration, 1);
      
      // Easing: easeOutExpo
      const eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      setCurrent(Math.round(eased * targetValue));

      if (progress < 1) {
        animationFrameId = requestAnimationFrame(step);
      }
    };

    animationFrameId = requestAnimationFrame(step);

    return () => {
      if (animationFrameId) cancelAnimationFrame(animationFrameId);
    };
  }, [targetValue, duration]);

  return current;
}
