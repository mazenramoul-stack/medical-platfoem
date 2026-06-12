const VARIANTS = {
  primary:   'text-ink bg-gradient-to-br from-neuro to-violet hover:opacity-90 shadow-neon disabled:opacity-40',
  secondary: 'text-ink bg-gradient-to-br from-violet to-neuro hover:opacity-90 disabled:opacity-40',
  danger:    'text-ink bg-cardio hover:opacity-90 disabled:opacity-40',
  outline:   'bg-transparent text-mid border border-edge hover-glow',
  ghost:     'bg-transparent text-mid hover:bg-gray-100',
};

const SIZES = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2 text-sm',
  lg: 'px-5 py-2.5 text-base',
};

export default function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  type = 'button',
  children,
  ...rest
}) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
