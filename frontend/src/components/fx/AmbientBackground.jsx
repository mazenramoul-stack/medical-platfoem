import { useEffect, useState } from 'react';

import ParticleField from './ParticleField.jsx';
import { useTokens } from '../../theme/ThemeContext.jsx';

/**
 * Full-screen ambient layers used app-wide: particle constellation,
 * a faint grid, and a soft radial glow that follows the cursor.
 * All fixed + non-interactive, sitting behind page content (zIndex 0).
 * Colors follow the active theme unless explicitly overridden via props.
 */
export default function AmbientBackground({ particleColor, glow }) {
  const { isDark, colors } = useTokens();
  const [pos, setPos] = useState({ x: 0.5, y: 0.4 });

  const pColor = particleColor ?? (isDark ? '0,255,200' : '13,148,136');
  const glowColor = glow ?? colors.neuro;
  const gridLine = isDark ? 'rgba(0,255,200,0.035)' : 'rgba(13,148,136,0.05)';

  useEffect(() => {
    const onMove = (e) => {
      setPos({ x: e.clientX / window.innerWidth, y: e.clientY / window.innerHeight });
    };
    window.addEventListener('mousemove', onMove);
    return () => window.removeEventListener('mousemove', onMove);
  }, []);

  return (
    <>
      <ParticleField color={pColor} />
      {/* grid */}
      <div
        aria-hidden="true"
        style={{
          position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none',
          backgroundImage:
            `linear-gradient(${gridLine} 1px, transparent 1px),`
            + `linear-gradient(90deg, ${gridLine} 1px, transparent 1px)`,
          backgroundSize: '60px 60px',
          maskImage: 'radial-gradient(ellipse 80% 80% at 50% 40%, #000 40%, transparent 100%)',
          WebkitMaskImage: 'radial-gradient(ellipse 80% 80% at 50% 40%, #000 40%, transparent 100%)',
        }}
      />
      {/* cursor glow */}
      <div
        aria-hidden="true"
        style={{
          position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none',
          background: `radial-gradient(ellipse 55% 45% at ${pos.x * 100}% ${pos.y * 100}%, ${glowColor}12, transparent 70%)`,
          transition: 'background 0.12s ease-out',
        }}
      />
    </>
  );
}
