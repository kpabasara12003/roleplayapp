// Generated from components/ConfirmDialog.tsx; source-sha256: 5f452c2aa8fa216fdd1c2047731ff2bd257dd22bb2fbabda87b770c6c4fca678
"use strict";
// src/components/ConfirmDialog.tsx → window.RPComponents.ConfirmDialog
(function () {
    function ConfirmDialog({ message, confirmLabel, cancelLabel, onConfirm, onCancel, danger }) {
        const Modal = (window.RPComponents && window.RPComponents.Modal) || 'div';
        const footer = React.createElement(React.Fragment, null, React.createElement('button', { className: 'btn-secondary', onClick: onCancel }, cancelLabel || 'Cancel'), React.createElement('button', {
            className: danger ? 'btn-danger' : 'btn-primary',
            onClick: onConfirm,
        }, confirmLabel || 'Confirm'));
        return React.createElement(Modal, { title: 'Confirm', onClose: onCancel, footer }, React.createElement('p', null, message));
    }
    if (!window.RPComponents)
        window.RPComponents = {};
    window.RPComponents.ConfirmDialog = ConfirmDialog;
})();
