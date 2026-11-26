// src/screens/ChatScreen.tsx → window.RPScreens.ChatScreen

(function() {
  const { useState, useEffect, useRef, useCallback, useMemo } = React;
  const { ErrorBanner, LoadingWrap, Modal } = window.RPComponents;
  const { useToast } = window.RPComponents;
  const { useConvStore } = window.RPConvStore;
  const { WsManager } = window.RPWs;
  const Api = window.RPApi;

  // ---- WS Status Bar ----
  function WsStatusBar({ status, reconnectIn }) {
    const labels = { connected: 'Connected', connecting: 'Connecting...', disconnected: 'Disconnected', reconnecting: 'Reconnecting...' };
    const s = status || 'disconnected';
    return React.createElement(
      'div',
      null,
      React.createElement(
        'div',
        { className: `ws-status-bar ws-status-${s === 'reconnecting' ? 'connecting' : s}` },
        React.createElement('span', { className: 'ws-dot' }),
        React.createElement('span', null, labels[s] || s)
      ),
      s === 'reconnecting' && reconnectIn > 0 && React.createElement(
        'div',
        { className: 'ws-reconnect-info' },
        `Retrying in ${Math.ceil(reconnectIn / 1000)}s`
      )
    );
  }

  // ---- Affinity bar ----
  function AffinityBar({ score }) {
    // score is -100 to 100. Bar center at 50%, fill extends left or right.
    const pct = Math.max(0, Math.min(100, (score + 100) / 2));
    const left   = pct < 50 ? pct : 50;
    const width  = Math.abs(pct - 50);
    return React.createElement(
      'div',
      { className: 'affinity-bar-wrap', title: `Affinity: ${score}` },
      React.createElement('div', {
        className: 'affinity-bar-fill',
        style: { left: `${left}%`, width: `${width}%`, background: score >= 0 ? 'var(--color-success)' : 'var(--color-danger)' }
      })
    );
  }

  // ---- Text formatting for roleplay (dialogue in soft pearl, *action* in italic muted rosewood/lavender) ----
  function formatRoleplayHtml(raw) {
    if (!raw) return '';
    let s = String(raw)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
    s = s.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*(.*?)\*/g, '<em class="action-bubble">*$1*</em>');
    s = s.replace(/\n/g, '<br>');
    return s;
  }

  // ---- State panel ----
  function StatePanel({ gameState, conversationId, onNavigate }) {
    if (!gameState) return React.createElement(
      'div',
      { className: 'chat-state-panel' },
      React.createElement(
        'div',
        { className: 'state-panel-section' },
        React.createElement('p', { style: { color: 'var(--color-text-muted)', fontSize: '0.8125rem' } }, 'No game state yet.')
      )
    );

    const inventoryList = Array.isArray(gameState.inventory)
      ? gameState.inventory
      : (gameState.inventory && typeof gameState.inventory === 'object')
        ? Object.values(gameState.inventory)
        : [];

    const relationshipList = Array.isArray(gameState.relationships)
      ? gameState.relationships
      : (gameState.relationships && typeof gameState.relationships === 'object')
        ? Object.values(gameState.relationships)
        : [];

    const questFlags = Array.isArray(gameState.quest_flags) ? gameState.quest_flags : [];
    const questProgress = (gameState.runtime && gameState.runtime.quest_progress) || {};
    const progressKeys = Object.keys(questProgress);
    const clockMins = gameState.runtime && gameState.runtime.clock_minutes != null ? gameState.runtime.clock_minutes : null;

    return React.createElement(
      'div',
      { className: 'chat-state-panel' },

      // Location & Story Time
      React.createElement(
        'div',
        { className: 'state-panel-section' },
        React.createElement('div', { className: 'state-panel-heading' }, 'Setting'),
        React.createElement('div', { className: 'state-location-place' }, gameState.place || '—'),
        gameState.time && React.createElement('div', { className: 'state-location-time' }, gameState.time),
        clockMins !== null && React.createElement(
          'div',
          { style: { fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '4px' } },
          `Story clock: ${Math.floor(clockMins / 60)}h ${clockMins % 60}m`
        )
      ),

      // Inventory
      inventoryList.length > 0 && React.createElement(
        'div',
        { className: 'state-panel-section' },
        React.createElement('div', { className: 'state-panel-heading' }, 'Inventory'),
        inventoryList.map((item, i) => React.createElement(
          'div',
          { key: item.id || i, className: 'inventory-item' },
          React.createElement(
            'div', null,
            React.createElement('div', { className: 'inventory-item-name' }, item.name || item.id),
            item.description && React.createElement('div', { style: { color: 'var(--color-text-muted)', fontSize: '0.75rem' } }, item.description)
          ),
          item.quantity != null && React.createElement('div', { className: 'inventory-item-qty' }, `x${item.quantity}`)
        ))
      ),

      // Relationships
      relationshipList.length > 0 && React.createElement(
        'div',
        { className: 'state-panel-section' },
        React.createElement('div', { className: 'state-panel-heading' }, 'Relationships'),
        relationshipList.map((r, i) => React.createElement(
          'div',
          { key: r.character_name || i, className: 'relationship-item' },
          React.createElement('div', { className: 'relationship-name' }, r.character_name),
          r.relationship_status && React.createElement('div', { className: 'relationship-status' }, r.relationship_status),
          React.createElement(AffinityBar, { score: r.affinity_score || 0 })
        ))
      ),

      // Quests & Objectives
      (questFlags.length > 0 || progressKeys.length > 0 || (gameState.quests && gameState.quests.length > 0)) && React.createElement(
        'div',
        { className: 'state-panel-section' },
        React.createElement('div', { className: 'state-panel-heading' }, 'Quests & Objectives'),
        gameState.quests && Array.isArray(gameState.quests) && gameState.quests.map((q, i) => React.createElement(
          'div',
          { key: i, className: 'quest-item' },
          React.createElement('div', { className: 'quest-title' }, q.title),
          q.stages && q.stages.length > 0 && React.createElement(
            'div',
            { className: 'quest-stage' },
            `${q.stages.filter(s => s.completed).length}/${q.stages.length} stages`
          )
        )),
        progressKeys.map(k => React.createElement(
          'div',
          { key: k, className: 'quest-item' },
          React.createElement('div', { className: 'quest-title' }, k.replace(/_/g, ' ')),
          React.createElement('div', { className: 'quest-stage' }, `${questProgress[k].status || 'inactive'}${questProgress[k].stage ? ' · ' + questProgress[k].stage : ''}${questProgress[k].objectives ? ' · ' + Object.entries(questProgress[k].objectives).map(([name,count]) => name.replace(/_/g,' ') + ': ' + count).join(', ') : ''}`)
        )),
        questFlags.length > 0 && React.createElement(
          'div',
          { style: { marginTop: '6px' } },
          questFlags.map(f => React.createElement(
            'span',
            { key: f, className: 'badge', style: { marginRight: '4px', marginBottom: '4px', display: 'inline-block' } },
            f
          ))
        )
      ),

      // Memory link
      React.createElement(
        'div',
        { className: 'state-panel-section' },
        React.createElement(
          'button',
          {
            className: 'btn-ghost btn-sm',
            style: { width: '100%', textAlign: 'left' },
            onClick: () => onNavigate('MemoryScreen', { conversationId })
          },
          'View Memories & Notes'
        )
      )
    );
  }

  // ---- Single message row ----
  function MessageRow({ msg, onFork, onRegenerate, onEdit, isBranchLoading }) {
    const isUser     = msg.role === 'user' || msg.sender === 'user';
    const isAI       = msg.role === 'assistant' || msg.role === 'ai' || msg.sender === 'ai' || msg.sender === 'assistant';
    const isDirector = msg.role === 'director' || msg.sender === 'director';

    const roleClass = isUser ? 'msg-user' : isAI ? 'msg-ai' : isDirector ? 'msg-director' : 'msg-system';
    const provisionalClass = msg.is_provisional ? ' msg-provisional' : '';
    const rawTurn = msg.turn_id || (msg.metadata && msg.metadata.turn_id) || msg.event_id || '';
    const turnId = rawTurn.replace(/^(actor|user|director)-/, '');
    const validTurn = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(turnId);

    return React.createElement(
      'div',
      { className: `msg ${roleClass}${provisionalClass}`, 'data-msg-id': msg.id },
      React.createElement(
        'div',
        { className: 'msg-meta' },
        React.createElement('span', null, isUser ? 'You' : isAI ? 'Character' : isDirector ? 'Narrator' : 'System'),
        msg.created_at && React.createElement('span', null, new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
      ),
      React.createElement('div', {
        className: 'msg-bubble',
        dangerouslySetInnerHTML: { __html: formatRoleplayHtml(msg.content) }
      }),
      // Branch controls (only on committed, non-system messages with an identifiable turn)
      validTurn && !msg.is_provisional && msg.role !== 'system' && msg.sender !== 'system' && React.createElement(
        'div',
        { className: 'branch-controls' },
        isAI && React.createElement(
          'button',
          {
            className: 'branch-btn',
            onClick: () => onRegenerate({ ...msg, turn_id: turnId }),
            disabled: isBranchLoading,
            title: 'Create a new branch with a different actor response from before-reply checkpoint'
          },
          'Branch: Regenerate response'
        ),
        isUser && React.createElement(
          'button',
          {
            className: 'branch-btn',
            onClick: () => onEdit({ ...msg, turn_id: turnId }),
            disabled: isBranchLoading,
            title: 'Edit this message, creating a new branch before this action'
          },
          'Branch: Edit message'
        ),
        React.createElement(
          'button',
          {
            className: 'branch-btn',
            onClick: () => onFork({ ...msg, turn_id: turnId }),
            disabled: isBranchLoading,
            title: 'Fork story from this point'
          },
          'Branch: Fork story here'
        )
      )
    );
  }

  // ---- Edit message modal ----
  function EditMessageModal({ message, onConfirm, onClose }) {
    const [content, setContent] = useState(message.content);
    const [loading, setLoading] = useState(false);

    async function handleConfirm() {
      setLoading(true);
      await onConfirm(message, content);
      setLoading(false);
    }

    const footer = React.createElement(
      React.Fragment, null,
      React.createElement('button', { className: 'btn-secondary', onClick: onClose, disabled: loading }, 'Cancel'),
      React.createElement('button', { className: 'btn-primary', onClick: handleConfirm, disabled: loading || !content.trim() },
        loading ? 'Branching...' : 'Branch: Edit Message')
    );

    return React.createElement(
      Modal, { title: 'Edit Message (Creates Branch)', onClose, footer },
      React.createElement('div', { className: 'info-box' }, 'This creates a new branch of the story with your edited message.'),
      React.createElement(
        'div', { className: 'input-group' },
        React.createElement('label', { className: 'label' }, 'Message Content'),
        React.createElement('textarea', {
          className: 'textarea', value: content, rows: 6,
          onChange: e => setContent(e.target.value), disabled: loading
        })
      )
    );
  }

  // ---- Fork modal ----
  function ForkModal({ message, onConfirm, onClose }) {
    const [title, setTitle]         = useState('');
    const [fromInitial, setFromInitial] = useState(!message?.turn_id);
    const [loading, setLoading]     = useState(false);

    async function handleConfirm() {
      setLoading(true);
      await onConfirm({
        title: title.trim() || undefined,
        initial: fromInitial,
      });
      setLoading(false);
    }

    const footer = React.createElement(
      React.Fragment, null,
      React.createElement('button', { className: 'btn-secondary', onClick: onClose, disabled: loading }, 'Cancel'),
      React.createElement('button', { className: 'btn-primary', onClick: handleConfirm, disabled: loading },
        loading ? 'Forking...' : 'Branch: Fork Story')
    );

    return React.createElement(
      Modal, { title: 'Fork Story (Creates Branch)', onClose, footer },
      React.createElement('div', { className: 'info-box' }, 'Forking creates a new, independent branch of the story from this state.'),
      React.createElement(
        'div', { className: 'input-group' },
        React.createElement('label', { className: 'label', htmlFor: 'fork-title' }, 'Branch Title (optional)'),
        React.createElement('input', {
          id: 'fork-title', className: 'input', value: title,
          onChange: e => setTitle(e.target.value), placeholder: 'e.g. "What if I said..."',
          autoFocus: true
        })
      ),
      React.createElement(
        'label', { className: 'checkbox-label', style: { marginTop: '12px' } },
        React.createElement('input', {
          type: 'checkbox',
          checked: fromInitial,
          onChange: e => setFromInitial(e.target.checked)
        }),
        'Fork from initial story checkpoint (restart from beginning as a new branch)'
      )
    );
  }

  // ---- Main ChatScreen ----
  function ChatScreen({ conversationId, onNavigate }) {
    const toast = useToast();
    const { state, actions, selectors } = useConvStore();

    const [conversation, setConversation] = useState(null);
    const [loading, setLoading]           = useState(true);
    const [error, setError]               = useState(null);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [oldestMsgId, setOldestMsgId]   = useState(null);
    const [hasMoreHistory, setHasMoreHistory] = useState(false);

    const [wsStatus, setWsStatus]           = useState('disconnected');
    const [wsReconnectIn, setWsReconnectIn] = useState(0);

    const [composerText, setComposerText]   = useState('');
    const [sending, setSending]             = useState(false);
    const [sendError, setSendError]         = useState(null);
    const [blockedReason, setBlockedReason] = useState(null);

    const [branchLoading, setBranchLoading] = useState(false);
    const [forkModal, setForkModal]         = useState(null); // message obj
    const [editModal, setEditModal]         = useState(null); // message obj

    const wsRef         = useRef(null);
    const messagesEndRef = useRef(null);
    const reconTimerRef  = useRef(null);
    const reconcileRef   = useRef(false); // is reconciliation in progress?
    const wsBufferRef    = useRef([]);     // buffered WS events during reconciliation
    const pendingReqRef  = useRef({});    // request_id → optimisticId

    const chunksRef = useRef({});
    const attemptsRef = useRef({});
    const eventHandlerRef = useRef(null);
    const retryInputRef = useRef(null);
    // Active turn ref
    const activeTurnRef = useRef(null);

    const messages    = selectors.getMessages(conversationId);
    const gameState   = selectors.getGameState(conversationId);
    const turnStatus  = selectors.getTurnStatus(conversationId);
    const isLocked    = selectors.isComposerLocked(conversationId);

    // Auto-scroll
    useEffect(() => {
      if (messagesEndRef.current) {
        messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
      }
    }, [messages.length]);

    // ---- WS event handlers ----
    const handleWsEvent = useCallback((type, data) => {
      if (reconcileRef.current) {
        wsBufferRef.current.push({ type, data });
        return;
      }
      eventHandlerRef.current(type, data);
    }, []);

    function processWsEvent(type, data) {
      const convId = conversationId;
      switch (type) {
        case 'turn_accepted': {
          // Associate turn_id with pending request
          const { turn_id, request_id } = data;
          if (request_id && pendingReqRef.current[request_id]) {
            activeTurnRef.current = turn_id;
          }
          actions.setTurnStatus(convId, turn_id, 'accepted', 'validating', null);
          actions.lockComposer(convId);
          break;
        }
        case 'state_change': {
          const stage = data.state || data.status || data.stage;
          if (stage === 'error' || stage === 'reply_completed') break; // persisted turn polling decides completion/failure
          actions.setTurnStatus(convId, data.turn_id || activeTurnRef.current, stage, stage, null);
          break;
        }
        case 'text_chunk': {
          const { turn_id, generation_id, attempt, chunk } = data;
          const chunk_index = data.index ?? data.chunk_index;
          const group = `${turn_id}:${generation_id}`;
          if ((attemptsRef.current[group] || 0) > attempt) break;
          if (attempt > (attemptsRef.current[group] || 0)) {
            for (const key of Object.keys(chunksRef.current)) if (key.startsWith(group + ":")) actions.removeMessage(convId, `provisional:${key}`);
            attemptsRef.current[group] = attempt;
          }
          if (chunk === undefined || chunk === null) break;
          const bufKey = `${turn_id}:${generation_id}:${attempt}`;
          const buffer = chunksRef.current[bufKey] ||= {};
          if (buffer[chunk_index] !== undefined) break;
          buffer[chunk_index] = chunk;
          // Update or create provisional message
          const bufContent = Object.keys(buffer).sort((a,b)=>Number(a)-Number(b)).map(i=>buffer[i]).join('');
          const provId = `provisional:${bufKey}`;
          actions.setProvisional(convId, {
            id: provId,
            conversation_id: convId,
            role: 'assistant',
            content: bufContent,
            is_provisional: true,
            created_at: new Date().toISOString(),
            turn_id,
            generation_id,
            attempt,
          });
          break;
        }
        case 'message_completed': {
          const { message_id, turn_id, generation_id, attempt, created_at, request_id } = data;
          const content = data.full_content ?? data.content;
          const role = data.sender === 'ai' ? 'assistant' : (data.sender || data.role || 'assistant');
          if (role === 'assistant') {
            for (const key of Object.keys(chunksRef.current)) actions.removeMessage(convId, `provisional:${key}`);
            chunksRef.current = {};
          }
          const bufKey = `${turn_id}:${generation_id}:${attempt}`;
          const provId = `provisional:${bufKey}`;

          // Check for optimistic user message to commit
          if (request_id && pendingReqRef.current[request_id]) {
            const { optimisticId } = pendingReqRef.current[request_id];
            if (role === 'user' && optimisticId) {
              actions.commitProvisional(convId, optimisticId, {
                id: message_id, conversation_id: convId, role,
                content, created_at, turn_id, generation_id, attempt,
              });
              delete pendingReqRef.current[request_id];
              break;
            }
          }

          // Commit AI provisional
          actions.commitProvisional(convId, provId, {
            id: message_id, conversation_id: convId, role: role || 'assistant',
            content, created_at: created_at || new Date().toISOString(),
            turn_id, generation_id, attempt,
          });
          break;
        }
        case 'engine_state_updated': {
          const game_state = data.current_state || data.game_state;
          if (game_state) actions.setGameState(convId, game_state);
          break;
        }
        case 'director_state_change': {
          const stage = data.state || data.stage;
          const { turn_id } = data;
          if (stage === 'completed') {
            actions.setTurnStatus(convId, turn_id, 'completed', 'completed', null);
            actions.unlockComposer(convId);
            setBlockedReason(null);
            activeTurnRef.current = null;
          } else {
            actions.setTurnStatus(convId, turn_id, stage, stage, null);
          }
          break;
        }
        case 'action_blocked': {
          const { reason, turn_id } = data;
          setBlockedReason(reason);
          actions.setTurnStatus(convId, turn_id, 'blocked', 'blocked', reason);
          actions.unlockComposer(convId);
          activeTurnRef.current = null;
          break;
        }
        case 'error': {
          const { message: msg, turn_id } = data;
          if (turn_id) actions.setTurnStatus(convId, turn_id, 'failed', 'failed', msg);
          actions.unlockComposer(convId);
          activeTurnRef.current = null;
          toast.error(msg || 'An error occurred during generation.');
          break;
        }
      }
    }

    eventHandlerRef.current = processWsEvent;

    // ---- Flush buffered WS events ----
    function flushWsBuffer() {
      const events = wsBufferRef.current.slice();
      wsBufferRef.current = [];
      events.forEach(({ type, data }) => processWsEvent(type, data));
    }

    // ---- Setup WS ----
    function setupWs(lastSeq) {
      const ws = new WsManager();
      wsRef.current = ws;

      ws.onStatus((status, extra) => {
        setWsStatus(status);
        if (status === 'reconnecting' && extra?.delay) {
          setWsReconnectIn(extra.delay);
          if (reconTimerRef.current) clearInterval(reconTimerRef.current);
          reconTimerRef.current = setInterval(() => {
            setWsReconnectIn(prev => Math.max(0, prev - 500));
          }, 500);
        } else {
          if (reconTimerRef.current) clearInterval(reconTimerRef.current);
          setWsReconnectIn(0);
        }
      });

      // Subscribe to all events
      ws.on('*', ({ type, data }) => handleWsEvent(type, data));

      ws.on('ws_open', async () => {
        try {
          const latest = await Api.resumeConversation(conversationId);
          if (wsRef.current !== ws) return;
          actions.loadMessages(conversationId, latest.messages || []);
          if (latest.state) actions.setGameState(conversationId, latest.state);
        } catch (_) { /* polling below provides recovery */ }
      });
      ws.connect(conversationId, lastSeq);
    }

    // ---- Resume flow ----
    useEffect(() => {
      let cancelled = false;
      actions.clearConversation(conversationId);

      async function doResume() {
        setLoading(true);
        setError(null);
        try {
          // Step 1: GET resume
          const resume = await Api.resumeConversation(conversationId);
          if (cancelled) return;

          setConversation(resume.conversation);

          // Load messages
          const msgs = resume.messages || [];
          actions.loadMessages(conversationId, msgs);
          if (msgs.length > 0) {
            setOldestMsgId(msgs[0].id);
            setHasMoreHistory(msgs.length >= 100);
          }

          // Apply game state
          if (resume.state) actions.setGameState(conversationId, resume.state);

          // Step 2: Inspect active turn
          if (resume.turn) {
            const t = resume.turn;
            activeTurnRef.current = t.id;
            actions.setTurnStatus(conversationId, t.id, t.status, t.stage, t.blocked_reason);
            if (t.status !== 'completed' && t.status !== 'failed' && t.status !== 'blocked') {
              actions.lockComposer(conversationId);
            }
          }

          const lastSeq = resume.last_seen_seq ?? null;
          setLoading(false);

          // Step 3: Connect WS
          reconcileRef.current = true;
          wsBufferRef.current = [];
          setupWs(lastSeq);

          // Step 4: Fetch resume again (reconcile)
          try {
            const resume2 = await Api.resumeConversation(conversationId);
            if (cancelled) return;
            if (resume2.messages) actions.loadMessages(conversationId, resume2.messages);
            if (resume2.state) actions.setGameState(conversationId, resume2.state);
          } catch (e) {
            console.warn('Resume reconcile failed:', e);
          }

          // Step 5: Flush buffer
          reconcileRef.current = false;
          flushWsBuffer();

        } catch (err) {
          if (!cancelled) {
            setError(err);
            setLoading(false);
          }
        }
      }

      doResume();

      return () => {
        cancelled = true;
        if (wsRef.current) wsRef.current.disconnect();
        if (reconTimerRef.current) clearInterval(reconTimerRef.current);
      };
    }, [conversationId]);

    useEffect(() => {
      let cancelled = false, busy = false;
      const timer = setInterval(async () => {
        if (busy) return;
        busy = true;
        try {
          const latest = await Api.resumeConversation(conversationId);
          if (cancelled) return;
          actions.loadMessages(conversationId, latest.messages || []);
          if (latest.state) actions.setGameState(conversationId, latest.state);
          const turn = latest.turn;
          if (activeTurnRef.current && turn?.id !== activeTurnRef.current) return;
          if (turn) {
            activeTurnRef.current = turn.id;
            actions.setTurnStatus(conversationId,turn.id,turn.status,turn.status,turn.failure);
          }
          if (turn && ['validating','generating','narrating'].includes(turn.status)) actions.lockComposer(conversationId);
          else actions.unlockComposer(conversationId);
          if (turn && ['completed','failed','blocked'].includes(turn.status)) {
            activeTurnRef.current = null;
            for (const key of Object.keys(chunksRef.current)) actions.removeMessage(conversationId, `provisional:${key}`);
            chunksRef.current = {};
          }
        } catch (_) {} finally { busy = false; }
      }, 2500);
      return () => { cancelled = true; clearInterval(timer); };
    }, [conversationId]);

    // ---- Load older history ----
    async function loadOlderHistory() {
      if (!oldestMsgId || historyLoading) return;
      setHistoryLoading(true);
      try {
        const data = await Api.getChatHistory(conversationId, { before_id: oldestMsgId, limit: 100 });
        const items = Array.isArray(data) ? data : (data.messages || data.items || []);
        if (items.length > 0) {
          actions.loadMessages(conversationId, items);
          setOldestMsgId(items[0].id);
          setHasMoreHistory(items.length === 100);
        } else {
          setHasMoreHistory(false);
        }
      } catch (err) {
        toast.error(window.RPComponents.formatError(err));
      } finally {
        setHistoryLoading(false);
      }
    }

    // ---- Send message ----
    async function handleSend() {
      const content = composerText.trim();
      if (!content || isLocked || sending) return;
      if (content.length > 16000) { toast.error('Message too long (max 16000 chars).'); return; }

      const requestId = crypto.randomUUID();
      const stableId = retryInputRef.current?.content === content ? retryInputRef.current.id : requestId;
      retryInputRef.current = { content, id: stableId };
      const optimisticId = `optimistic:${stableId}`;

      setSending(true);
      setSendError(null);
      setComposerText('');
      setBlockedReason(null);

      // Optimistic user message
      actions.setProvisional(conversationId, {
        id: optimisticId,
        conversation_id: conversationId,
        role: 'user',
        content,
        is_provisional: true,
        created_at: new Date().toISOString(),
        request_id: requestId,
      });
      actions.lockComposer(conversationId);
      pendingReqRef.current[requestId] = { optimisticId };

      try {
        const accepted = await Api.sendMessage(conversationId, { content, request_id: stableId });
        actions.commitProvisional(conversationId, optimisticId, { ...accepted, role: 'user' });
        activeTurnRef.current = accepted.turn_id;
        actions.setTurnStatus(conversationId, accepted.turn_id, 'validating', 'validating', null);
        retryInputRef.current = null;
        delete pendingReqRef.current[requestId];
      } catch (err) {
        // On error: remove optimistic message, unlock
        actions.removeMessage(conversationId, optimisticId);
        delete pendingReqRef.current[requestId];
        actions.unlockComposer(conversationId);
        setSendError(err);
        setComposerText(content); // restore
      } finally {
        setSending(false);
      }
    }

    // ---- Retry failed turn ----
    async function handleRetry() {
      if (!turnStatus?.turnId) return;
      try {
        await Api.retryTurn(turnStatus.turnId);
        actions.lockComposer(conversationId);
        actions.setTurnStatus(conversationId, turnStatus.turnId, 'validating', 'validating', null);
        toast.info('Retrying...');
      } catch (err) {
        toast.error(window.RPComponents.formatError(err));
      }
    }

    // ---- Branch: Regenerate ----
    async function handleRegenerate(msg) {
      if (branchLoading) return;
      setBranchLoading(true);
      const requestId = crypto.randomUUID();
      try {
        const payload = { turn_id: msg.turn_id, request_id: requestId };
        const result = await Api.regenerateConversation(conversationId, payload);
        const newConvId = result.conversation_id || result.id || (result.conversation && result.conversation.id);
        if (newConvId) {
          onNavigate('ChatScreen', { conversationId: newConvId });
          toast.info('Branched: actor response regenerating...');
        }
      } catch (err) {
        if (err.status === 409) {
          toast.error('Cannot regenerate: ' + (err.detail || 'historic turn before-reply checkpoint unavailable.'));
        } else {
          toast.error(window.RPComponents.formatError(err));
        }
      } finally {
        setBranchLoading(false);
      }
    }

    // ---- Branch: Fork ----
    async function handleFork(msg, forkOptions) {
      setBranchLoading(true);
      setForkModal(null);
      const requestId = crypto.randomUUID();
      try {
        const payload = { request_id: requestId };
        if (forkOptions && forkOptions.initial) {
          payload.initial = true;
        } else if (msg && msg.turn_id) {
          payload.turn_id = msg.turn_id;
        } else {
          payload.initial = true;
        }
        if (forkOptions && forkOptions.title) payload.title = forkOptions.title;

        const result = await Api.forkConversation(conversationId, payload);
        const newConvId = result.conversation_id || result.id || (result.conversation && result.conversation.id);
        if (newConvId) {
          onNavigate('ChatScreen', { conversationId: newConvId });
          toast.info('Branched: story forked.');
        }
      } catch (err) {
        toast.error(window.RPComponents.formatError(err));
      } finally {
        setBranchLoading(false);
      }
    }

    // ---- Branch: Edit ----
    async function handleEdit(msg, newContent) {
      setBranchLoading(true);
      setEditModal(null);
      const requestId = crypto.randomUUID();
      try {
        const payload = { turn_id: msg.turn_id, content: newContent, request_id: requestId };
        const result = await Api.editConversation(conversationId, payload);
        const newConvId = result.conversation_id || result.id || (result.conversation && result.conversation.id);
        if (newConvId) {
          onNavigate('ChatScreen', { conversationId: newConvId });
          toast.info('Branched: message edited.');
        }
      } catch (err) {
        toast.error(window.RPComponents.formatError(err));
      } finally {
        setBranchLoading(false);
      }
    }

    // ---- Key handler in composer ----
    function handleComposerKeyDown(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    }

    const charCount = composerText.length;
    const charCountClass = charCount > 15500 ? 'at-limit' : charCount > 14000 ? 'near-limit' : '';

    if (loading) return React.createElement(
      'div',
      { className: 'chat-layout' },
      React.createElement('div', { className: 'chat-sidebar' }),
      React.createElement('div', { className: 'chat-main', style: { alignItems: 'center', justifyContent: 'center' } },
        React.createElement(LoadingWrap, null)),
      React.createElement('div', { className: 'chat-state-panel' })
    );

    return React.createElement(
      'div',
      { className: 'chat-layout' },

      // ---- Left sidebar ----
      React.createElement(
        'div',
        { className: 'chat-sidebar' },
        React.createElement(
          'div',
          { className: 'chat-sidebar-header' },
          React.createElement('div', { className: 'chat-sidebar-title' }, conversation?.title || 'Story'),
          React.createElement(
            'div',
            { style: { display: 'flex', gap: '4px', marginTop: '8px' } },
            React.createElement('button', { className: 'btn-ghost btn-sm', onClick: () => onNavigate('SavedStories') }, '← Stories')
          )
        ),
        React.createElement(
          'div',
          { className: 'chat-sidebar-body' },
          React.createElement(WsStatusBar, { status: wsStatus, reconnectIn: wsReconnectIn }),
          conversation?.parent_conversation_id && React.createElement(
            'div',
            null,
            React.createElement('div', { className: 'section-title' }, 'Branch Parent'),
            React.createElement(
              'a',
              {
                href: '#',
                style: { fontSize: '0.8125rem' },
                onClick: e => { e.preventDefault(); onNavigate('ChatScreen', { conversationId: conversation.parent_conversation_id }); }
              },
              'View parent story'
            )
          ),
          error && React.createElement(ErrorBanner, { error, onDismiss: () => setError(null) })
        )
      ),

      // ---- Center: messages + composer ----
      React.createElement(
        'div',
        { className: 'chat-main' },

        // Messages
        React.createElement(
          'div',
          { className: 'chat-messages' },
          hasMoreHistory && React.createElement(
            'div',
            { className: 'chat-history-load' },
            React.createElement(
              'button',
              { className: 'btn-secondary btn-sm', onClick: loadOlderHistory, disabled: historyLoading },
              historyLoading ? 'Loading...' : 'Load older messages'
            )
          ),
          messages.length === 0 && !loading && React.createElement(
            'div',
            { style: { textAlign: 'center', color: 'var(--color-text-muted)', padding: '40px 20px' } },
            'Start the conversation below.'
          ),
          messages.map(msg => React.createElement(MessageRow, {
            key: msg.id,
            msg,
            onFork: (m) => setForkModal(m),
            onRegenerate: handleRegenerate,
            onEdit: (m) => setEditModal(m),
            isBranchLoading: branchLoading,
          })),
          React.createElement('div', { ref: messagesEndRef })
        ),

        // Blocked reason
        blockedReason && React.createElement(
          'div',
          { className: 'action-blocked-box' },
          'Action blocked: ', blockedReason
        ),

        // Turn status bar
        React.createElement(
          'div',
          { className: 'turn-status-bar' },
          React.createElement(
            'div',
            { className: 'turn-status-label' },
            turnStatus
              ? React.createElement(React.Fragment, null,
                  React.createElement('span', null, 'Turn:'),
                  React.createElement('span', { className: `turn-status-stage ${turnStatus.stage || turnStatus.status}` },
                    (turnStatus.stage || turnStatus.status || '').toUpperCase())
                )
              : React.createElement('span', { style: { opacity: 0.5 } }, 'Ready')
          ),
          turnStatus?.status === 'failed' && React.createElement(
            'button',
            { className: 'btn-secondary btn-sm', onClick: handleRetry },
            'Retry'
          )
        ),

        // Composer
        React.createElement(
          'div',
          { className: 'composer' },
          sendError && React.createElement(ErrorBanner, { error: sendError, onDismiss: () => setSendError(null) }),
          React.createElement(
            'div',
            { className: 'composer-row' },
            React.createElement('textarea', {
              className: 'composer-textarea',
              value: composerText,
              onChange: e => setComposerText(e.target.value),
              onKeyDown: handleComposerKeyDown,
              placeholder: isLocked ? 'Waiting for story to continue...' : 'What do you do? (Enter to send, Shift+Enter for newline)',
              disabled: isLocked || sending,
              maxLength: 16000,
              rows: 2,
            }),
            React.createElement(
              'button',
              {
                className: 'btn-primary composer-send',
                onClick: handleSend,
                disabled: isLocked || sending || !composerText.trim(),
              },
              sending ? 'Sending...' : 'Send'
            )
          ),
          React.createElement(
            'div',
            { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
            isLocked && React.createElement('span', { className: 'composer-locked-notice' }, 'Story is generating — please wait...'),
            React.createElement('span', { className: `composer-char-count ${charCountClass}` }, `${charCount}/16000`)
          )
        )
      ),

      // ---- Right: state panel ----
      React.createElement(StatePanel, { gameState, conversationId, onNavigate }),

      // ---- Modals ----
      forkModal && React.createElement(ForkModal, {
        message: forkModal,
        onConfirm: (opts) => handleFork(forkModal, opts),
        onClose: () => setForkModal(null),
      }),

      editModal && React.createElement(EditMessageModal, {
        message: editModal,
        onConfirm: (msg, content) => handleEdit(msg, content),
        onClose: () => setEditModal(null),
      })
    );
  }

  if (!window.RPScreens) window.RPScreens = {};
  window.RPScreens.ChatScreen = ChatScreen;
})();
