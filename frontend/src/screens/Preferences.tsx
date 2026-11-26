// src/screens/Preferences.tsx → window.RPScreens.Preferences

(function() {
  const { useState, useEffect } = React;
  const { ErrorBanner, LoadingWrap } = window.RPComponents;
  const { useToast } = window.RPComponents;
  const Api = window.RPApi;

  function Preferences() {
    const toast = useToast();
    const [prefs, setPrefs] = useState({
      language: 'en',
      response_length: 'medium',
      perspective: 'third',
      pacing: 'balanced',
      formatting: 'asterisks',
      intensity: 'balanced',
    });
    const [loading, setLoading] = useState(true);
    const [saving, setSaving]   = useState(false);
    const [error, setError]     = useState(null);

    useEffect(() => {
      Api.getPreferences().then(data => {
        if (data) setPrefs(p => ({ ...p, ...data }));
      }).catch(err => setError(err)).finally(() => setLoading(false));
    }, []);

    function set(k, v) { setPrefs(p => ({ ...p, [k]: v })); }

    async function handleSave(e) {
      e.preventDefault();
      setSaving(true);
      setError(null);
      try {
        await Api.updatePreferences(prefs);
        toast.success('Preferences saved.');
      } catch (err) {
        setError(err);
      } finally {
        setSaving(false);
      }
    }

    if (loading) return React.createElement(LoadingWrap, null);

    function SelectField({ label, id, value, onChange, options }) {
      return React.createElement(
        'div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: id }, label),
        React.createElement(
          'select', { id, className: 'select', value, onChange: e => onChange(e.target.value), disabled: saving },
          options.map(([v, l]) => React.createElement('option', { key: v, value: v }, l))
        )
      );
    }

    return React.createElement(
      'div',
      null,
      React.createElement('div', { className: 'page-header' }, React.createElement('h2', { className: 'page-title' }, 'Preferences')),
      React.createElement(ErrorBanner, { error, onDismiss: () => setError(null) }),
      React.createElement(
        'form',
        { onSubmit: handleSave, style: { maxWidth: '480px' } },

        React.createElement(
          'div', { className: 'input-group' },
          React.createElement('label', { className: 'label', htmlFor: 'pref-lang' }, 'Language'),
          React.createElement('input', {
            id: 'pref-lang', className: 'input', type: 'text',
            value: prefs.language || '', onChange: e => set('language', e.target.value),
            disabled: saving, placeholder: 'e.g. en, fr, es'
          })
        ),

        React.createElement(SelectField, {
          label: 'Response Length', id: 'pref-length', value: prefs.response_length || 'medium',
          onChange: v => set('response_length', v),
          options: [['short', 'Short'], ['medium', 'Medium'], ['long', 'Long']]
        }),

        React.createElement(SelectField, {
          label: 'Perspective', id: 'pref-perspective', value: prefs.perspective || 'third',
          onChange: v => set('perspective', v),
          options: [['first', 'First person (I do...)'], ['third', 'Third person (You do...)']]
        }),

        React.createElement(SelectField, {
          label: 'Pacing', id: 'pref-pacing', value: prefs.pacing || 'balanced',
          onChange: v => set('pacing', v),
          options: [['slow', 'Slow (detailed)'], ['balanced', 'Balanced'], ['fast', 'Fast (action-focused)']]
        }),

        React.createElement(SelectField, {
          label: 'Formatting', id: 'pref-formatting', value: prefs.formatting || 'asterisks',
          onChange: v => set('formatting', v),
          options: [['asterisks', 'Asterisks (*action*)'], ['plain', 'Plain text']]
        }),

        React.createElement(SelectField, {
          label: 'Intensity', id: 'pref-intensity', value: prefs.intensity || 'balanced',
          onChange: v => set('intensity', v),
          options: [['gentle', 'Gentle'], ['balanced', 'Balanced'], ['dramatic', 'Dramatic']]
        }),

        React.createElement(
          'button',
          { type: 'submit', className: 'btn-primary', disabled: saving },
          saving ? 'Saving...' : 'Save Preferences'
        )
      )
    );
  }

  if (!window.RPScreens) window.RPScreens = {};
  window.RPScreens.Preferences = Preferences;
})();
