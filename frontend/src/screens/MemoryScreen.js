// src/screens/MemoryScreen.tsx → window.RPScreens.MemoryScreen

(function() {
  const { useState, useEffect } = React;
  const { EmptyState, ErrorBanner, LoadingWrap, ConfirmDialog, Modal } = window.RPComponents;
  const { useToast } = window.RPComponents;
  const Api = window.RPApi;

  // ---- Edit memory/fact modal ----
  function EditMemoryModal({ memory, conversationId, onSave, onClose }) {
    const [form, setForm] = useState({
      content: memory.content || '',
      pinned: memory.pinned || false,
      forgotten: memory.forgotten ?? memory.suppressed ?? false,
      restrictedToNone: Array.isArray(memory.known_by) && memory.known_by.length === 0,
      known_by: Array.isArray(memory.known_by) ? memory.known_by.join(', ') : '',
    });
    const [saving, setSaving] = useState(false);
    const [err, setErr]       = useState(null);

    function set(k, v) { setForm(f => ({ ...f, [k]: v })); }

    async function handleSave(e) {
      e.preventDefault();
      setSaving(true);
      setErr(null);
      // PATCH resets omitted control fields to defaults, so send the complete control state
      const knownArr = form.known_by.split(',').map(s => s.trim()).filter(Boolean);
      const payload = {
        content: form.content.trim(),
        pinned: Boolean(form.pinned),
        forgotten: Boolean(form.forgotten),
        known_by: form.restrictedToNone ? [] : (form.known_by.trim() ? knownArr : null), // null is unrestricted, [] is restricted to none
      };
      try {
        const updated = await Api.patchMemory(conversationId, memory.id, payload);
        onSave(updated);
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
        saving ? 'Saving...' : 'Update Memory')
    );

    return React.createElement(
      Modal, { title: 'Edit Memory', onClose, footer },
      React.createElement(ErrorBanner, { error: err }),
      React.createElement('div', { className: 'warning-box' },
        'Forgetting a memory changes generation context, not stored chat history.'),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'mem-content' }, 'Content'),
        React.createElement('textarea', { id: 'mem-content', className: 'textarea', value: form.content, onChange: e => set('content', e.target.value), rows: 4, disabled: saving })
      ),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'mem-known' }, 'Known By (comma-separated names, empty = unrestricted)'),
        React.createElement('input', { id: 'mem-known', className: 'input', value: form.known_by, onChange: e => set('known_by', e.target.value), disabled: saving })
      ),
      React.createElement('label', { className: 'checkbox-label' },
        React.createElement('input', { type: 'checkbox', checked: form.restrictedToNone, onChange: e => set('restrictedToNone', e.target.checked), disabled: saving }),
        'Hidden from every character'
      ),
      React.createElement('label', { className: 'checkbox-label', style: { marginBottom: '8px' } },
        React.createElement('input', { type: 'checkbox', checked: form.pinned, onChange: e => set('pinned', e.target.checked), disabled: saving }),
        'Pinned (always included in context)'
      ),
      React.createElement('label', { className: 'checkbox-label' },
        React.createElement('input', { type: 'checkbox', checked: form.forgotten, onChange: e => set('forgotten', e.target.checked), disabled: saving }),
        'Forgotten / Suppressed (excluded from generation context)'
      )
    );
  }

  // ---- Add note form ----
  function AddNoteForm({ conversationId, onAdd }) {
    const toast = useToast();
    const [content, setContent] = useState('');
    const [pinned, setPinned]   = useState(false);
    const [saving, setSaving]   = useState(false);
    const [err, setErr]         = useState(null);

    async function handleAdd(e) {
      e.preventDefault();
      if (!content.trim()) return;
      setSaving(true);
      setErr(null);
      try {
        const note = await Api.addNote(conversationId, { content: content.trim(), pinned });
        setContent('');
        setPinned(false);
        onAdd(note);
        toast.success('Note added.');
      } catch (e) {
        setErr(e);
      } finally {
        setSaving(false);
      }
    }

    return React.createElement(
      'div',
      { className: 'card', style: { marginBottom: '16px' } },
      React.createElement(
        'div',
        { className: 'card-body' },
        React.createElement('h4', { style: { marginBottom: '8px' } }, 'Add Note'),
        React.createElement(ErrorBanner, { error: err }),
        React.createElement('div', { className: 'input-group' },
          React.createElement('textarea', {
            className: 'textarea', value: content, onChange: e => setContent(e.target.value),
            placeholder: 'Write a note about this story...', rows: 3, disabled: saving
          })
        ),
        React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' } },
          React.createElement('label', { className: 'checkbox-label' },
            React.createElement('input', { type: 'checkbox', checked: pinned, onChange: e => setPinned(e.target.checked) }),
            'Pin note'
          ),
          React.createElement('button', { className: 'btn-primary btn-sm', onClick: handleAdd, disabled: saving || !content.trim() },
            saving ? 'Adding...' : 'Add Note')
        )
      )
    );
  }

  // ---- Main MemoryScreen ----
  function MemoryScreen({ conversationId, onBack }) {
    const toast = useToast();
    const [facts, setFacts]         = useState([]);
    const [notes, setNotes]         = useState([]);
    const [loading, setLoading]     = useState(true);
    const [error, setError]         = useState(null);
    const [editModal, setEditModal] = useState(null); // memory obj
    const [deleteNote, setDeleteNote] = useState(null);
    const [tab, setTab]             = useState('facts');

    useEffect(() => {
      Api.getMemories(conversationId)
        .then(data => {
          setFacts(data.facts || data.memories || []);
          setNotes(data.notes || []);
        })
        .catch(err => setError(err))
        .finally(() => setLoading(false));
    }, [conversationId]);

    function handleMemorySave(updated) {
      setFacts(prev => prev.map(f => f.id === updated.id ? updated : f));
      setEditModal(null);
      toast.success('Memory updated.');
    }

    async function handleDeleteNote(id) {
      try {
        await Api.deleteNote(conversationId, id);
        setNotes(prev => prev.filter(n => n.id !== id));
        setDeleteNote(null);
        toast.success('Note deleted.');
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
        { className: 'back-row' },
        React.createElement('button', { className: 'btn-ghost', onClick: onBack }, '← Back'),
        React.createElement('h2', { style: { margin: 0 } }, 'Memories')
      ),

      React.createElement(ErrorBanner, { error, onDismiss: () => setError(null) }),

      React.createElement(
        'div',
        { className: 'tabs' },
        React.createElement('button', { className: `tab-btn ${tab === 'facts' ? 'active' : ''}`, onClick: () => setTab('facts') }, `Facts (${facts.length})`),
        React.createElement('button', { className: `tab-btn ${tab === 'notes' ? 'active' : ''}`, onClick: () => setTab('notes') }, `Notes (${notes.length})`)
      ),

      // Facts tab
      tab === 'facts' && React.createElement(
        'div',
        { className: 'tab-panel' },
        facts.length === 0
          ? React.createElement(EmptyState, { message: 'No memories recorded yet.' })
          : facts.map(f => React.createElement(
              'div',
              { key: f.id, className: 'list-item', style: { flexDirection: 'column', alignItems: 'flex-start', gap: '6px' } },
              React.createElement(
                'div',
                { style: { display: 'flex', width: '100%', justifyContent: 'space-between', alignItems: 'flex-start' } },
                React.createElement('span', { style: { flex: 1, fontSize: '0.9375rem', opacity: f.forgotten ? 0.5 : 1, fontStyle: f.forgotten ? 'italic' : 'normal' } }, f.content),
                React.createElement('button', { className: 'btn-secondary btn-sm', onClick: () => setEditModal(f), style: { flexShrink: 0, marginLeft: '8px' } }, 'Edit')
              ),
              React.createElement(
                'div',
                { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } },
                f.pinned && React.createElement('span', { className: 'badge badge-info' }, 'Pinned'),
                f.forgotten && React.createElement('span', { className: 'badge badge-warning' }, 'Suppressed'),
                f.known_by && f.known_by.length > 0 && React.createElement('span', { style: { fontSize: '0.75rem', color: 'var(--color-text-muted)' } },
                  `Known by: ${f.known_by.join(', ')}`)
              )
            ))
      ),

      // Notes tab
      tab === 'notes' && React.createElement(
        'div',
        { className: 'tab-panel' },
        React.createElement(AddNoteForm, { conversationId, onAdd: n => setNotes(prev => [...prev, n]) }),
        notes.length === 0
          ? React.createElement(EmptyState, { message: 'No notes yet.' })
          : notes.map(n => React.createElement(
              'div',
              { key: n.id, className: 'list-item', style: { flexDirection: 'column', alignItems: 'flex-start', gap: '4px' } },
              React.createElement(
                'div',
                { style: { display: 'flex', width: '100%', justifyContent: 'space-between', alignItems: 'flex-start' } },
                React.createElement('span', { style: { flex: 1, fontSize: '0.9375rem' } }, n.content),
                React.createElement('button', {
                  className: 'btn-ghost btn-sm',
                  style: { color: 'var(--color-danger)', flexShrink: 0 },
                  onClick: () => setDeleteNote(n)
                }, 'Delete')
              ),
              n.pinned && React.createElement('span', { className: 'badge badge-info' }, 'Pinned')
            ))
      ),

      editModal && React.createElement(EditMemoryModal, {
        memory: editModal,
        conversationId,
        onSave: handleMemorySave,
        onClose: () => setEditModal(null),
      }),

      deleteNote && React.createElement(ConfirmDialog, {
        message: 'Delete this note?',
        confirmLabel: 'Delete',
        danger: true,
        onConfirm: () => handleDeleteNote(deleteNote.id),
        onCancel: () => setDeleteNote(null),
      })
    );
  }

  if (!window.RPScreens) window.RPScreens = {};
  window.RPScreens.MemoryScreen = MemoryScreen;
})();
