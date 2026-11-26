// src/api/ws.ts → window.RPWs
// WebSocket manager: single-use ticket, exponential backoff, sequence tracking, event dispatcher

(function() {
  class WsManager {
    constructor() {
      this._ws = null;
      this._conversationId = null;
      this._lastSeq = null;
      this._listeners = {};   // eventType → Set of callbacks
      this._reconnectTimer = null;
      this._reconnectDelay = 1000;
      this._maxDelay = 30000;
      this._shouldReconnect = false;
      this._connecting = false;
      this._connected = false;
      this._epoch = 0;
      this._currentTicket = null;
      this._statusListeners = new Set();
    }

    // ---- Event emitter ----
    on(eventType, cb) {
      if (!this._listeners[eventType]) this._listeners[eventType] = new Set();
      this._listeners[eventType].add(cb);
    }

    off(eventType, cb) {
      if (this._listeners[eventType]) this._listeners[eventType].delete(cb);
    }

    emit(eventType, data, seq) {
      const listeners = this._listeners[eventType];
      if (listeners) {
        listeners.forEach(cb => {
          try { cb(data, seq); } catch(e) { console.error('WS listener error:', e); }
        });
      }
    }

    onStatus(cb) { this._statusListeners.add(cb); }
    offStatus(cb) { this._statusListeners.delete(cb); }

    _emitStatus(status, extra) {
      this._statusListeners.forEach(cb => { try { cb(status, extra); } catch(e) {} });
    }

    // ---- Connect ----
    async connect(conversationId, lastSeq) {
      this.disconnect();
      this._conversationId = conversationId;
      // Recover last seen seq from store if not provided
      if (lastSeq !== undefined && lastSeq !== null) {
        this._lastSeq = lastSeq;
      } else {
        const stored = localStorage.getItem(`chat_last_seq_${conversationId}`);
        this._lastSeq = stored ? Number(stored) : null;
      }
      this._shouldReconnect = true;
      this._reconnectDelay = 1000;
      await this._doConnect();
    }

    async _doConnect() {
      if (this._connecting || (this._ws && this._ws.readyState === WebSocket.OPEN)) return;
      const epoch = this._epoch;
      this._connecting = true;
      this._emitStatus('connecting');

      let ticket;
      try {
        const result = await window.RPApi.getTicket(this._conversationId);
        if (epoch !== this._epoch || !this._shouldReconnect) return;
        ticket = result && (result.ticket || result.token || result.ws_ticket);
        if (!ticket) throw new Error('No ticket returned by backend');
      } catch (err) {
        if (epoch !== this._epoch) return;
        this._connecting = false;
        if (err.status === 401 || err.status === 404) {
          this._shouldReconnect = false;
          this._emitStatus('disconnected', { reason: 'Unauthorized or unavailable story' });
          return;
        }
        this._scheduleReconnect();
        return;
      }

      this._currentTicket = ticket;

      const wsBase = window.RPApi.getWsBase ? window.RPApi.getWsBase() : 'ws://localhost:8000';
      let url = `${wsBase}/chat/ws/${this._conversationId}?ticket=${encodeURIComponent(ticket)}`;
      if (this._lastSeq !== null && this._lastSeq !== undefined) {
        url += `&last_seen_seq=${this._lastSeq}`;
      }

      let ws;
      try {
        ws = new WebSocket(url);
      } catch (err) {
        this._connecting = false;
        this._scheduleReconnect();
        return;
      }
      this._ws = ws;

      ws.onopen = () => {
        if (epoch !== this._epoch || this._ws !== ws) return;
        this._connecting = false;
        this._connected = true;
        this._reconnectDelay = 1000;
        this._emitStatus('connected');
        this.emit('ws_open', {});
      };

      ws.onmessage = (event) => {
        if (epoch !== this._epoch || this._ws !== ws) return;
        try {
          const raw = JSON.parse(event.data);
          this._handleFrame(raw);
        } catch (e) {
          console.warn('Ignored malformed live event');
        }
      };

      ws.onclose = (event) => {
        if (epoch !== this._epoch || this._ws !== ws) return;
        this._connecting = false;
        this._connected = false;
        this._ws = null;
        this._emitStatus('disconnected');
        this.emit('ws_close', { code: event.code, reason: event.reason });

        if (event.code === 1008) this._shouldReconnect = false;
        // If closed with 1008 (policy violation / expired ticket), we can re-request a ticket once if still authorized
        if (this._shouldReconnect) {
          this._scheduleReconnect();
        }
      };

      ws.onerror = (err) => {
        if (epoch !== this._epoch || this._ws !== ws) return;
        console.error('WS socket error:', err);
        this.emit('ws_error', { error: err });
      };
    }

    _handleFrame(frame) {
      // Backend frame shape: { stream_sequence_id, event_body }
      // where event_body has { event: "...", payload: { ... } }
      const seq = frame.stream_sequence_id ?? frame.seq ?? null;

      // Update and persist last seq
      if (seq !== null && seq !== undefined && this._conversationId) {
        this._lastSeq = Math.max(this._lastSeq || 0, seq);
        try {
          localStorage.setItem(`chat_last_seq_${this._conversationId}`, String(this._lastSeq));
        } catch (e) {}
      }

      let eventType = null;
      let eventPayload = {};

      if (frame.event_body && typeof frame.event_body === 'object') {
        eventType = frame.event_body.event;
        eventPayload = { ...frame.event_body, ...(frame.event_body.payload || {}) };
      } else if (frame.event) {
        eventType = frame.event;
        eventPayload = { ...frame, ...(frame.payload || {}) };
      } else if (frame.type) {
        eventType = frame.type;
        eventPayload = frame.data || {};
      } else if (frame.error) {
        eventType = 'error';
        eventPayload = { message: frame.error };
      }

      if (!eventType) return;

      // Handle ping → pong
      if (eventType === 'ping') {
        if (this._ws && this._ws.readyState === WebSocket.OPEN) {
          this._ws.send(JSON.stringify({ type: 'pong' }));
        }
        return;
      }

      // Emit specific event and wildcard
      this.emit(eventType, eventPayload, seq);
      this.emit('*', { type: eventType, data: eventPayload, seq });
    }

    _scheduleReconnect() {
      if (this._reconnectTimer) clearTimeout(this._reconnectTimer);
      if (!this._shouldReconnect) return;

      // Exponential backoff with jitter (±20%)
      const jitter = (Math.random() - 0.5) * 0.4 * this._reconnectDelay;
      const delay = Math.round(Math.min(this._reconnectDelay + jitter, this._maxDelay));

      this._emitStatus('reconnecting', { delay, nextAttemptAt: Date.now() + delay });

      this._reconnectTimer = setTimeout(() => {
        if (this._shouldReconnect) {
          this._doConnect();
        }
      }, delay);

      this._reconnectDelay = Math.min(this._reconnectDelay * 2, this._maxDelay);
    }

    // ---- Send via WS (alternative transport) ----
    send(content, requestId) {
      if (!this._ws || this._ws.readyState !== WebSocket.OPEN) {
        throw new Error('WebSocket not connected');
      }
      const payload = { content, request_id: requestId };
      this._ws.send(JSON.stringify(payload));
    }

    // ---- Disconnect ----
    disconnect() {
      this._epoch++;
      this._shouldReconnect = false;
      if (this._reconnectTimer) {
        clearTimeout(this._reconnectTimer);
        this._reconnectTimer = null;
      }
      if (this._ws) {
        try {
          this._ws.onclose = null;
          this._ws.close(1000, 'Client intentional close');
        } catch(e) {}
        this._ws = null;
      }
      this._connected = false;
      this._connecting = false;
      this._emitStatus('disconnected');
    }

    // ---- State ----
    get isConnected() { return this._connected; }
    get isConnecting() { return this._connecting; }

    // ---- Reset for new conversation ----
    reset() {
      this.disconnect();
      this._listeners = {};
      this._statusListeners = new Set();
      this._conversationId = null;
      this._lastSeq = null;
      this._reconnectDelay = 1000;
    }
  }

  window.RPWs = { WsManager };
})();
