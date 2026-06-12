import { useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Sparkles } from '@react-three/drei';
import * as THREE from 'three';

import { prefersReducedMotion } from '../../theme/tokens.js';

/**
 * Anatomical human heart, procedurally built: ventricular mass (lathe profile
 * with organic surface noise), two atria, aortic arch with branch vessels,
 * pulmonary trunk, superior vena cava and coronary arteries.
 *
 * Beats with a real cardiac cycle: atrial kick, then a strong ventricular
 * "lub" (radial squeeze + systolic twist), then a softer "dub", with a
 * pressure pulse running through the great vessels. Hover raises the rate.
 */

function pulse(p, center, width) {
  const d = p - center;
  return Math.exp(-(d * d) / width);
}

function mix(hexA, hexB, t) {
  return `#${new THREE.Color(hexA).lerp(new THREE.Color(hexB), t).getHexString()}`;
}

export default function Heart3D({ accent = '#f43f5e', scale = 1, bpm = 72 }) {
  const group = useRef();
  const beatGroup = useRef();
  const ventGroup = useRef();
  const ventMesh = useRef();
  const atriaGroup = useRef();
  const vesselGroup = useRef();
  const phaseRef = useRef(0);
  const [hovered, setHovered] = useState(false);
  const reduced = useMemo(() => prefersReducedMotion(), []);

  // ---- geometry ----
  const ventricleGeometry = useMemo(() => {
    // teardrop profile of the ventricular mass, apex pointing down
    const ctrl = [
      [0.06, 0.6], [0.34, 0.58], [0.62, 0.48], [0.82, 0.26], [0.9, 0.0],
      [0.86, -0.28], [0.7, -0.56], [0.46, -0.82], [0.2, -1.0], [0.04, -1.08],
    ].map(([x, y]) => new THREE.Vector2(x, y));
    const profile = new THREE.SplineCurve(ctrl).getPoints(40);
    const geo = new THREE.LatheGeometry(profile, 48);
    // deterministic organic irregularity (no Math.random — keeps renders stable)
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const y = pos.getY(i);
      const z = pos.getZ(i);
      const r = Math.sqrt(x * x + z * z) || 1;
      const bump = 0.028 * Math.sin(4.0 * y + 3.0 * x) + 0.022 * Math.sin(6.0 * z - 2.0 * y);
      pos.setX(i, x + (x / r) * bump);
      pos.setZ(i, z + (z / r) * bump);
    }
    geo.scale(1.12, 1, 0.92);
    geo.computeVertexNormals();
    return geo;
  }, []);

  const vessels = useMemo(() => {
    const aortaCurve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(-0.05, 0.5, -0.08),
      new THREE.Vector3(-0.02, 1.0, -0.12),
      new THREE.Vector3(-0.32, 1.24, -0.14),
      new THREE.Vector3(-0.62, 1.05, -0.16),
      new THREE.Vector3(-0.7, 0.68, -0.18),
    ]);
    const pulmonaryCurve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(0.26, 0.48, 0.25),
      new THREE.Vector3(0.15, 0.85, 0.33),
      new THREE.Vector3(-0.12, 1.02, 0.3),
    ]);
    // coronaries hug the ventricle surface (front z ≈ profile radius × 0.92)
    const ladCurve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(0.18, 0.35, 0.7),
      new THREE.Vector3(0.02, 0.0, 0.79),
      new THREE.Vector3(-0.1, -0.35, 0.7),
      new THREE.Vector3(-0.06, -0.65, 0.5),
      new THREE.Vector3(0.0, -0.88, 0.28),
    ]);
    const circumflexCurve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(0.45, 0.25, 0.6),
      new THREE.Vector3(0.62, -0.05, 0.5),
      new THREE.Vector3(0.64, -0.35, 0.36),
      new THREE.Vector3(0.5, -0.6, 0.22),
    ]);
    return {
      aorta: new THREE.TubeGeometry(aortaCurve, 40, 0.155, 14, false),
      pulmonary: new THREE.TubeGeometry(pulmonaryCurve, 28, 0.125, 12, false),
      lad: new THREE.TubeGeometry(ladCurve, 32, 0.024, 8, false),
      circumflex: new THREE.TubeGeometry(circumflexCurve, 28, 0.022, 8, false),
    };
  }, []);

  // ---- materials (accent-tinted cardiac palette) ----
  const mats = useMemo(() => {
    const muscle = mix(accent, '#7f1d1d', 0.55);
    const common = { roughness: 0.42, metalness: 0.05, clearcoat: 0.7, clearcoatRoughness: 0.3 };
    return {
      muscle: new THREE.MeshPhysicalMaterial({
        color: muscle, emissive: new THREE.Color(accent), emissiveIntensity: 0.1, ...common,
      }),
      atria: new THREE.MeshPhysicalMaterial({
        color: mix(muscle, '#ffffff', 0.1), emissive: new THREE.Color(accent), emissiveIntensity: 0.08, ...common,
      }),
      artery: new THREE.MeshPhysicalMaterial({
        color: mix(accent, '#ffffff', 0.18), emissive: new THREE.Color(accent), emissiveIntensity: 0.12, ...common,
      }),
      vein: new THREE.MeshPhysicalMaterial({
        color: '#7186b8', emissive: new THREE.Color('#7186b8'), emissiveIntensity: 0.05, ...common,
      }),
      coronary: new THREE.MeshPhysicalMaterial({ color: mix(muscle, '#000000', 0.35), ...common, roughness: 0.5 }),
    };
  }, [accent]);

  useFrame((state, delta) => {
    const bpmEff = bpm * (hovered ? 1.25 : 1);
    if (!reduced) phaseRef.current = (phaseRef.current + (delta * bpmEff) / 60) % 1;
    const p = phaseRef.current;

    // cardiac cycle: atrial kick → ventricular systole ("lub") → "dub"
    const atrialKick = pulse(p, 0.02, 0.0022);
    const ventSys = pulse(p, 0.16, 0.004) + 0.35 * pulse(p, 0.34, 0.003);
    const arteryPulse = pulse(p, 0.22, 0.006);

    if (ventGroup.current) {
      const squeeze = 1 - 0.085 * ventSys;
      ventGroup.current.scale.set(squeeze, 1 + 0.05 * ventSys, squeeze);
      ventGroup.current.rotation.y = 0.09 * ventSys; // systolic twist
    }
    if (atriaGroup.current) {
      atriaGroup.current.scale.setScalar(1 + 0.1 * atrialKick - 0.05 * ventSys);
    }
    if (vesselGroup.current) {
      vesselGroup.current.scale.setScalar(1 + 0.035 * arteryPulse);
    }
    if (beatGroup.current) beatGroup.current.position.y = 0.02 * ventSys;
    if (group.current) {
      if (!reduced) group.current.rotation.y += 0.0035;
      group.current.scale.setScalar(scale * (hovered ? 1.06 : 1));
    }
    if (ventMesh.current) {
      const m = ventMesh.current.material;
      m.emissiveIntensity = THREE.MathUtils.lerp(m.emissiveIntensity, hovered ? 0.26 : 0.1, 0.1);
    }
  });

  return (
    <group
      ref={group}
      rotation={[0.1, 0, -0.22]}
      onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = 'pointer'; }}
      onPointerOut={() => { setHovered(false); document.body.style.cursor = 'auto'; }}
    >
      <group ref={beatGroup}>
        {/* ventricular mass + right-ventricle bulge + coronaries */}
        <group ref={ventGroup}>
          <mesh ref={ventMesh} geometry={ventricleGeometry} material={mats.muscle} />
          <mesh material={mats.muscle} position={[0.5, -0.12, 0.18]} scale={[0.62, 0.78, 0.5]}>
            <sphereGeometry args={[1, 32, 24]} />
          </mesh>
          <mesh geometry={vessels.lad} material={mats.coronary} />
          <mesh geometry={vessels.circumflex} material={mats.coronary} />
        </group>

        {/* atria (scale around their own centroid) */}
        <group ref={atriaGroup} position={[0, 0.67, 0]}>
          <mesh material={mats.atria} position={[-0.38, 0.05, -0.12]} scale={[0.34, 0.29, 0.31]}>
            <sphereGeometry args={[1, 28, 20]} />
          </mesh>
          <mesh material={mats.atria} position={[0.5, -0.05, 0.05]} scale={[0.38, 0.34, 0.36]}>
            <sphereGeometry args={[1, 28, 20]} />
          </mesh>
        </group>

        {/* great vessels */}
        <group ref={vesselGroup}>
          <mesh geometry={vessels.aorta} material={mats.artery} />
          {/* aortic arch branches */}
          {[[-0.18, 1.32, -0.13], [-0.33, 1.38, -0.14], [-0.48, 1.28, -0.15]].map((pos) => (
            <mesh key={pos.join(',')} material={mats.artery} position={pos} rotation={[0, 0, 0.08]}>
              <cylinderGeometry args={[0.045, 0.052, 0.32, 10]} />
            </mesh>
          ))}
          <mesh geometry={vessels.pulmonary} material={mats.vein} />
          {/* superior vena cava */}
          <mesh material={mats.vein} position={[0.52, 0.95, 0.02]}>
            <cylinderGeometry args={[0.115, 0.125, 0.55, 12]} />
          </mesh>
        </group>
      </group>

      <Sparkles count={24} scale={3.2} size={2.5} speed={0.4} color={accent} />
    </group>
  );
}
