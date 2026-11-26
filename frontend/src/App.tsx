// src/App.tsx → window.RPApp

(function() {
  const { useState, useCallback, useEffect } = React;

  function SideNav({ currentScreen, onNavigate, username, onLogout, onOpenSettings }) {
    const items = [
      { key: 'Catalog',         label: 'Discover' },
      { key: 'SavedStories',    label: 'Your stories' },
      { key: 'MyScenarios',     label: 'Create scenarios' },
      { key: 'Preferences',     label: 'Preferences' },
      { key: 'PersonasScreen',  label: 'Personas' },
    ];

    const currentBase = window.RPApi && window.RPApi.getApiBase ? window.RPApi.getApiBase() : 'http://localhost:8000';

    return React.createElement(
      'nav',
      { className: 'sidenav', 'aria-label': 'Main navigation' },
      React.createElement('div', { className: 'sidenav-brand' }, 'fable.', React.createElement('small', null, 'A PLACE TO BECOME')),
      React.createElement(
        'div',
        { className: 'sidenav-items' },
        items.map(item => React.createElement(
          'button',
          {
            key: item.key,
            className: `nav-item ${currentScreen === item.key ? 'active' : ''}`,
            onClick: () => onNavigate(item.key),
            'aria-current': currentScreen === item.key ? 'page' : undefined,
          },
          React.createElement('span', {className:'nav-symbol', 'aria-hidden':true}, ({Catalog:'◈',SavedStories:'≋',MyScenarios:'＋',Preferences:'☷',PersonasScreen:'◯'})[item.key]), item.label
        ))
      ),
      React.createElement(
        'div',
        { style: { padding: '12px 8px', borderTop: '1px solid var(--color-border)', display: 'flex', flexDirection: 'column', gap: '4px' } },
        React.createElement(
          'div',
          { style: { fontSize: '0.75rem', color: 'var(--color-text-muted)', padding: '2px 8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } },
          `User: ${username}`
        ),
        React.createElement(
          'button',
          {
            className: 'nav-item',
            onClick: onOpenSettings,
            style: { fontSize: '0.75rem', color: 'var(--color-text-muted)' }
          },
          `Backend: ${currentBase.replace(/^https?:\/\//, '')}`
        ),
        React.createElement(
          'button',
          { className: 'nav-item', onClick: onLogout, style: { color: 'var(--color-danger)', width: '100%', marginTop: '4px' } },
          'Log Out'
        )
      )
    );
  }

  function ServerSettingsModal({ onClose, onChanged }) {
    const [url, setUrl] = useState(window.RPApi.getApiBase ? window.RPApi.getApiBase() : 'http://localhost:8000');
    const [error,setError] = useState(null);
    const Modal = window.RPComponents && window.RPComponents.Modal;

    function handleSave() {
      try {
        if (window.RPUnsaved && !window.confirm('Changing servers discards unsaved changes and signs you out. Continue?')) return;
        const changed = window.RPApi.setApiBase(url.trim());
        if (changed) onChanged?.();
        onClose();
      } catch (error) { setError(error.message); }
    }

    const footer = React.createElement(
      React.Fragment, null,
      React.createElement('button', { className: 'btn-secondary', onClick: onClose }, 'Cancel'),
      React.createElement('button', { className: 'btn-primary', onClick: handleSave }, 'Save URL')
    );

    return React.createElement(
      Modal,
      { title: 'Server Configuration', onClose, footer },
      React.createElement(window.RPComponents.ErrorBanner,{error}),
      React.createElement('p', { style: { fontSize: '0.875rem', color: 'var(--color-text-muted)' } },
        'Choose a trusted server. Changing the server signs you out; your existing key will not be sent to the new server.'),
      React.createElement(
        'div', { className: 'input-group', style: { marginTop: '12px' } },
        React.createElement('label', { className: 'label', htmlFor: 'server-url' }, 'Backend API URL'),
        React.createElement('input', {
          id: 'server-url', className: 'input', value: url,
          onChange: e => setUrl(e.target.value), placeholder: 'http://localhost:8000',
          autoFocus: true
        })
      )
    );
  }

  function App() {
    const session = window.RPSession.getSession();
    const [user, setUser] = useState(session);
    const [showSettings, setShowSettings] = useState(false);
    const [screen, setScreen] = useState(() => {
      if (!session) return 'Auth';
      const nav = window.RPSession.getNavState();
      return nav?.screen || 'Catalog';
    });
    const [screenParams, setScreenParams] = useState(() => {
      const nav = window.RPSession.getNavState();
      return nav?.params || {};
    });

    const navigate = useCallback((screenName, params) => {
      if (window.RPUnsaved && !window.confirm('Discard unsaved scenario changes?')) return;
      setScreen(screenName);
      setScreenParams(params || {});
      window.RPSession.setNavState({ screen: screenName, params: params || {} });
    }, []);

    function handleAuth(userData) {
      setUser(userData);
      setScreen('Catalog');
      setScreenParams({});
      window.RPSession.setNavState({ screen: 'Catalog', params: {} });
    }

    function resetSession() {
      window.RPSession.clearAll();
      setUser(null);
      setScreen('Auth');
      setScreenParams({});
    }

    useEffect(() => { const expired = () => { window.RPSession.clearAll(); setUser(null); setScreen('Auth'); }; window.addEventListener('rp:unauthorized', expired); return () => window.removeEventListener('rp:unauthorized', expired); }, []);
    function handleLogout() {
      if (window.RPUnsaved && !window.confirm('Discard unsaved scenario changes and sign out?')) return;
      resetSession();
    }
    const { AuthScreen, MyScenarios, ScenarioEditor, Catalog, SavedStories, ChatScreen, Preferences, PersonasScreen, MemoryScreen } = window.RPScreens || {};

    // Not authenticated
    if (!user) {
      return React.createElement(
        React.Fragment, null,
        React.createElement(AuthScreen, { onAuth: handleAuth }),
        showSettings && React.createElement(ServerSettingsModal, { onClose: () => setShowSettings(false), onChanged: resetSession })
      );
    }

    // Secondary screens (full-width, no sidenav)
    if (screen === 'ScenarioEditor') {
      return React.createElement(
        'div',
        { className: 'app-layout app-layout-full' },
        React.createElement(
          'div',
          { className: 'content-area' },
          React.createElement(
            'div',
            { className: 'topbar' },
            React.createElement('span', { className: 'topbar-username' }, user.username),
            React.createElement('button', { className: 'btn-ghost btn-sm', onClick: handleLogout }, 'Log Out')
          ),
          React.createElement(
            'div',
            { className: 'content-scroll' },
            React.createElement(ScenarioEditor, {
              key: screenParams.scenarioId,
              scenarioId: screenParams.scenarioId,
              onBack: () => navigate('MyScenarios'),
            })
          )
        ),
        showSettings && React.createElement(ServerSettingsModal, { onClose: () => setShowSettings(false), onChanged: resetSession })
      );
    }

    if (screen === 'ChatScreen') {
      return React.createElement(
        'div',
        { style: { height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' } },
        React.createElement(ChatScreen, {
          key: screenParams.conversationId,
          conversationId: screenParams.conversationId,
          onNavigate: navigate,
        }),
        showSettings && React.createElement(ServerSettingsModal, { onClose: () => setShowSettings(false), onChanged: resetSession })
      );
    }

    if (screen === 'MemoryScreen') {
      return React.createElement(
        'div',
        { className: 'app-layout app-layout-full' },
        React.createElement(
          'div',
          { className: 'content-area' },
          React.createElement(
            'div',
            { className: 'topbar' },
            React.createElement('span', { className: 'topbar-username' }, user.username),
            React.createElement('button', { className: 'btn-ghost btn-sm', onClick: handleLogout }, 'Log Out')
          ),
          React.createElement(
            'div',
            { className: 'content-scroll' },
            React.createElement(MemoryScreen, {
              conversationId: screenParams.conversationId,
              onBack: () => screenParams.returnTo
                ? navigate(screenParams.returnTo, screenParams.returnParams)
                : navigate('ChatScreen', { conversationId: screenParams.conversationId }),
            })
          )
        ),
        showSettings && React.createElement(ServerSettingsModal, { onClose: () => setShowSettings(false), onChanged: resetSession })
      );
    }

    // Main screens with sidebar navigation
    function renderScreen() {
      switch (screen) {
        case 'MyScenarios':    return React.createElement(MyScenarios, { onNavigate: navigate });
        case 'Catalog':        return React.createElement(Catalog, { onNavigate: navigate });
        case 'SavedStories':   return React.createElement(SavedStories, { onNavigate: navigate });
        case 'Preferences':    return React.createElement(Preferences, null);
        case 'PersonasScreen': return React.createElement(PersonasScreen, null);
        default:               return React.createElement(Catalog, { onNavigate: navigate });
      }
    }

    return React.createElement(
      'div',
      { className: 'app-layout' },
      React.createElement(SideNav, {
        currentScreen: screen,
        onNavigate: navigate,
        username: user.username,
        onLogout: handleLogout,
        onOpenSettings: () => setShowSettings(true),
      }),
      React.createElement(
        'div',
        { className: 'content-area' },
        React.createElement(
          'div',
          { className: 'content-scroll' },
          renderScreen()
        )
      ),
      showSettings && React.createElement(ServerSettingsModal, { onClose: () => setShowSettings(false), onChanged: resetSession })
    );
  }

  window.RPApp = { App };
})();
