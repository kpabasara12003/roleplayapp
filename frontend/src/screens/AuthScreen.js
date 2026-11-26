// src/screens/AuthScreen.tsx → window.RPScreens.AuthScreen

(function() {
  const { useState } = React;
  const { ErrorBanner } = window.RPComponents;
  const { register, login } = window.RPApi;
  const { setSession } = window.RPSession;

  function AuthScreen({ onAuth }) {
    const [tab, setTab]           = useState('login');
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading]   = useState(false);
    const [error, setError]       = useState(null);
    const [fieldErrors, setFieldErrors] = useState({});

    async function handleSubmit(e) {
      e.preventDefault();
      setError(null);
      setFieldErrors({});
      if (!username.trim() || !password.trim()) {
        setError('Username and password are required.');
        return;
      }
      setLoading(true);
      try {
        let result;
        if (tab === 'login') {
          result = await login(username.trim(), password);
        } else {
          result = await register(username.trim(), password);
        }
        // result should contain { id, username, api_key }
        const apiKey = result.api_key || result.apiKey;
        const userId = result.id || result.user_id;
        window.RPSession.setSession({ userId, username: result.username || username, apiKey });
        onAuth({ userId, username: result.username || username, apiKey });
      } catch (err) {
        if (err.fieldErrors) {
          setFieldErrors(err.fieldErrors);
          setError(null);
        } else {
          setError(err);
        }
      } finally {
        setLoading(false);
      }
    }

    function switchTab(t) {
      setTab(t);
      setError(null);
      setFieldErrors({});
    }

    return React.createElement(
      'div',
      { className: 'auth-wrap' },
      React.createElement(
        'div',
        { className: 'auth-card' }, React.createElement('span', {className:'eyebrow'}, 'YOUR NEXT CHAPTER'),
        React.createElement(
          'div',
          { className: 'auth-brand' },
          React.createElement('h1', null, 'fable.'),
          React.createElement('p', null, 'A place to become someone else.')
        ),

        // Tabs
        React.createElement(
          'div',
          { className: 'tabs' },
          React.createElement(
            'button',
            { className: `tab-btn ${tab === 'login' ? 'active' : ''}`, onClick: () => switchTab('login') },
            'Log In'
          ),
          React.createElement(
            'button',
            { className: `tab-btn ${tab === 'register' ? 'active' : ''}`, onClick: () => switchTab('register') },
            'Register'
          )
        ),

        React.createElement(ErrorBanner, { error }),

        React.createElement(
          'form',
          { onSubmit: handleSubmit },

          // Username
          React.createElement(
            'div',
            { className: 'input-group' },
            React.createElement('label', { className: 'label', htmlFor: 'auth-username' }, 'Username'),
            React.createElement('input', {
              id: 'auth-username',
              className: `input${fieldErrors.username ? ' input-error' : ''}`,
              type: 'text',
              value: username,
              onChange: e => setUsername(e.target.value),
              autoComplete: 'username',
              autoFocus: true,
              disabled: loading,
            }),
            fieldErrors.username && React.createElement('p', { className: 'field-error' }, fieldErrors.username)
          ),

          // Password
          React.createElement(
            'div',
            { className: 'input-group' },
            React.createElement('label', { className: 'label', htmlFor: 'auth-password' }, 'Password'),
            React.createElement('input', {
              id: 'auth-password',
              className: `input${fieldErrors.password ? ' input-error' : ''}`,
              type: 'password',
              value: password,
              onChange: e => setPassword(e.target.value),
              autoComplete: tab === 'login' ? 'current-password' : 'new-password',
              disabled: loading,
            }),
            fieldErrors.password && React.createElement('p', { className: 'field-error' }, fieldErrors.password)
          ),

          React.createElement(
            'button',
            {
              type: 'submit',
              className: 'btn-primary btn-full',
              disabled: loading,
            },
            loading ? 'Please wait...' : (tab === 'login' ? 'Log In' : 'Create Account')
          )
        ),

        tab === 'register' && React.createElement(
          'p',
          { style: { marginTop: '12px', fontSize: '0.8125rem', color: 'var(--color-text-muted)', textAlign: 'center' } },
          'Already have an account? ',
          React.createElement('a', { href: '#', onClick: e => { e.preventDefault(); switchTab('login'); } }, 'Log in')
        )
      )
    );
  }

  if (!window.RPScreens) window.RPScreens = {};
  window.RPScreens.AuthScreen = AuthScreen;
})();
