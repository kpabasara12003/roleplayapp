// src/components/EmptyState.tsx → window.RPComponents.EmptyState

(function() {
  function EmptyState({ message, action }) {
    return React.createElement(
      'div',
      { className: 'empty-state' },
      React.createElement('p', { className: 'empty-state-message' }, message || 'Nothing here yet.'),
      action
        ? React.createElement(
            'button',
            { className: 'btn-secondary btn-sm', onClick: action.onClick },
            action.label
          )
        : null
    );
  }

  if (!window.RPComponents) window.RPComponents = {};
  window.RPComponents.EmptyState = EmptyState;
})();
