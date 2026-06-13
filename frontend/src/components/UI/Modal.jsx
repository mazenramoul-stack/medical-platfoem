import { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';

import { useI18n } from '../../i18n/LanguageContext.jsx';

// Interactive elements we cycle through when trapping Tab focus.
const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'textarea:not([disabled])',
  'input:not([disabled])', 'select:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(', ');

export default function Modal({ open, onClose, title, children, footer }) {
  const { t } = useI18n();
  const dialogRef = useRef(null);
  const titleId = useId();
  // Keep the latest onClose without re-running the focus effect (parents often
  // pass a fresh arrow each render, which would otherwise re-trap focus).
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; });

  // Accessibility while open: move focus in, trap Tab, Escape to close, and
  // restore focus to the triggering element on close.
  useEffect(() => {
    if (!open) return undefined;
    const node = dialogRef.current;
    const previouslyFocused = document.activeElement;

    const focusables = () =>
      node ? Array.from(node.querySelectorAll(FOCUSABLE)).filter((el) => el.offsetParent !== null) : [];

    node?.focus(); // dialog container (tabIndex=-1) — screen reader announces it

    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        onCloseRef.current?.();
        return;
      }
      if (e.key !== 'Tab' || !node) return;
      const items = focusables();
      if (items.length === 0) { e.preventDefault(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      const inside = node.contains(active) && items.includes(active);
      if (e.shiftKey) {
        if (!inside || active === first) { e.preventDefault(); last.focus(); }
      } else if (!inside || active === last) {
        e.preventDefault(); first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      if (previouslyFocused && typeof previouslyFocused.focus === 'function') previouslyFocused.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="bg-white rounded-xl shadow-xl w-full max-w-lg outline-none"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <h2 id={titleId} className="text-base font-semibold text-gray-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close')}
            className="text-gray-500 hover:text-gray-700"
          >
            <X size={18} />
          </button>
        </div>
        <div className="p-5">{children}</div>
        {footer && <div className="px-5 py-4 border-t border-gray-200 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}
