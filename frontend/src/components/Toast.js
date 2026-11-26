// src/components/Toast.tsx → window.RPComponents.Toast + window.useToast
// Stack-based toast manager with auto-dismiss

(function() {
  const { useState, useCallback, useContext, createContext, useRef } = React;

  const ToastContext = createContext(null);

  let _toastId = 0;

  function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);
    const timersRef = useRef({});

    const dismiss = useCallback((id) => {
      setToasts(prev => prev.filter(t => t.id !== id));
      if (timersRef.current[id]) {
        clearTimeout(timersRef.current[id]);
        delete timersRef.current[id];
      }
    }, []);

    const addToast = useCallback((type, message, duration) => {
      const id = ++_toastId;
      const dur = duration ?? 3500;
      setToasts(prev => [...prev, { id, type, message }]);
      if (dur > 0) {
        timersRef.current[id] = setTimeout(() => dismiss(id), dur);
      }
      return id;
    }, [dismiss]);

    const toast = useCallback({
      success: (msg, dur) => addToast('success', msg, dur),
      error:   (msg, dur) => addToast('error', msg, dur),
      info:    (msg, dur) => addToast('info', msg, dur),
    }, [addToast]);

    // Actually make it a plain object
    const toastFns = {
      success: (msg, dur) => addToast('success', msg, dur),
      error:   (msg, dur) => addToast('error', msg, dur),
      info:    (msg, dur) => addToast('info', msg, dur),
      dismiss,
    };

    const LABELS = { success: 'Done:', error: 'Error:', info: 'Info:' };

    return React.createElement(
      ToastContext.Provider,
      { value: toastFns },
      children,
      React.createElement(
        'div',
        { className: 'toast-container', role: 'region', 'aria-live': 'polite', 'aria-label': 'Notifications' },
        toasts.map(t =>
          React.createElement(
            'div',
            {
              key: t.id,
              className: `toast toast-${t.type}`,
              role: 'alert',
            },
            React.createElement('span', { className: 'toast-label' }, LABELS[t.type] || ''),
            React.createElement('span', null, t.message),
            React.createElement(
              'button',
              {
                className: 'btn-ghost btn-sm',
                onClick: () => dismiss(t.id),
                'aria-label': 'Dismiss',
                style: { marginLeft: 'auto', padding: '0 4px', flexShrink: 0 },
              },
              'x'
            )
          )
        )
      )
    );
  }

  function useToast() {
    const ctx = useContext(ToastContext);
    if (!ctx) throw new Error('useToast must be used within ToastProvider');
    return ctx;
  }

  if (!window.RPComponents) window.RPComponents = {};
  window.RPComponents.ToastProvider = ToastProvider;
  window.RPComponents.useToast = useToast;
  window.useToast = useToast; // global convenience
})();
