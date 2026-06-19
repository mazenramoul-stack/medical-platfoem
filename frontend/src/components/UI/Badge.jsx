// Variants are CSS-variable driven so badges stay readable in both themes:
// the *-fg variables are deep shades in light mode, bright pastels in dark.
const VARIANTS = {
  primary:   { bg: 'rgb(var(--rgb-neuro) / 0.12)',  fg: 'var(--neuro-fg)',  bd: 'rgb(var(--rgb-neuro) / 0.35)' },
  secondary: { bg: 'rgb(var(--rgb-violet) / 0.14)', fg: 'var(--violet-fg)', bd: 'rgb(var(--rgb-violet) / 0.4)' },
  success:   { bg: 'rgb(var(--rgb-neuro) / 0.12)',  fg: 'var(--neuro-fg)',  bd: 'rgb(var(--rgb-neuro) / 0.35)' },
  danger:    { bg: 'rgb(var(--rgb-cardio) / 0.14)', fg: 'var(--cardio-fg)', bd: 'rgb(var(--rgb-cardio) / 0.4)' },
  warning:   { bg: 'rgb(var(--rgb-amber) / 0.14)',  fg: 'var(--amber-fg)',  bd: 'rgb(var(--rgb-amber) / 0.4)' },
  gray:      { bg: 'rgb(var(--rgb-hi) / 0.06)',     fg: 'var(--text-mid)',  bd: 'rgb(var(--rgb-hi) / 0.12)' },
};

export default function Badge({ variant = 'gray', children, className = '', title }) {
  const v = VARIANTS[variant] || VARIANTS.gray;
  return (
    <span
      title={title}
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${className}`}
      style={{
        background: v.bg,
        color: v.fg,
        border: `1px solid ${v.bd}`,
        boxShadow: `0 0 10px ${v.bg}`,
        letterSpacing: '0.02em',
      }}
    >
      {children}
    </span>
  );
}
