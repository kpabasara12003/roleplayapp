// src/components/ErrorBanner.tsx → window.RPComponents.ErrorBanner

(function() {
  const { useState } = React;

  function formatError(error) {
    if (!error) return 'An unknown error occurred.';
    if (typeof error === 'string') return error;
    if (error.fieldErrors) {
      const fields = Object.entries(error.fieldErrors)
        .map(([k, v]) => `${k}: ${v}`)
        .join('; ');
      return `Validation error — ${fields}`;
    }
    switch (error.status) {
      case 401: return 'Session expired. Please log in again.';
      case 404: return error.detail || 'The requested resource was not found.';
      case 409: return error.detail || 'Conflict — please refresh and try again.';
      case 429: return 'Too many requests. Please wait a moment before retrying.';
      default:  return error.detail || error.message || `Error ${error.status || ''}`.trim();
    }
  }

  function ErrorBanner({ error, onDismiss }) {
    const [dismissed, setDismissed] = useState(null);
    if (!error || dismissed === error) return null;

    const message = formatError(error);

    function handleDismiss() {
      setDismissed(error);
      if (onDismiss) onDismiss();
    }

    return React.createElement(
      'div',
      { className: 'error-banner', role: 'alert' },
      React.createElement('span', null, message),
      React.createElement(
        'button',
        {
          className: 'error-banner-dismiss',
          onClick: handleDismiss,
          'aria-label': 'Dismiss error',
        },
        'x'
      )
    );
  }

  if (!window.RPComponents) window.RPComponents = {};
  window.RPComponents.ErrorBanner = ErrorBanner;
  window.RPComponents.formatError = formatError;
})();
