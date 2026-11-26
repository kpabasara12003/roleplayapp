// Generated from api/client.ts; source-sha256: 605dac2f0cc24b2c20ac83a4d3f3fbaf3518ff16d16c8d43f6190a74c386638a
"use strict";
// src/api/client.ts → window.RPApi
// HTTP client with auth, error handling, status preservation, and configurable base URL
(function () {
    const defaultBase = 'http://localhost:8000';
    function normalizeBase(value) {
        const url = new URL(value || defaultBase);
        if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash)
            throw new Error('Use an HTTP(S) server URL without credentials, query or fragment.');
        return url.href.replace(/\/+$/, '');
    }
    function getApiBase() {
        try {
            return normalizeBase(localStorage.getItem('rp_api_base') || defaultBase);
        }
        catch (_) {
            return defaultBase;
        }
    }
    function setApiBase(value) {
        const next = normalizeBase(value.trim() || defaultBase);
        const changed = next !== getApiBase();
        if (changed)
            window.RPSession.clearAll();
        localStorage.setItem('rp_api_base', next);
        return changed;
    }
    function getWsBase() {
        const api = getApiBase();
        if (api.startsWith('https://'))
            return api.replace(/^https:\/\//, 'wss://');
        if (api.startsWith('http://'))
            return api.replace(/^http:\/\//, 'ws://');
        return 'ws://localhost:8000';
    }
    class ApiError extends Error {
        status;
        detail;
        fieldErrors;
        constructor(status, detail, fieldErrors = null) {
            super(detail || `HTTP ${status}`);
            this.status = status;
            this.detail = detail;
            this.fieldErrors = fieldErrors || null;
        }
    }
    async function request(method, path, body, extraHeaders) {
        if (!path.startsWith('/') || path.startsWith('//'))
            throw new ApiError(0, 'Invalid API path.');
        const base = getApiBase();
        const bound = localStorage.getItem('rp_session_base');
        const apiKey = window.RPSession.getApiKey();
        if (apiKey && bound && bound !== base)
            throw new ApiError(401, 'Sign in to the selected server.');
        const headers = {
            'Content-Type': 'application/json',
            ...(apiKey ? { 'X-API-Key': apiKey } : {}),
            ...(extraHeaders || {}),
        };
        const options = {
            method,
            redirect: 'error', credentials: 'omit', cache: 'no-store',
            headers,
            ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
        };
        let response;
        try {
            response = await fetch(`${getApiBase()}${path}`, options);
        }
        catch (err) {
            throw new ApiError(0, 'Network error: ' + (err instanceof Error ? err.message : 'Failed to connect to backend'));
        }
        // 204 No Content
        if (response.status === 204)
            return null;
        let data;
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            try {
                data = await response.json();
            }
            catch {
                data = null;
            }
        }
        else {
            data = null;
        }
        if (response.ok)
            return data;
        // Error handling by status
        switch (response.status) {
            case 401:
                if (apiKey && !path.startsWith('/users/login'))
                    window.dispatchEvent(new Event('rp:unauthorized'));
                throw new ApiError(401, 'Authentication required or API key expired. Please log in again.');
            case 404:
                throw new ApiError(404, (data && data.detail) || 'Resource not found.');
            case 409:
                throw new ApiError(409, (data && data.detail) || 'Conflict — please refresh.');
            case 422: {
                let fieldErrors = null;
                if (data && data.detail && Array.isArray(data.detail)) {
                    fieldErrors = {};
                    data.detail.forEach((e) => {
                        const field = e.loc?.slice(1).join('.') || 'general';
                        fieldErrors[field] = e.msg;
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
    async function register(username, password, email) {
        const payload = { username, password };
        if (email)
            payload.email = email;
        return request('POST', '/users/register', payload);
    }
    async function login(username, password) {
        return request('POST', '/users/login', { username, password });
    }
    async function rotateKey() {
        return request('POST', '/users/rotate-key');
    }
    // ---- Scenarios ----
    async function getScenarios() {
        return request('GET', '/scenarios');
    }
    async function createScenario(data) {
        return request('POST', '/scenarios', data);
    }
    async function getScenario(id) {
        return request('GET', `/scenarios/${id}`);
    }
    async function updateScenario(id, data) {
        return request('PATCH', `/scenarios/${id}`, data);
    }
    async function deleteScenario(id) {
        return request('DELETE', `/scenarios/${id}`);
    }
    async function publishScenario(id) {
        return request('POST', `/scenarios/${id}/publish`);
    }
    // ---- Characters ----
    async function getCharacters(scenarioId) {
        return request('GET', `/characters?scenario_id=${scenarioId}`);
    }
    async function createCharacter(scenarioId, data) {
        return request('POST', '/characters', { ...data, scenario_id: Number(scenarioId) });
    }
    async function updateCharacter(characterId, data) {
        return request('PATCH', `/characters/${characterId}`, data);
    }
    async function deleteCharacter(characterId) {
        return request('DELETE', `/characters/${characterId}`);
    }
    // ---- Lore ----
    async function getLore(scenarioId) {
        return request('GET', `/scenarios/${scenarioId}/lore`);
    }
    async function createLore(scenarioId, data) {
        return request('POST', `/scenarios/${scenarioId}/lore`, data);
    }
    async function updateLore(scenarioId, loreId, data) {
        return request('PUT', `/scenarios/${scenarioId}/lore/${loreId}`, data);
    }
    async function deleteLore(scenarioId, loreId) {
        return request('DELETE', `/scenarios/${scenarioId}/lore/${loreId}`);
    }
    // ---- Catalog ----
    async function getCatalog(params) {
        const qs = params ? '?' + new URLSearchParams(params).toString() : '';
        return request('GET', `/catalog/scenarios${qs}`);
    }
    async function searchCatalog(params) {
        return request('GET', '/catalog/search?' + new URLSearchParams(params).toString());
    }
    async function getCatalogFilters() {
        return request('GET', '/catalog/filters');
    }
    // ---- Chat ----
    async function startChat(data) {
        return request('POST', '/chat/start', data);
    }
    async function sendMessage(conversationId, data) {
        return request('POST', '/chat/send', {
            conversation_id: Number(conversationId),
            content: data.content,
            request_id: data.request_id,
        });
    }
    async function getTurn(turnId) {
        return request('GET', `/chat/turn/${turnId}`);
    }
    async function retryTurn(turnId) {
        return request('POST', `/chat/turn/${turnId}/retry`);
    }
    // ---- Conversations ----
    async function getConversations(params) {
        const qs = params ? '?' + new URLSearchParams(params).toString() : '';
        return request('GET', `/conversations${qs}`);
    }
    async function getConversation(id) {
        return request('GET', `/conversations/${id}`);
    }
    async function updateConversation(id, data) {
        return request('PATCH', `/conversations/${id}`, data);
    }
    async function resumeConversation(id) {
        return request('GET', `/conversations/${id}/resume`);
    }
    async function getChatHistory(id, params) {
        const qs = params ? '?' + new URLSearchParams(params).toString() : '';
        return request('GET', `/chat/history/${id}${qs}`);
    }
    // ---- Branch actions ----
    async function forkConversation(id, data) {
        return request('POST', `/conversations/${id}/fork`, data);
    }
    async function regenerateConversation(id, data) {
        return request('POST', `/conversations/${id}/regenerate`, data);
    }
    async function editConversation(id, data) {
        return request('POST', `/conversations/${id}/edit`, data);
    }
    // ---- WebSocket ticket ----
    async function getTicket(conversationId) {
        return request('POST', `/chat/ticket/${conversationId}`);
    }
    // ---- Preferences ----
    async function getPreferences() {
        return request('GET', '/preferences');
    }
    async function updatePreferences(data) {
        return request('PUT', '/preferences', data);
    }
    // ---- Personas ----
    async function getPersonas() {
        return request('GET', '/personas');
    }
    async function createPersona(data) {
        return request('POST', '/personas', data);
    }
    async function updatePersona(id, data) {
        return request('PUT', `/personas/${id}`, data);
    }
    async function deletePersona(id) {
        return request('DELETE', `/personas/${id}`);
    }
    // ---- Memories & Notes ----
    async function getMemories(conversationId) {
        return request('GET', `/conversations/${conversationId}/memories`);
    }
    async function patchMemory(conversationId, factId, data) {
        return request('PATCH', `/conversations/${conversationId}/memories/${factId}`, data);
    }
    async function addNote(conversationId, data) {
        return request('POST', `/conversations/${conversationId}/memories/notes`, data);
    }
    async function deleteNote(conversationId, noteId) {
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
