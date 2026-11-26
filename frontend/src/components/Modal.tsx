// src/components/Modal.tsx → window.RPComponents.Modal

(function() {
  const { useEffect, useRef } = React;

  function Modal({ title, children, onClose, footer, wide, busy = false }) {
    const overlayRef = useRef(null);
    const modalRef   = useRef(null);

    // Escape to close
    useEffect(() => {
      function handleKeyDown(e) {
        if (!busy && e.key === 'Escape') onClose && onClose();
      }
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }, [onClose,busy]);

    // Focus trap
    useEffect(() => {
      const modal = modalRef.current;
      if (!modal) return;
      const previousFocus = document.activeElement;
      const getFocusable = () => [...modal.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )].filter(el => !el.disabled && el.getClientRects().length);
      const focusable = getFocusable();
      if (focusable.length) focusable[0].focus();

      function handleTab(e) {
        if (e.key !== 'Tab') return;
        const current = getFocusable();
        if (!current.length) { e.preventDefault(); return; }
        const first = current[0];
        const last = current[current.length - 1];
        if (e.shiftKey) {
          if (document.activeElement === first) { e.preventDefault(); last.focus(); }
        } else {
          if (document.activeElement === last)  { e.preventDefault(); first.focus(); }
        }
      }
      modal.addEventListener('keydown', handleTab);
      return () => { modal.removeEventListener('keydown', handleTab); if (previousFocus?.isConnected) previousFocus.focus(); };
    }, []);

    function handleOverlayClick(e) {
      if (!busy && e.target === overlayRef.current) onClose && onClose();
    }

    return React.createElement(
      'div',
      {
        className: 'modal-overlay',
        ref: overlayRef,
        onClick: handleOverlayClick,
        role: 'dialog',
        'aria-modal': 'true',
        'aria-label': title,
      },
      React.createElement(
        'div',
        {
          className: 'modal',
          ref: modalRef,
          style: wide ? { maxWidth: '720px' } : {},
        },
        // Header
        React.createElement(
          'div',
          { className: 'modal-header' },
          React.createElement('h3', null, title),
          onClose && React.createElement(
            'button',
            {
              className: 'modal-close-btn',
              onClick: onClose,
              'aria-label': 'Close dialog', disabled: busy,
            },
            'x'
          )
        ),
        // Body
        React.createElement('div', { className: 'modal-body' }, children),
        // Footer
        footer && React.createElement('div', { className: 'modal-footer' }, footer)
      )
    );
  }

  if (!window.RPComponents) window.RPComponents = {};
  window.RPComponents.Modal = Modal;
})();
