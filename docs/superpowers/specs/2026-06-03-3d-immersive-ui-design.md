# 3D Immersive UI Redesign — Design Spec

Date: 2026-06-03 · Project: Multimodal Medical AI Platform (frontend)

## Goal
Transform the React frontend into an immersive, dark-neon **3D** experience
("wow the audience") while keeping all existing functionality (auth, patient
CRUD, MRI/ECG upload + results, reports) fully working. Backend untouched.

## Decisions (from brainstorming)
- **Scope:** global theme everywhere + flagship full-3D Login & Dashboard;
  functional pages re-skinned to match but kept 100% working.
- **3D engine:** Three.js + @react-three/fiber + @react-three/drei, procedural
  geometry (no large model files).
- **Domain mapping:** brain = MRI/EEG (teal/violet), heart = ECG/Echo (rose/amber).

## Design language
- Background `#07070f`; panels `#111122`/`#0a0a0f`; borders `#1e1e2e`.
- Accents: neuro teal `#00ffcc`, violet `#a855f7`; cardio rose `#f43f5e`, amber `#fbbf24`.
- Fonts: Space Mono (display/labels), DM Sans (body) via Google Fonts.
- Ambient layers (fixed, pointer-events:none, behind content): particle
  constellation, mouse-follow radial glow, faint grid. Honor `prefers-reduced-motion`.

## Components
New `components/fx/`: `ParticleField`, `MouseGlow`, `GridOverlay`, `TiltCard`.
New `components/three/`: `Scene3D` (r3f canvas wrapper + lights + auto-rotate +
hover/click + WebGL fallback), `Brain3D`, `Heart3D` (beating), `ECGWave3D`,
`RotatingCube`.
New `theme/tokens.js`: centralized colors/fonts (single source, reversible).

## Per-page
- Login/Register: 3D hero (Brain3D + Heart3D) + neon glass form; same auth logic.
- Dashboard: TiltCards per modality (MRI/ECG/EEG/Echo/Patients/Reports) + stats.
- Shell (Sidebar/Navbar/Layout): dark neon glass, glowing active nav.
- Patients/MRI/ECG/Results/Reports: re-skin to theme; tables/forms/uploads/result
  images/PDF flows unchanged. Result pages get a 3D accent header only.
- EEG/Echo placeholders: restyled, keep "coming soon".

## Non-goals / safety
- No changes to backend, API, Redux logic, services, routing, validation work.
- `prefers-reduced-motion` + WebGL-unavailable fallback (static neon, no crash).
- Lazy-load 3D scenes so data pages stay fast.
- `npm run build` must pass after each wave.

## Build order (waves)
1. Deps + theme tokens + fonts + ambient FX + shell restyle.
2. 3D primitives (Scene3D, Brain3D, Heart3D, TiltCard, RotatingCube).
3. Flagship Login + Dashboard.
4. Re-skin functional pages.
5. Build verification + review.
