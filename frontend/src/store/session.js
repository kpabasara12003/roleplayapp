// src/store/session.ts → window.RPSession
// Encapsulated session persistence using localStorage

(function() {
  const KEYS = {
    API_KEY:  'rp_api_key',
    USER_ID:  'rp_user_id',
    USERNAME: 'rp_username',
    NAV_STATE:'rp_nav_state',
  };

  const RPSession = {
    // API Key
    getApiKey() {
      return localStorage.getItem(KEYS.API_KEY) || null;
    },
    setApiKey(key) {
      if (key) localStorage.setItem(KEYS.API_KEY, key);
      else localStorage.removeItem(KEYS.API_KEY);
    },

    // User ID
    getUserId() {
      return localStorage.getItem(KEYS.USER_ID) || null;
    },
    setUserId(id) {
      if (id) localStorage.setItem(KEYS.USER_ID, id);
      else localStorage.removeItem(KEYS.USER_ID);
    },

    // Username
    getUsername() {
      return localStorage.getItem(KEYS.USERNAME) || null;
    },
    setUsername(name) {
      if (name) localStorage.setItem(KEYS.USERNAME, name);
      else localStorage.removeItem(KEYS.USERNAME);
    },

    // Combined set/get
    setSession({ userId, username, apiKey }) {
      localStorage.setItem('rp_session_base', window.RPApi.getApiBase());
      RPSession.setUserId(userId);
      RPSession.setUsername(username);
      RPSession.setApiKey(apiKey);
    },
    getSession() {
      const userId   = RPSession.getUserId();
      const username = RPSession.getUsername();
      const apiKey   = RPSession.getApiKey();
      if (!userId || !apiKey) return null;
      return { userId, username, apiKey };
    },
    isAuthenticated() {
      return !!(RPSession.getApiKey() && RPSession.getUserId());
    },

    // Nav state (which screen was last active)
    getNavState() {
      try {
        const raw = localStorage.getItem(KEYS.NAV_STATE);
        return raw ? JSON.parse(raw) : { screen: 'Catalog' };
      } catch {
        return { screen: 'Catalog' };
      }
    },
    setNavState(state) {
      localStorage.setItem(KEYS.NAV_STATE, JSON.stringify(state));
    },

    // Clear everything
    clearAll() {
      Object.values(KEYS).forEach(k => localStorage.removeItem(k));
      // Also remove any other rp_* keys
      const toRemove = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && ((key.startsWith('rp_') && key !== 'rp_api_base') || key.startsWith('chat_last_seq_'))) toRemove.push(key);
      }
      toRemove.forEach(k => localStorage.removeItem(k));
    },
  };

  window.RPSession = RPSession;
})();
