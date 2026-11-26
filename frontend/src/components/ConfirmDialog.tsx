interface ConfirmDialogProps {
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
  danger?: boolean;
}
// React is supplied by the local vendor script, not an npm module.
declare const React: {
  Fragment: symbol;
  createElement(type: unknown, props: unknown, ...children: unknown[]): unknown;
};
interface Window {
  RPComponents: { Modal?: unknown; ConfirmDialog?: (props: ConfirmDialogProps) => unknown };
}

// src/components/ConfirmDialog.tsx → window.RPComponents.ConfirmDialog

(function() {
  function ConfirmDialog({ message, confirmLabel, cancelLabel, onConfirm, onCancel, danger }: ConfirmDialogProps) {
    const Modal = (window.RPComponents && window.RPComponents.Modal) || 'div';
    const footer = React.createElement(
      React.Fragment,
      null,
      React.createElement(
        'button',
        { className: 'btn-secondary', onClick: onCancel },
        cancelLabel || 'Cancel'
      ),
      React.createElement(
        'button',
        {
          className: danger ? 'btn-danger' : 'btn-primary',
          onClick: onConfirm,
        },
        confirmLabel || 'Confirm'
      )
    );

    return React.createElement(
      Modal,
      { title: 'Confirm', onClose: onCancel, footer },
      React.createElement('p', null, message)
    );
  }

  if (!window.RPComponents) window.RPComponents = {};
  window.RPComponents.ConfirmDialog = ConfirmDialog;
})();
