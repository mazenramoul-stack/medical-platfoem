import { Suspense, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Float } from '@react-three/drei';

/** Detect WebGL once so we can fall back gracefully instead of crashing. */
function webglAvailable() {
  try {
    const c = document.createElement('canvas');
    return !!(window.WebGLRenderingContext && (c.getContext('webgl') || c.getContext('experimental-webgl')));
  } catch {
    return false;
  }
}

/**
 * Shared react-three-fiber canvas: lighting, gentle float, auto-rotate orbit,
 * and a static neon fallback when WebGL is unavailable.
 */
export default function Scene3D({
  accent = '#00ffcc',
  height = 320,
  children,
  float = true,
  autoRotate = true,
  controls = true,
  camera = { position: [0, 0, 4.2], fov: 45 },
  fallbackIcon = '◉',
}) {
  const ok = useMemo(() => webglAvailable(), []);

  if (!ok) {
    return (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{
          fontSize: 72, color: accent, filter: `drop-shadow(0 0 24px ${accent})`,
        }}>{fallbackIcon}</div>
      </div>
    );
  }

  const content = float ? <Float speed={2} rotationIntensity={0.6} floatIntensity={0.8}>{children}</Float> : children;

  return (
    <div style={{ height, width: '100%' }}>
      <Canvas camera={camera} dpr={[1, 2]} gl={{ antialias: true, alpha: true }}>
        <ambientLight intensity={0.5} />
        <pointLight position={[5, 5, 5]} intensity={1.2} color="#ffffff" />
        <pointLight position={[-5, -3, 2]} intensity={1.6} color={accent} />
        <Suspense fallback={null}>{content}</Suspense>
        {controls && (
          <OrbitControls
            enableZoom={false}
            enablePan={false}
            autoRotate={autoRotate}
            autoRotateSpeed={1.2}
          />
        )}
      </Canvas>
    </div>
  );
}
