// src/components/LoadingSpinner.tsx → window.RPComponents.LoadingSpinner

(function() {
  function LoadingSpinner({ size = 'md', label = 'Loading...' }) {
    return React.createElement(
      'span',
      {
        className: `spinner spinner-${size}`,
        role: 'status',
        'aria-label': label,
        title: label,
      }
    );
  }

  function LoadingWrap({ size = 'md', label }) {
    return React.createElement(
      'div',
      { className: 'spinner-wrap' },
      React.createElement(LoadingSpinner, { size, label })
    );
  }

  if (!window.RPComponents) window.RPComponents = {};
  window.RPComponents.LoadingSpinner = LoadingSpinner;
  window.RPComponents.LoadingWrap = LoadingWrap;
})();
