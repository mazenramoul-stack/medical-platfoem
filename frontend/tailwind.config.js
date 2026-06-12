/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Theme-aware palette. Every value resolves to a CSS variable defined
        // in src/index.css (:root = light, .dark = dark-neon), so the same
        // class names render correctly in both themes. The --rgb-* channel
        // form keeps Tailwind alpha modifiers (e.g. ring-neuro/70) working.
        primary:    'rgb(var(--rgb-neuro) / <alpha-value>)',
        secondary:  'rgb(var(--rgb-violet) / <alpha-value>)',
        success:    'rgb(var(--rgb-neuro) / <alpha-value>)',
        danger:     'rgb(var(--rgb-cardio) / <alpha-value>)',
        warning:    'rgb(var(--rgb-amber) / <alpha-value>)',
        background: 'rgb(var(--rgb-bg) / <alpha-value>)',
        card:       'rgb(var(--rgb-panel) / <alpha-value>)',
        // accents
        neuro:      'rgb(var(--rgb-neuro) / <alpha-value>)',
        violet:     'rgb(var(--rgb-violet) / <alpha-value>)',
        cardio:     'rgb(var(--rgb-cardio) / <alpha-value>)',
        amber:      'rgb(var(--rgb-amber) / <alpha-value>)',
        blue:       'rgb(var(--rgb-blue) / <alpha-value>)',
        // surfaces / lines
        ink:        'rgb(var(--rgb-ink) / <alpha-value>)',
        panel:      'rgb(var(--rgb-panel) / <alpha-value>)',
        paneldeep:  'rgb(var(--rgb-paneldeep) / <alpha-value>)',
        edge:       'rgb(var(--rgb-edge) / <alpha-value>)',
        surface:    'rgb(var(--rgb-bg) / <alpha-value>)',
        // text emphasis (use text-hi / text-mid / text-low)
        hi:         'rgb(var(--rgb-hi) / <alpha-value>)',
        mid:        'rgb(var(--rgb-mid) / <alpha-value>)',
        low:        'rgb(var(--rgb-low) / <alpha-value>)',
      },
      fontFamily: {
        mono: ["'Space Mono'", 'monospace'],
        sans: ["'DM Sans'", 'sans-serif'],
      },
      boxShadow: {
        neon: '0 0 24px var(--glow-strong), 0 0 48px var(--glow-soft)',
      },
      keyframes: {
        floaty: { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-6px)' } },
        pulseGlow: { '0%,100%': { opacity: '0.5' }, '50%': { opacity: '1' } },
      },
      animation: {
        floaty: 'floaty 4s ease-in-out infinite',
        pulseGlow: 'pulseGlow 2.5s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
