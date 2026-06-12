export default function Card({ children, className = '', title, action }) {
  return (
    <div className={`holo-panel ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: '1px solid var(--edge)' }}>
          {title && <h2 className="text-base font-mono font-bold text-hi tracking-wide">{title}</h2>}
          {action}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}
