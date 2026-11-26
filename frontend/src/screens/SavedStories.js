// src/screens/SavedStories.tsx → window.RPScreens.SavedStories

(function() {
  const { useState, useEffect, useCallback } = React;
  const { EmptyState, ErrorBanner, LoadingWrap, ConfirmDialog, Modal } = window.RPComponents;
  const { useToast } = window.RPComponents;
  const Api = window.RPApi;

  function formatDate(d) {
    if (!d) return '';
    try { return new Date(d).toLocaleString(); } catch { return d; }
  }

  function RenameModal({ conversation, onSave, onClose }) {
    const [title, setTitle] = useState(conversation.title || '');
    const [saving, setSaving] = useState(false);
    const [err, setErr]       = useState(null);

    async function handleSave() {
      setSaving(true);
      setErr(null);
      try {
        const updated = await Api.updateConversation(conversation.id, { title: title.trim() });
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
      React.createElement('button', { className: 'btn-primary', onClick: handleSave, disabled: saving || !title.trim() },
        saving ? 'Saving...' : 'Rename')
    );

    return React.createElement(
      Modal, { title: 'Rename Story', onClose, footer },
      React.createElement(ErrorBanner, { error: err }),
      React.createElement('div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'rename-title' }, 'Title'),
        React.createElement('input', {
          id: 'rename-title', className: 'input', value: title,
          onChange: e => setTitle(e.target.value), autoFocus: true
        })
      )
    );
  }

  function SavedStories({ onNavigate }) {
    const toast = useToast();
    const [conversations, setConversations] = useState([]);
    const [loading, setLoading]     = useState(true);
    const [error, setError]         = useState(null);
    const [filter, setFilter]       = useState('active'); // 'active' | 'archived'
    const [lastId, setLastId]       = useState(null);
    const [hasMore, setHasMore]     = useState(false);
    const [renameModal, setRenameModal]   = useState(null); // conversation obj
    const [archiveConfirm, setArchiveConfirm] = useState(null);
    const [restoreConfirm, setRestoreConfirm] = useState(null);

    const load = useCallback(async (before, replace) => {
      setLoading(true);
      setError(null);
      try {
        const params = { limit: 30, archived: filter === 'archived' };
        if (before) params.before = before;
        const data = await Api.getConversations(params);
        const items = Array.isArray(data) ? data : (data.conversations || data.items || []);
        if (replace || !before) setConversations(items);
        else setConversations(prev => [...prev, ...items]);
        setHasMore(items.length === 30);
        if (items.length > 0) setLastId(items[items.length - 1].id);
      } catch (err) {
        setError(err);
      } finally {
        setLoading(false);
      }
    }, [filter]);

    useEffect(() => { load(null, true); }, [load]);

    async function handleArchive(conv) {
      try {
        await Api.updateConversation(conv.id, { archived: true });
        setConversations(prev => prev.filter(c => c.id !== conv.id));
        setArchiveConfirm(null);
        toast.success('Story archived.');
      } catch (err) {
        toast.error(window.RPComponents.formatError(err));
      }
    }

    async function handleRestore(conv) {
      try {
        await Api.updateConversation(conv.id, { archived: false });
        setConversations(prev => prev.filter(c => c.id !== conv.id));
        setRestoreConfirm(null);
        toast.success('Story restored.');
      } catch (err) {
        toast.error(window.RPComponents.formatError(err));
      }
    }

    function handleRenameSuccess(updated) {
      setConversations(prev => prev.map(c => c.id === updated.id ? updated : c));
      setRenameModal(null);
      toast.success('Story renamed.');
    }

    function statusBadge(status) {
      const cls = status === 'active' ? 'badge-success' : status === 'completed' ? 'badge-info' : 'badge-warning';
      return React.createElement('span', { className: `badge ${cls}` }, status);
    }

    return React.createElement(
      'div',
      null,
      React.createElement(
        'div',
        { className: 'page-header' },
        React.createElement('h2', { className: 'page-title' }, 'Saved Stories'),
        React.createElement(
          'div',
          { style: { display: 'flex', gap: '8px' } },
          React.createElement('button', {
            className: `tab-btn ${filter === 'active' ? 'active' : ''}`,
            style: { border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', borderBottom: filter === 'active' ? '' : '1px solid var(--color-border)' },
            onClick: () => setFilter('active')
          }, 'Active'),
          React.createElement('button', {
            className: `tab-btn ${filter === 'archived' ? 'active' : ''}`,
            style: { border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', borderBottom: filter === 'archived' ? '' : '1px solid var(--color-border)' },
            onClick: () => setFilter('archived')
          }, 'Archived')
        )
      ),

      React.createElement(ErrorBanner, { error, onDismiss: () => setError(null) }),

      loading && conversations.length === 0
        ? React.createElement(LoadingWrap, null)
        : conversations.length === 0
        ? React.createElement(EmptyState, {
            message: filter === 'archived' ? 'No archived stories.' : 'No saved stories yet. Start one from the Catalog.',
            action: filter === 'active' ? { label: 'Go to Catalog', onClick: () => onNavigate('Catalog') } : null,
          })
        : React.createElement(
            'div',
            { style: { display: 'flex', flexDirection: 'column', gap: '8px' } },
            conversations.map(conv => React.createElement(
              'div',
              { key: conv.id, className: 'list-item' },
              React.createElement(
                'div',
                { style: { flex: 1, minWidth: 0 } },
                React.createElement(
                  'div',
                  { style: { display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' } },
                  React.createElement('span', { style: { fontWeight: 600 } }, conv.title || 'Untitled Story'),
                  statusBadge(conv.status)
                ),
                React.createElement(
                  'div',
                  { style: { fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '2px' } },
                  `Updated ${formatDate(conv.updated_at)}`,
                  conv.parent_conversation_id && React.createElement(
                    'span',
                    null,
                    ' · ',
                    React.createElement('a', {
                      href: '#',
                      style: { color: 'var(--color-text-muted)' },
                      onClick: e => { e.preventDefault(); onNavigate('ChatScreen', { conversationId: conv.parent_conversation_id }); }
                    }, 'Parent branch')
                  )
                )
              ),
              React.createElement(
                'div',
                { className: 'list-item-actions' },
                // Open — NEVER calls /chat/start
                React.createElement('button', {
                  className: 'btn-primary btn-sm',
                  onClick: () => onNavigate('ChatScreen', { conversationId: conv.id })
                }, 'Open'),
                React.createElement('button', {
                  className: 'btn-secondary btn-sm',
                  onClick: () => setRenameModal(conv)
                }, 'Rename'),
                filter === 'active'
                  ? React.createElement('button', {
                      className: 'btn-ghost btn-sm',
                      style: { color: 'var(--color-danger)' },
                      onClick: () => setArchiveConfirm(conv)
                    }, 'Archive')
                  : React.createElement('button', {
                      className: 'btn-ghost btn-sm',
                      onClick: () => setRestoreConfirm(conv)
                    }, 'Restore')
              )
            ))
          ),

      hasMore && !loading && React.createElement(
        'div',
        { style: { textAlign: 'center', marginTop: '16px' } },
        React.createElement('button', { className: 'btn-secondary', onClick: () => load(lastId) }, 'Load More')
      ),

      renameModal && React.createElement(RenameModal, {
        conversation: renameModal,
        onSave: handleRenameSuccess,
        onClose: () => setRenameModal(null),
      }),

      archiveConfirm && React.createElement(ConfirmDialog, {
        message: `Archive "${archiveConfirm.title || 'this story'}"? You can restore it later.`,
        confirmLabel: 'Archive',
        danger: true,
        onConfirm: () => handleArchive(archiveConfirm),
        onCancel: () => setArchiveConfirm(null),
      }),

      restoreConfirm && React.createElement(ConfirmDialog, {
        message: `Restore "${restoreConfirm.title || 'this story'}"?`,
        confirmLabel: 'Restore',
        onConfirm: () => handleRestore(restoreConfirm),
        onCancel: () => setRestoreConfirm(null),
      })
    );
  }

  if (!window.RPScreens) window.RPScreens = {};
  window.RPScreens.SavedStories = SavedStories;
})();
