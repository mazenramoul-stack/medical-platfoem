import { useCallback, useRef, useState } from 'react';

import { useTokens } from '../../theme/ThemeContext.jsx';

/**
 * 3D mouse-tilt card with glow + shimmer. Wraps arbitrary children.
 * Pass an accent color (hex); optional onClick. Used for dashboard tiles.
 */
export default function TiltCard({
  accent = '#00ffcc',
  onClick,
  className = '',
  style = {},
  children,
  width,
  height,
}) {
  const { isDark, colors } = useTokens();
  const ref = useRef(null);
  const [rot, setRot] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState(false);

  const onMove = useCallback((e) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const rx = ((e.clientY - (r.top + r.height / 2)) / (r.height / 2)) * -12;
    const ry = ((e.clientX - (r.left + r.width / 2)) / (r.width / 2)) * 12;
    setRot({ x: rx, y: ry });
  }, []);

  const onLeave = useCallback(() => { setRot({ x: 0, y: 0 }); setHovered(false); }, []);

  const restShadow = isDark ? '0 4px 24px #00000088' : '0 4px 24px rgba(15,23,42,0.10)';

  return (
    <div
      ref={ref}
      onMouseMove={onMove}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={onLeave}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => (e.key === 'Enter' || e.key === ' ') && onClick(e) : undefined}
      style={{ perspective: 900, cursor: onClick ? 'pointer' : 'default', userSelect: 'none', ...style }}
    >
      <div
        className={className}
        style={{
          width, height,
          borderRadius: 18,
          background: hovered
            ? `linear-gradient(135deg, ${accent}1a, ${colors.panelDeep})`
            : `linear-gradient(135deg, ${colors.panel}, ${colors.panelDeep})`,
          border: `1px solid ${hovered ? accent : colors.edge}`,
          boxShadow: hovered
            ? `0 0 36px ${accent}44, 0 0 80px ${accent}22, inset 0 0 22px ${accent}11`
            : restShadow,
          transform: `rotateX(${rot.x}deg) rotateY(${rot.y}deg) scale(${hovered ? 1.04 : 1})`,
          transition: hovered
            ? 'box-shadow .2s, border-color .2s, transform .06s'
            : 'all .5s cubic-bezier(.23,1,.32,1)',
          position: 'relative',
          overflow: 'hidden',
          transformStyle: 'preserve-3d',
        }}
      >
        {/* shimmer follows tilt */}
        <div style={{
          position: 'absolute', inset: 0, borderRadius: 18, pointerEvents: 'none',
          background: `radial-gradient(circle at ${50 + rot.y * 2}% ${50 - rot.x * 2}%, ${accent}1c 0%, transparent 65%)`,
          transition: 'background .06s',
        }} />
        {/* corner dot */}
        <div style={{
          position: 'absolute', top: 12, right: 12, width: 6, height: 6, borderRadius: '50%',
          background: accent, boxShadow: `0 0 8px ${accent}`,
          opacity: hovered ? 1 : 0.3, transition: 'opacity .3s',
        }} />
        {children}
        {/* bottom bar */}
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, height: 2,
          background: `linear-gradient(90deg, transparent, ${accent}, transparent)`,
          opacity: hovered ? 1 : 0, transition: 'opacity .3s',
        }} />
      </div>
    </div>
  );
}
