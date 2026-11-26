// src/store/conversationStore.ts → window.RPConvStore
// React context + reducer for conversation state management

(function() {
  const { createContext, useContext, useReducer, useCallback, useMemo } = React;

  // ---- Initial state ----
  const initialState = {
    messages: {},           // { [convId]: { [msgId]: Message } }
    pendingInputs: {},      // { [requestId]: { convId, content, optimisticId } }
    streamBuffers: {},      // { [`${turnId}:${genId}:${attempt}`]: string[] }
    currentAttempt: {},     // { [`${turnId}:${genId}`]: number }
    gameState: {},          // { [convId]: GameState }
    turnStatus: {},         // { [convId]: { turnId, status, stage, blockedReason } }
    composerLocked: {},     // { [convId]: boolean }
  };

  // ---- Action types ----
  const A = {
    ADD_MESSAGE:        'ADD_MESSAGE',
    UPDATE_MESSAGE:     'UPDATE_MESSAGE',
    SET_PROVISIONAL:    'SET_PROVISIONAL',
    COMMIT_PROVISIONAL: 'COMMIT_PROVISIONAL',
    REMOVE_MESSAGE:     'REMOVE_MESSAGE',
    SET_PENDING:        'SET_PENDING',
    CLEAR_PENDING:      'CLEAR_PENDING',
    APPEND_CHUNK:       'APPEND_CHUNK',
    SET_ATTEMPT:        'SET_ATTEMPT',
    SET_GAME_STATE:     'SET_GAME_STATE',
    SET_TURN_STATUS:    'SET_TURN_STATUS',
    LOCK_COMPOSER:      'LOCK_COMPOSER',
    UNLOCK_COMPOSER:    'UNLOCK_COMPOSER',
    CLEAR_CONVERSATION: 'CLEAR_CONVERSATION',
    LOAD_MESSAGES:      'LOAD_MESSAGES',
  };

  function reducer(state, action) {
    switch (action.type) {
      case A.LOAD_MESSAGES: {
        const { convId, messages } = action;
        const existing = state.messages[convId] || {};
        const merged = { ...existing };
        messages.forEach(m => {
          const unifiedRole = m.role || (m.sender === 'ai' ? 'assistant' : m.sender) || 'assistant';
          merged[m.id] = { ...m, role: unifiedRole };
        });
        return { ...state, messages: { ...state.messages, [convId]: merged } };
      }

      case A.ADD_MESSAGE: {
        const { convId, message } = action;
        const existing = state.messages[convId] || {};
        // Dedup by message_id
        if (existing[message.id]) return state;
        const unifiedRole = message.role || (message.sender === 'ai' ? 'assistant' : message.sender) || 'assistant';
        return {
          ...state,
          messages: {
            ...state.messages,
            [convId]: { ...existing, [message.id]: { ...message, role: unifiedRole } },
          },
        };
      }

      case A.UPDATE_MESSAGE: {
        const { convId, messageId, updates } = action;
        const existing = state.messages[convId] || {};
        const msg = existing[messageId];
        if (!msg) return state;
        return {
          ...state,
          messages: {
            ...state.messages,
            [convId]: { ...existing, [messageId]: { ...msg, ...updates } },
          },
        };
      }

      case A.SET_PROVISIONAL: {
        const { convId, message } = action; // message.id = optimistic id
        const existing = state.messages[convId] || {};
        return {
          ...state,
          messages: {
            ...state.messages,
            [convId]: { ...existing, [message.id]: { ...message, is_provisional: true } },
          },
        };
      }

      case A.COMMIT_PROVISIONAL: {
        // Replace optimistic message with canonical
        const { convId, optimisticId, canonicalMessage } = action;
        const existing = state.messages[convId] || {};
        const updated = { ...existing };
        delete updated[optimisticId];
        // Only add if not already present (dedup)
        if (!updated[canonicalMessage.id]) {
          updated[canonicalMessage.id] = { ...canonicalMessage, is_provisional: false };
        }
        return {
          ...state,
          messages: { ...state.messages, [convId]: updated },
        };
      }

      case A.REMOVE_MESSAGE: {
        const { convId, messageId } = action;
        const existing = { ...(state.messages[convId] || {}) };
        delete existing[messageId];
        return { ...state, messages: { ...state.messages, [convId]: existing } };
      }

      case A.SET_PENDING: {
        const { requestId, convId, content, optimisticId } = action;
        return {
          ...state,
          pendingInputs: { ...state.pendingInputs, [requestId]: { convId, content, optimisticId } },
        };
      }

      case A.CLEAR_PENDING: {
        const { requestId } = action;
        const updated = { ...state.pendingInputs };
        delete updated[requestId];
        return { ...state, pendingInputs: updated };
      }

      case A.APPEND_CHUNK: {
        const { key, chunk } = action;
        const existing = state.streamBuffers[key] || [];
        return {
          ...state,
          streamBuffers: { ...state.streamBuffers, [key]: [...existing, chunk] },
        };
      }

      case A.SET_ATTEMPT: {
        const { key, attempt } = action;
        return {
          ...state,
          currentAttempt: { ...state.currentAttempt, [key]: attempt },
        };
      }

      case A.SET_GAME_STATE: {
        const { convId, gameState } = action;
        const previous = state.gameState[convId];
        if (previous && previous.state_version > gameState.state_version) return state;
        return { ...state, gameState: { ...state.gameState, [convId]: gameState } };
      }

      case A.SET_TURN_STATUS: {
        const { convId, turnId, status, stage, blockedReason } = action;
        return {
          ...state,
          turnStatus: { ...state.turnStatus, [convId]: { turnId, status, stage, blockedReason } },
        };
      }

      case A.LOCK_COMPOSER: {
        return { ...state, composerLocked: { ...state.composerLocked, [action.convId]: true } };
      }

      case A.UNLOCK_COMPOSER: {
        return { ...state, composerLocked: { ...state.composerLocked, [action.convId]: false } };
      }

      case A.CLEAR_CONVERSATION: {
        const { convId } = action;
        const msgs = { ...state.messages };
        const gs   = { ...state.gameState };
        const ts   = { ...state.turnStatus };
        const cl   = { ...state.composerLocked };
        delete msgs[convId];
        delete gs[convId];
        delete ts[convId];
        delete cl[convId];
        return { ...state, messages: msgs, gameState: gs, turnStatus: ts, composerLocked: cl };
      }

      default:
        return state;
    }
  }

  // ---- Context ----
  const ConvStoreContext = createContext(null);

  function ConversationStoreProvider({ children }) {
    const [state, dispatch] = useReducer(reducer, initialState);

    const actions = useMemo(() => ({
      loadMessages(convId, messages) {
        dispatch({ type: A.LOAD_MESSAGES, convId, messages });
      },
      addMessage(convId, message) {
        dispatch({ type: A.ADD_MESSAGE, convId, message });
      },
      updateMessage(convId, messageId, updates) {
        dispatch({ type: A.UPDATE_MESSAGE, convId, messageId, updates });
      },
      setProvisional(convId, message) {
        dispatch({ type: A.SET_PROVISIONAL, convId, message });
      },
      commitProvisional(convId, optimisticId, canonicalMessage) {
        dispatch({ type: A.COMMIT_PROVISIONAL, convId, optimisticId, canonicalMessage });
      },
      removeMessage(convId, messageId) {
        dispatch({ type: A.REMOVE_MESSAGE, convId, messageId });
      },
      setPending(requestId, convId, content, optimisticId) {
        dispatch({ type: A.SET_PENDING, requestId, convId, content, optimisticId });
      },
      clearPending(requestId) {
        dispatch({ type: A.CLEAR_PENDING, requestId });
      },
      appendChunk(key, chunk) {
        dispatch({ type: A.APPEND_CHUNK, key, chunk });
      },
      setAttempt(key, attempt) {
        dispatch({ type: A.SET_ATTEMPT, key, attempt });
      },
      setGameState(convId, gameState) {
        dispatch({ type: A.SET_GAME_STATE, convId, gameState });
      },
      setTurnStatus(convId, turnId, status, stage, blockedReason) {
        dispatch({ type: A.SET_TURN_STATUS, convId, turnId, status, stage, blockedReason });
      },
      lockComposer(convId) {
        dispatch({ type: A.LOCK_COMPOSER, convId });
      },
      unlockComposer(convId) {
        dispatch({ type: A.UNLOCK_COMPOSER, convId });
      },
      clearConversation(convId) {
        dispatch({ type: A.CLEAR_CONVERSATION, convId });
      },
    }), []);

    // Selectors
    const selectors = useMemo(() => ({
      getMessages(convId) {
        const map = state.messages[convId] || {};
        return Object.values(map).sort((a, b) => {
          const ta = a.created_at || '';
          const tb = b.created_at || '';
          return ta < tb ? -1 : ta > tb ? 1 : 0;
        });
      },
      getGameState(convId) { return state.gameState[convId] || null; },
      getTurnStatus(convId) { return state.turnStatus[convId] || null; },
      isComposerLocked(convId) { return !!state.composerLocked[convId]; },
      getStreamBuffer(key) { return (state.streamBuffers[key] || []).join(''); },
      getPending(requestId) { return state.pendingInputs[requestId] || null; },
    }), [state]);

    const value = useMemo(() => ({ state, actions, selectors }), [state, actions, selectors]);

    return React.createElement(ConvStoreContext.Provider, { value }, children);
  }

  function useConvStore() {
    const ctx = useContext(ConvStoreContext);
    if (!ctx) throw new Error('useConvStore must be used within ConversationStoreProvider');
    return ctx;
  }

  window.RPConvStore = { ConversationStoreProvider, useConvStore };
})();
