import { useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Sparkles } from '@react-three/drei';
import * as THREE from 'three';

import { prefersReducedMotion } from '../../theme/tokens.js';

/* ---- tiny 3D value-noise → ridged fbm (for cortical folds) ---- */
const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10);
const lerp = (a, b, t) => a + (b - a) * t;
function hash(x, y, z) {
  const p = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453;
  return p - Math.floor(p);
}
function vnoise(x, y, z) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const u = fade(x - xi), v = fade(y - yi), w = fade(z - zi);
  const c = (i, j, k) => hash(xi + i, yi + j, zi + k);
  const x1 = lerp(c(0, 0, 0), c(1, 0, 0), u), x2 = lerp(c(0, 1, 0), c(1, 1, 0), u);
  const x3 = lerp(c(0, 0, 1), c(1, 0, 1), u), x4 = lerp(c(0, 1, 1), c(1, 1, 1), u);
  return lerp(lerp(x1, x2, v), lerp(x3, x4, v), w);
}
function ridged(x, y, z) {
  let amp = 0.5, freq = 1, sum = 0;
  for (let o = 0; o < 4; o++) {
    const n = 1 - Math.abs(2 * vnoise(x * freq, y * freq, z * freq) - 1);
    sum += n * amp; amp *= 0.5; freq *= 2.15;
  }
  return sum;
}

function mix(hexA, hexB, t) {
  return `#${new THREE.Color(hexA).lerp(new THREE.Color(hexB), t).getHexString()}`;
}

/**
 * Cerebrum: rounded on top, flattened underside, longest front-to-back, heavy
 * gyri, a deep longitudinal fissure splitting two hemisphere bulges, and
 * per-vertex darkening inside the sulci so the folds read like real cortex.
 */
function buildCerebrumGeometry() {
  const geo = new THREE.IcosahedronGeometry(1, 6);
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  const v = new THREE.Vector3();
  const n = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i);
    n.copy(v).normalize();

    // cortical folds (gyri/sulci)
    const folds = ridged(n.x * 3.4 + 4, n.y * 3.4, n.z * 3.4) - 0.5;
    v.copy(n).multiplyScalar(1 + folds * 0.17);

    // proportions: widest ear-to-ear (x), longest front-back (z), low (y)
    v.x *= 1.06; v.y *= 0.8; v.z *= 1.28;

    // flatten the underside (brains sit flat below)
    if (v.y < 0) v.y *= 0.55;

    // deep longitudinal fissure + hemisphere bulges on either side of it
    if (v.y > 0) {
      const groove = Math.exp(-(v.x * v.x) / 0.01) * 0.26 * v.y;
      v.y -= groove;
    }
    v.x += Math.sign(v.x) * Math.exp(-(v.x * v.x) / 0.02) * 0.05;

    pos.setXYZ(i, v.x, v.y, v.z);

    // sulci shading: valleys (low fold value) darker and slightly redder
    const depth = THREE.MathUtils.clamp(0.5 - folds, 0, 1);
    colors[i * 3 + 0] = 1 - depth * 0.30;
    colors[i * 3 + 1] = 1 - depth * 0.42;
    colors[i * 3 + 2] = 1 - depth * 0.40;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.computeVertexNormals();
  return geo;
}

/** Cerebellum: smaller mass under the back, with fine horizontal folia bands. */
function buildCerebellumGeometry() {
  const geo = new THREE.SphereGeometry(1, 56, 40);
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  const v = new THREE.Vector3();
  const n = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i);
    n.copy(v).normalize();
    // layered horizontal striations + a touch of noise
    const bands = Math.sin(v.y * 26) * 0.5 + 0.5;
    const grain = vnoise(n.x * 5 + 9, n.y * 5, n.z * 5) - 0.5;
    v.copy(n).multiplyScalar(1 + (bands - 0.5) * 0.06 + grain * 0.05);
    // central vermis groove
    v.x += Math.sign(v.x) * Math.exp(-(v.x * v.x) / 0.03) * 0.03;
    pos.setXYZ(i, v.x, v.y, v.z);

    const depth = 1 - bands;
    colors[i * 3 + 0] = 1 - depth * 0.28;
    colors[i * 3 + 1] = 1 - depth * 0.38;
    colors[i * 3 + 2] = 1 - depth * 0.36;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.scale(0.52, 0.36, 0.44);
  geo.computeVertexNormals();
  return geo;
}

export default function Brain3D({ accent = '#00ffcc', scale = 1 }) {
  const group = useRef();
  const cortexMesh = useRef();
  const [hovered, setHovered] = useState(false);
  const [active, setActive] = useState(false);
  const reduced = useMemo(() => prefersReducedMotion(), []);

  const cerebrum = useMemo(() => buildCerebrumGeometry(), []);
  const cerebellum = useMemo(() => buildCerebellumGeometry(), []);

  // anatomical palette, faintly tinted by the theme accent for cohesion
  const mats = useMemo(() => {
    const common = { roughness: 0.48, metalness: 0.02, clearcoat: 0.55, clearcoatRoughness: 0.4, vertexColors: true };
    return {
      cortex: new THREE.MeshPhysicalMaterial({
        color: mix('#c89aa0', accent, 0.06), emissive: new THREE.Color(accent), emissiveIntensity: 0.1, ...common,
      }),
      cerebellum: new THREE.MeshPhysicalMaterial({
        color: mix('#b5878f', accent, 0.06), emissive: new THREE.Color(accent), emissiveIntensity: 0.08, ...common,
      }),
      stem: new THREE.MeshPhysicalMaterial({
        color: mix('#c9b09c', accent, 0.05), roughness: 0.5, metalness: 0.02, clearcoat: 0.5, clearcoatRoughness: 0.45,
      }),
    };
  }, [accent]);

  useFrame((_, dt) => {
    if (group.current && !reduced) group.current.rotation.y += dt * (hovered ? 0.5 : 0.22);
    if (cortexMesh.current) {
      const m = cortexMesh.current.material;
      m.emissiveIntensity = THREE.MathUtils.lerp(m.emissiveIntensity, hovered ? 0.22 : 0.1, 0.1);
    }
  });

  const target = (active ? 1.1 : 1) * (hovered ? 1.05 : 1) * scale;

  return (
    <group
      ref={group}
      scale={target}
      rotation={[0.25, 0, 0]}
      onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = 'pointer'; }}
      onPointerOut={() => { setHovered(false); document.body.style.cursor = 'auto'; }}
      onClick={(e) => { e.stopPropagation(); setActive((x) => !x); }}
    >
      <mesh ref={cortexMesh} geometry={cerebrum} material={mats.cortex} />
      {/* cerebellum under the back of the cerebrum */}
      <mesh geometry={cerebellum} material={mats.cerebellum} position={[0, -0.34, -0.92]} rotation={[0.25, 0, 0]} />
      {/* brainstem angling down-forward beneath the centre */}
      <mesh material={mats.stem} position={[0, -0.5, -0.32]} rotation={[-0.5, 0, 0]}>
        <cylinderGeometry args={[0.15, 0.1, 0.6, 16]} />
      </mesh>
      <Sparkles count={24} scale={3.2} size={2.5} speed={0.4} color={accent} />
    </group>
  );
}
