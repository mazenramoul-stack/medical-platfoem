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

/**
 * `highlight` (optional) is a map of region id -> { color, intensity }, mirroring
 * Heart3D. Whole-structure ids ('cerebrum' | 'cerebellum' | 'stem') glow that mesh
 * and ghost the rest; hemisphere ids ('left' | 'right') show a translucent glow
 * marker over that side (used for EEG lateralization, where the model gives
 * one-sided vs generalized but NOT which side — see the panel caveat).
 * `highlight.focus` ({ x, y, z?, color, intensity }) places a small glow marker at
 * a specific point — used for the MRI tumour position projected from the 2D mask.
 */
export default function Brain3D({ accent = '#00ffcc', scale = 1, highlight = null }) {
  const group = useRef();
  const cortexMesh = useRef();
  const cerebellumMesh = useRef();
  const stemMesh = useRef();
  const leftMarker = useRef();
  const rightMarker = useRef();
  const gradcamMarker = useRef();
  const [hovered, setHovered] = useState(false);
  const [active, setActive] = useState(false);
  const reduced = useMemo(() => prefersReducedMotion(), []);

  const cerebrum = useMemo(() => buildCerebrumGeometry(), []);
  const cerebellum = useMemo(() => buildCerebellumGeometry(), []);

  // anatomical palette, faintly tinted by the theme accent for cohesion.
  // transparent:true so non-problem structures can be ghosted (opacity lerped down).
  const mats = useMemo(() => {
    const common = { roughness: 0.48, metalness: 0.02, clearcoat: 0.55, clearcoatRoughness: 0.4, vertexColors: true, transparent: true, opacity: 1 };
    const cCortex = mix('#c89aa0', accent, 0.06);
    const cCereb = mix('#b5878f', accent, 0.06);
    const cStem = mix('#c9b09c', accent, 0.05);
    const marker = () => new THREE.MeshStandardMaterial({
      color: '#ffffff', emissive: new THREE.Color('#ffffff'), emissiveIntensity: 1.0,
      roughness: 0.4, metalness: 0, transparent: true, opacity: 0.45, depthWrite: false,
    });
    return {
      cortex: new THREE.MeshPhysicalMaterial({ color: cCortex, emissive: new THREE.Color(accent), emissiveIntensity: 0.1, ...common }),
      cerebellum: new THREE.MeshPhysicalMaterial({ color: cCereb, emissive: new THREE.Color(accent), emissiveIntensity: 0.08, ...common }),
      stem: new THREE.MeshPhysicalMaterial({
        color: cStem, emissive: new THREE.Color(accent), emissiveIntensity: 0.05,
        roughness: 0.5, metalness: 0.02, clearcoat: 0.5, clearcoatRoughness: 0.45, transparent: true, opacity: 1,
      }),
      markerL: marker(),
      markerR: marker(),
      markerGradcam: marker(),
      palette: {
        cortex: new THREE.Color(cCortex),
        cerebellum: new THREE.Color(cCereb),
        stem: new THREE.Color(cStem),
        grey: new THREE.Color('#d2d5dd'),
      },
    };
  }, [accent]);

  const hasHighlight = !!(highlight && Object.keys(highlight).length);
  const GHOST = 0.3;
  const setO = (m, t, solid) => { m.opacity = THREE.MathUtils.lerp(m.opacity, t, 0.12); m.depthWrite = solid; };

  // Glow the implicated structure and keep it solid; ghost the rest to translucent
  // grey; with no highlight keep the normal opaque look (+ hover lift on cortex).
  const applyMesh = (ref, id, baseColor, baseEmissive) => {
    const m = ref.current && ref.current.material;
    if (!m) return;
    const hl = highlight && highlight[id];
    if (hl) {
      m.color.lerp(baseColor, 0.12);
      m.emissive.set(hl.color);
      m.emissiveIntensity = THREE.MathUtils.lerp(m.emissiveIntensity, hl.intensity, 0.12);
      setO(m, 1, true);
    } else if (hasHighlight) {
      m.color.lerp(mats.palette.grey, 0.1);
      m.emissive.set(mats.palette.grey);
      m.emissiveIntensity = THREE.MathUtils.lerp(m.emissiveIntensity, 0.03, 0.12);
      setO(m, GHOST, false);
    } else {
      m.color.lerp(baseColor, 0.12);
      m.emissive.set(accent);
      m.emissiveIntensity = THREE.MathUtils.lerp(m.emissiveIntensity, baseEmissive + (hovered ? 0.12 : 0), 0.12);
      setO(m, 1, true);
    }
  };

  // Hemisphere marker — a soft translucent glow over one side, shown only while
  // that side is implicated.
  const applyMarker = (ref, id, tsec) => {
    const mesh = ref.current;
    if (!mesh) return;
    const hl = highlight && highlight[id];
    mesh.visible = !!hl;
    if (!hl) return;
    mesh.material.emissive.set(hl.color);
    mesh.material.color.set(hl.color);
    const wave = 0.5 + 0.5 * Math.sin(tsec * 3);
    mesh.scale.setScalar(1 + 0.05 * wave);
    mesh.material.emissiveIntensity = 0.85 + 0.35 * wave;
  };

  // Grad-CAM peak marker — a small glow at a specific point (the on-demand Grad-CAM
  // peak). Shown only while a gradcamFocus is supplied.
  const applyFocus = (ref, focus, tsec) => {
    const mesh = ref.current;
    if (!mesh) return;
    mesh.visible = !!focus;
    if (!focus) return;
    mesh.position.set(focus.x, focus.y, focus.z ?? 0.35);
    mesh.material.emissive.set(focus.color);
    mesh.material.color.set(focus.color);
    const wave = 0.5 + 0.5 * Math.sin(tsec * 3);
    mesh.scale.setScalar(1 + 0.12 * wave);
    mesh.material.emissiveIntensity = 0.9 + 0.5 * wave;
  };

  useFrame((state, dt) => {
    if (group.current && !reduced) group.current.rotation.y += dt * (hovered ? 0.5 : 0.22);
    const tsec = state.clock.getElapsedTime();
    applyMesh(cortexMesh, 'cerebrum', mats.palette.cortex, 0.1);
    applyMesh(cerebellumMesh, 'cerebellum', mats.palette.cerebellum, 0.08);
    applyMesh(stemMesh, 'stem', mats.palette.stem, 0.05);
    applyMarker(leftMarker, 'left', tsec);
    applyMarker(rightMarker, 'right', tsec);
    applyFocus(gradcamMarker, highlight && highlight.gradcamFocus, tsec);
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
      <mesh ref={cerebellumMesh} geometry={cerebellum} material={mats.cerebellum} position={[0, -0.34, -0.92]} rotation={[0.25, 0, 0]} />
      {/* brainstem angling down-forward beneath the centre */}
      <mesh ref={stemMesh} material={mats.stem} position={[0, -0.5, -0.32]} rotation={[-0.5, 0, 0]}>
        <cylinderGeometry args={[0.15, 0.1, 0.6, 16]} />
      </mesh>
      {/* hemisphere highlight markers — shown only when implicated */}
      <mesh ref={leftMarker} material={mats.markerL} position={[-0.5, 0.2, 0.12]} visible={false}>
        <sphereGeometry args={[0.6, 24, 24]} />
      </mesh>
      <mesh ref={rightMarker} material={mats.markerR} position={[0.5, 0.2, 0.12]} visible={false}>
        <sphereGeometry args={[0.6, 24, 24]} />
      </mesh>
      {/* Grad-CAM peak marker — where the classifier looked (shown on demand) */}
      <mesh ref={gradcamMarker} material={mats.markerGradcam} visible={false}>
        <sphereGeometry args={[0.26, 24, 24]} />
      </mesh>
      <Sparkles count={24} scale={3.2} size={2.5} speed={0.4} color={accent} />
    </group>
  );
}
