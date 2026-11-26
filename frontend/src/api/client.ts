type ApiId = number | string;
type ApiPayload = Record<string, unknown>;
type QueryParams = Record<string, string>;
interface Window {
  RPSession: { getApiKey(): string | null; clearAll(): void };
  RPApi: Record<string, Function>;
}

// src/api/client.ts → window.RPApi
// HTTP client with auth, error handling, status preservation, and configurable base URL

(function() {
  const defaultBase = 'http://localhost:8000';
  function normalizeBase(value: string) {
    const url = new URL(value || defaultBase);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('Use an HTTP(S) server URL without credentials, query or fragment.');
    return url.href.replace(/\/+$/, '');
  }
  function getApiBase() {
    try { return normalizeBase(localStorage.getItem('rp_api_base') || defaultBase); }
    catch (_) { return defaultBase; }
  }
  function setApiBase(value: string) {
    const next = normalizeBase(value.trim() || defaultBase);
    const changed = next !== getApiBase();
    if (changed) window.RPSession.clearAll();
    localStorage.setItem('rp_api_base', next);
    return changed;
  }

  function getWsBase() {
    const api = getApiBase();
    if (api.startsWith('https://')) return api.replace(/^https:\/\//, 'wss://');
    if (api.startsWith('http://')) return api.replace(/^http:\/\//, 'ws://');
    return 'ws://localhost:8000';
  }

  class ApiError extends Error {
    status: number;
    detail: string;
    fieldErrors: Record<string, string> | null;
    constructor(status: number, detail: string, fieldErrors: Record<string, string> | null = null) {
      super(detail || `HTTP ${status}`);
      this.status = status;
      this.detail = detail;
      this.fieldErrors = fieldErrors || null;
    }
  }

  async function request(method: string, path: string, body?: unknown, extraHeaders?: Record<string, string>) {
    if (!path.startsWith('/') || path.startsWith('//')) throw new ApiError(0, 'Invalid API path.');
    const base = getApiBase();
    const bound = localStorage.getItem('rp_session_base');
    const apiKey = window.RPSession.getApiKey();
    if (apiKey && bound && bound !== base) throw new ApiError(401, 'Sign in to the selected server.');
    const headers = {
      'Content-Type': 'application/json',
      ...(apiKey ? { 'X-API-Key': apiKey } : {}),
      ...(extraHeaders || {}),
    };

    const options: RequestInit = {
      method,
      redirect: 'error', credentials: 'omit', cache: 'no-store',
      headers,
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    };

    let response;
    try {
      response = await fetch(`${getApiBase()}${path}`, options);
    } catch (err) {
      throw new ApiError(0, 'Network error: ' + (err instanceof Error ? err.message : 'Failed to connect to backend'));
    }

    // 204 No Content
    if (response.status === 204) return null;

    let data;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      try { data = await response.json(); } catch { data = null; }
    } else {
      data = null;
    }

    if (response.ok) return data;

    // Error handling by status
    switch (response.status) {
      case 401:
        if (apiKey && !path.startsWith('/users/login')) window.dispatchEvent(new Event('rp:unauthorized'));
        throw new ApiError(401, 'Authentication required or API key expired. Please log in again.');
      case 404:
        throw new ApiError(404, (data && data.detail) || 'Resource not found.');
      case 409:
        throw new ApiError(409, (data && data.detail) || 'Conflict — please refresh.');
      case 422: {
        let fieldErrors: Record<string, string> | null = null;
        if (data && data.detail && Array.isArray(data.detail)) {
          fieldErrors = {};
          data.detail.forEach((e: {loc?: (string | number)[]; msg: string}) => {
            const field = e.loc?.slice(1).join('.') || 'general';
            fieldErrors![field] = e.msg;
          });
        }
        throw new ApiError(422, (data && typeof data.detail === 'string' ? data.detail : 'Validation error.'), fieldErrors);
      }
      case 429:
        throw new ApiError(429, 'Too many requests. Please wait before trying again.');
      case 413:
        throw new ApiError(413, 'This draft is too large. Reduce the rules or initial-state data.');
      default:
        throw new ApiError(response.status, (data && data.detail) || `Server error (${response.status})`);
    }
  }

  // ---- Auth ----
  async function register(username: string, password: string, email?: string) {
    const payload: {username: string; password: string; email?: string} = { username, password };
    if (email) payload.email = email;
    return request('POST', '/users/register', payload);
  }

  async function login(username: string, password: string) {
    return request('POST', '/users/login', { username, password });
  }

  async function rotateKey() {
    return request('POST', '/users/rotate-key');
  }

  // ---- Scenarios ----
  async function getScenarios() {
    return request('GET', '/scenarios');
  }

  async function createScenario(data: ApiPayload) {
    return request('POST', '/scenarios', data);
  }

  async function getScenario(id: ApiId) {
    return request('GET', `/scenarios/${id}`);
  }

  async function updateScenario(id: ApiId, data: ApiPayload) {
    return request('PATCH', `/scenarios/${id}`, data);
  }

  async function deleteScenario(id: ApiId) {
    return request('DELETE', `/scenarios/${id}`);
  }

  async function publishScenario(id: ApiId) {
    return request('POST', `/scenarios/${id}/publish`);
  }

  // ---- Characters ----
  async function getCharacters(scenarioId: ApiId) {
    return request('GET', `/characters?scenario_id=${scenarioId}`);
  }

  async function createCharacter(scenarioId: ApiId, data: ApiPayload) {
    return request('POST', '/characters', { ...data, scenario_id: Number(scenarioId) });
  }

  async function updateCharacter(characterId: ApiId, data: ApiPayload) {
    return request('PATCH', `/characters/${characterId}`, data);
  }

  async function deleteCharacter(characterId: ApiId) {
    return request('DELETE', `/characters/${characterId}`);
  }

  // ---- Lore ----
  async function getLore(scenarioId: ApiId) {
    return request('GET', `/scenarios/${scenarioId}/lore`);
  }

  async function createLore(scenarioId: ApiId, data: ApiPayload) {
    return request('POST', `/scenarios/${scenarioId}/lore`, data);
  }

  async function updateLore(scenarioId: ApiId, loreId: ApiId, data: ApiPayload) {
    return request('PUT', `/scenarios/${scenarioId}/lore/${loreId}`, data);
  }

  async function deleteLore(scenarioId: ApiId, loreId: ApiId) {
    return request('DELETE', `/scenarios/${scenarioId}/lore/${loreId}`);
  }

  // ---- Catalog ----
  async function getCatalog(params?: QueryParams) {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return request('GET', `/catalog/scenarios${qs}`);
  }

  async function searchCatalog(params: QueryParams) {
    return request('GET', '/catalog/search?' + new URLSearchParams(params).toString());
  }

  async function getCatalogFilters() {
    return request('GET', '/catalog/filters');
  }

  // ---- Chat ----
  async function startChat(data: ApiPayload) {
    return request('POST', '/chat/start', data);
  }

  async function sendMessage(conversationId: ApiId, data: ApiPayload) {
    return request('POST', '/chat/send', {
      conversation_id: Number(conversationId),
      content: data.content,
      request_id: data.request_id,
    });
  }

  async function getTurn(turnId: ApiId) {
    return request('GET', `/chat/turn/${turnId}`);
  }

  async function retryTurn(turnId: ApiId) {
    return request('POST', `/chat/turn/${turnId}/retry`);
  }

  // ---- Conversations ----
  async function getConversations(params?: QueryParams) {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return request('GET', `/conversations${qs}`);
  }

  async function getConversation(id: ApiId) {
    return request('GET', `/conversations/${id}`);
  }

  async function updateConversation(id: ApiId, data: ApiPayload) {
    return request('PATCH', `/conversations/${id}`, data);
  }

  async function resumeConversation(id: ApiId) {
    return request('GET', `/conversations/${id}/resume`);
  }

  async function getChatHistory(id: ApiId, params?: QueryParams) {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return request('GET', `/chat/history/${id}${qs}`);
  }

  // ---- Branch actions ----
  async function forkConversation(id: ApiId, data: ApiPayload) {
    return request('POST', `/conversations/${id}/fork`, data);
  }

  async function regenerateConversation(id: ApiId, data: ApiPayload) {
    return request('POST', `/conversations/${id}/regenerate`, data);
  }

  async function editConversation(id: ApiId, data: ApiPayload) {
    return request('POST', `/conversations/${id}/edit`, data);
  }

  // ---- WebSocket ticket ----
  async function getTicket(conversationId: ApiId) {
    return request('POST', `/chat/ticket/${conversationId}`);
  }

  // ---- Preferences ----
  async function getPreferences() {
    return request('GET', '/preferences');
  }

  async function updatePreferences(data: ApiPayload) {
    return request('PUT', '/preferences', data);
  }

  // ---- Personas ----
  async function getPersonas() {
    return request('GET', '/personas');
  }

  async function createPersona(data: ApiPayload) {
    return request('POST', '/personas', data);
  }

  async function updatePersona(id: ApiId, data: ApiPayload) {
    return request('PUT', `/personas/${id}`, data);
  }

  async function deletePersona(id: ApiId) {
    return request('DELETE', `/personas/${id}`);
  }

  // ---- Memories & Notes ----
  async function getMemories(conversationId: ApiId) {
    return request('GET', `/conversations/${conversationId}/memories`);
  }

  async function patchMemory(conversationId: ApiId, factId: ApiId, data: ApiPayload) {
    return request('PATCH', `/conversations/${conversationId}/memories/${factId}`, data);
  }

  async function addNote(conversationId: ApiId, data: ApiPayload) {
    return request('POST', `/conversations/${conversationId}/memories/notes`, data);
  }

  async function deleteNote(conversationId: ApiId, noteId: ApiId) {
    return request('DELETE', `/conversations/${conversationId}/memories/notes/${noteId}`);
  }

  window.RPApi = {
    ApiError,
    getApiBase,
    setApiBase,
    getWsBase,
    request,
    register,
    login,
    rotateKey,
    getScenarios,
    createScenario,
    getScenario,
    updateScenario,
    deleteScenario,
    publishScenario,
    getCharacters,
    createCharacter,
    updateCharacter,
    deleteCharacter,
    getLore,
    createLore,
    updateLore,
    deleteLore,
    getCatalog,
    getCatalogFilters,
    searchCatalog,
    startChat,
    sendMessage,
    getTurn,
    retryTurn,
    getConversations,
    getConversation,
    updateConversation,
    resumeConversation,
    getChatHistory,
    forkConversation,
    regenerateConversation,
    editConversation,
    getTicket,
    getPreferences,
    updatePreferences,
    getPersonas,
    createPersona,
    updatePersona,
    deletePersona,
    getMemories,
    patchMemory,
    addNote,
    deleteNote,
  };
})();
