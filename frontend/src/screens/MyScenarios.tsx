// src/screens/MyScenarios.tsx → window.RPScreens.MyScenarios

(function() {
  const { useState, useEffect, useCallback } = React;
  const { EmptyState, ErrorBanner, ConfirmDialog, LoadingWrap } = window.RPComponents;
  const { getScenarios, createScenario, deleteScenario } = window.RPApi;
  const { useToast } = window.RPComponents;

  function formatDate(d) {
    if (!d) return '';
    try { return new Date(d).toLocaleDateString(); } catch { return d; }
  }

  function MyScenarios({ onNavigate }) {
    const toast = useToast();
    const [scenarios, setScenarios] = useState([]);
    const [loading, setLoading]     = useState(true);
    const [error, setError]         = useState(null);
    const [creating, setCreating]   = useState(false);
    const [newTitle, setNewTitle]   = useState('');
    const [createError, setCreateError] = useState(null);
    const [createLoading, setCreateLoading] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState(null); // { id, title }

    const load = useCallback(async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getScenarios();
        setScenarios(Array.isArray(data) ? data : (data.scenarios || data.items || []));
      } catch (err) {
        setError(err);
      } finally {
        setLoading(false);
      }
    }, []);

    useEffect(() => { load(); }, [load]);

    async function handleCreate(e) {
      e.preventDefault();
      if (createLoading) return;
      if (!newTitle.trim() || newTitle.length>100) {setCreateError({status:422,fieldErrors:{title:'Enter a title with 1–100 characters.'}});return;}
      setCreateLoading(true);
      setCreateError(null);
      try {
        const created = await createScenario({ title: newTitle.trim() });
        setCreating(false);
        setNewTitle('');
        toast.success('Scenario created.');
        onNavigate('ScenarioEditor', { scenarioId: created.id });
      } catch (err) {
        setCreateError(err);
      } finally {
        setCreateLoading(false);
      }
    }

    async function handleDelete(id) {
      try {
        await deleteScenario(id);
        setScenarios(prev => prev.filter(s => s.id !== id));
        setConfirmDelete(null);
        toast.success('Scenario archived.');
      } catch (err) {
        toast.error(window.RPComponents.formatError(err));
      }
    }

    return React.createElement(
      'div',
      null,
      React.createElement(
        'div',
        { className: 'page-header' },
        React.createElement('h2', { className: 'page-title' }, 'My Scenarios'),
        React.createElement(
          'button',
          { className: 'btn-primary', onClick: () => setCreating(true) },
          'New Scenario'
        )
      ),

      React.createElement(ErrorBanner, { error, onDismiss: () => setError(null) }),

      // Create form
      creating && React.createElement(
        'div',
        { className: 'card', style: { marginBottom: '16px' } },
        React.createElement(
          'div',
          { className: 'card-body' },
          React.createElement('h3', { style: { marginBottom: '12px' } }, 'Create New Scenario'),
          React.createElement('p', {className:'editor-help'}, 'Start with a title. Add characters and a situation next. You can leave the world, place and era blank.'),
          React.createElement(ErrorBanner, { error: createError }),
          React.createElement(
            'form',
            { onSubmit: handleCreate },
            React.createElement(
              'div',
              { className: 'input-group' },
              React.createElement('label', { className: 'label', htmlFor: 'new-scenario-title' }, 'Title'),
              React.createElement('input', {
                id: 'new-scenario-title', required:true,maxLength:100,
                className: 'input',
                type: 'text',
                value: newTitle,
                onChange: e => setNewTitle(e.target.value),
                autoFocus: true,
                placeholder: 'Enter scenario title...',
              })
            ),
            React.createElement(
              'div',
              { style: { display: 'flex', gap: '8px' } },
              React.createElement(
                'button',
                { type: 'submit', className: 'btn-primary', disabled: createLoading || !newTitle.trim() },
                createLoading ? 'Creating...' : 'Create'
              ),
              React.createElement(
                'button',
                { type: 'button', className: 'btn-secondary', onClick: () => { setCreating(false); setNewTitle(''); setCreateError(null); } },
                'Cancel'
              )
            )
          )
        )
      ),

      loading
        ? React.createElement(LoadingWrap, null)
        : scenarios.length === 0
        ? React.createElement(EmptyState, {
            message: 'No scenarios yet. Start with a character or situation; a world is optional.',
            action: { label: 'New Scenario', onClick: () => setCreating(true) }
          })
        : React.createElement(
            'div',
            { style: { display: 'flex', flexDirection: 'column', gap: '8px' } },
            scenarios.map(s =>
              React.createElement(
                'div',
                { key: s.id, className: 'list-item' },
                React.createElement(
                  'div',
                  { style: { flex: 1, minWidth: 0 } },
                  React.createElement(
                    'div',
                    { style: { display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' } },
                    React.createElement('span', { style: { fontWeight: 600 } }, s.title),
                    s.published_at && React.createElement('span', { className: 'badge badge-success' }, 'Published'),
                    s.is_public && !s.published_at && React.createElement('span', { className: 'badge badge-info' }, 'Catalog enabled'),
                  ),
                  React.createElement(
                    'div',
                    { style: { fontSize: '0.8125rem', color: 'var(--color-text-muted)', marginTop: '2px' } },
                    [s.place, s.time].filter(Boolean).join(' · ') || 'No setting defined',
                    s.published_at && ` · Published ${formatDate(s.published_at)}`
                  )
                ),
                React.createElement(
                  'div',
                  { className: 'list-item-actions' },
                  React.createElement(
                    'button',
                    {
                      className: 'btn-secondary btn-sm',
                      onClick: () => onNavigate('ScenarioEditor', { scenarioId: s.id }),
                    },
                    'Edit'
                  ),
                  React.createElement(
                    'button',
                    {
                      className: 'btn-ghost btn-sm',
                      style: { color: 'var(--color-danger)' },
                      onClick: () => setConfirmDelete({ id: s.id, title: s.title }),
                    },
                    'Archive'
                  )
                )
              )
            )
          ),

      confirmDelete && React.createElement(ConfirmDialog, {
        message: `Archive "${confirmDelete.title}"? This does not erase players' saved stories.`,
        confirmLabel: 'Archive',
        danger: true,
        onConfirm: () => handleDelete(confirmDelete.id),
        onCancel: () => setConfirmDelete(null),
      })
    );
  }

  if (!window.RPScreens) window.RPScreens = {};
  window.RPScreens.MyScenarios = MyScenarios;
})();
