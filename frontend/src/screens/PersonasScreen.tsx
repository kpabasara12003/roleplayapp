// src/screens/PersonasScreen.tsx → window.RPScreens.PersonasScreen

(function() {
  const { useState, useEffect } = React;
  const { EmptyState, ErrorBanner, LoadingWrap, ConfirmDialog, Modal } = window.RPComponents;
  const { useToast } = window.RPComponents;
  const Api = window.RPApi;

  function PersonaModal({ persona, onSave, onClose }) {
    const [form, setForm] = useState({
      name: persona?.name || '',
      background: persona?.background || '',
      personality: persona?.personality || '',
      appearance: persona?.appearance || '',
    });
    const [saving, setSaving] = useState(false);
    const [err, setErr]       = useState(null);

    function set(k, v) { setForm(f => ({ ...f, [k]: v })); }

    async function handleSave(e) {
      e.preventDefault();
      if (!form.name.trim()) { setErr({ message: 'Name is required.' }); return; }
      setSaving(true);
      setErr(null);
      try {
        let result;
        if (persona?.id) {
          result = await Api.updatePersona(persona.id, form);
        } else {
          result = await Api.createPersona(form);
        }
        onSave(result);
      } catch (e) {
        setErr(e);
      } finally {
        setSaving(false);
      }
    }

    const footer = React.createElement(
      React.Fragment, null,
      React.createElement('button', { className: 'btn-secondary', onClick: onClose, disabled: saving }, 'Cancel'),
      React.createElement('button', { className: 'btn-primary', onClick: handleSave, disabled: saving },
        saving ? 'Saving...' : (persona?.id ? 'Update Persona' : 'Create Persona'))
    );

    return React.createElement(
      Modal, { title: persona?.id ? 'Edit Persona' : 'New Persona', onClose, footer },
      React.createElement(ErrorBanner, { error: err }),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'p-name' }, 'Name'),
        React.createElement('input', { id: 'p-name', className: 'input', value: form.name, onChange: e => set('name', e.target.value), autoFocus: true })
      ),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'p-appearance' }, 'Appearance'),
        React.createElement('input', { id: 'p-appearance', className: 'input', value: form.appearance, onChange: e => set('appearance', e.target.value) })
      ),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'p-personality' }, 'Personality'),
        React.createElement('textarea', { id: 'p-personality', className: 'textarea', value: form.personality, onChange: e => set('personality', e.target.value), rows: 3 })
      ),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'p-background' }, 'Background'),
        React.createElement('textarea', { id: 'p-background', className: 'textarea', value: form.background, onChange: e => set('background', e.target.value), rows: 3 })
      )
    );
  }

  function PersonasScreen() {
    const toast = useToast();
    const [personas, setPersonas]   = useState([]);
    const [loading, setLoading]     = useState(true);
    const [error, setError]         = useState(null);
    const [modal, setModal]         = useState(null); // null | 'new' | persona obj
    const [deleteConfirm, setDeleteConfirm] = useState(null);

    useEffect(() => {
      Api.getPersonas()
        .then(data => setPersonas(Array.isArray(data) ? data : (data.personas || data.items || [])))
        .catch(err => setError(err))
        .finally(() => setLoading(false));
    }, []);

    function handleSave(p) {
      if (modal === 'new') setPersonas(prev => [...prev, p]);
      else setPersonas(prev => prev.map(x => x.id === p.id ? p : x));
      setModal(null);
      toast.success('Persona saved.');
    }

    async function handleDelete(id) {
      try {
        await Api.deletePersona(id);
        setPersonas(prev => prev.filter(p => p.id !== id));
        setDeleteConfirm(null);
        toast.success('Persona deleted.');
      } catch (err) {
        toast.error(window.RPComponents.formatError(err));
      }
    }

    if (loading) return React.createElement(LoadingWrap, null);

    return React.createElement(
      'div',
      null,
      React.createElement(
        'div',
        { className: 'page-header' },
        React.createElement('h2', { className: 'page-title' }, 'Personas'),
        React.createElement('button', { className: 'btn-primary', onClick: () => setModal('new') }, 'New Persona')
      ),

      React.createElement('div', { className: 'info-box' },
        'Note: changing a persona does not rewrite ongoing stories. Changes apply to new stories only.'),

      React.createElement(ErrorBanner, { error, onDismiss: () => setError(null) }),

      personas.length === 0
        ? React.createElement(EmptyState, {
            message: 'No personas yet. Create one to customize how you appear in stories.',
            action: { label: 'New Persona', onClick: () => setModal('new') }
          })
        : React.createElement(
            'div',
            { style: { display: 'flex', flexDirection: 'column', gap: '8px' } },
            personas.map(p => React.createElement(
              'div',
              { key: p.id, className: 'list-item' },
              React.createElement(
                'div',
                { style: { flex: 1 } },
                React.createElement('div', { style: { fontWeight: 600 } }, p.name),
                React.createElement('div', { style: { fontSize: '0.8125rem', color: 'var(--color-text-muted)', marginTop: '2px' } },
                  p.appearance || p.personality || 'No details')
              ),
              React.createElement(
                'div',
                { className: 'list-item-actions' },
                React.createElement('button', { className: 'btn-secondary btn-sm', onClick: () => setModal(p) }, 'Edit'),
                React.createElement('button', {
                  className: 'btn-ghost btn-sm',
                  style: { color: 'var(--color-danger)' },
                  onClick: () => setDeleteConfirm(p)
                }, 'Delete')
              )
            ))
          ),

      modal && React.createElement(PersonaModal, {
        persona: modal === 'new' ? null : modal,
        onSave: handleSave,
        onClose: () => setModal(null),
      }),

      deleteConfirm && React.createElement(ConfirmDialog, {
        message: `Delete persona "${deleteConfirm.name}"?`,
        confirmLabel: 'Delete',
        danger: true,
        onConfirm: () => handleDelete(deleteConfirm.id),
        onCancel: () => setDeleteConfirm(null),
      })
    );
  }

  if (!window.RPScreens) window.RPScreens = {};
  window.RPScreens.PersonasScreen = PersonasScreen;
})();
