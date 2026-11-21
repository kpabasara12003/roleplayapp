const API_BASE = "http://localhost:8000";
const WS_BASE = "ws://localhost:8000";
let chatSocket = null;

/**
 * Global streaming state parameters to stitch coming frames out-of-band
 */
let currentStreamingBubble = null;
let isStreamingActive = false;

/* ---------- Storage Helpers ---------- */
const store = {
    get: (k) => localStorage.getItem(k),
    set: (k, v) => localStorage.setItem(k, v),
    del: (k) => localStorage.removeItem(k),
};

function loadSession() {
    const apiKey = store.get("rp_api_key");
    const userId = store.get("rp_user_id");
    const username = store.get("rp_username");
    if (apiKey && userId && username) {
        document.getElementById("auth-section").classList.add("hidden");
        document.getElementById("app-section").classList.remove("hidden");
        document.getElementById("user-bar").classList.remove("hidden");
        document.getElementById("user-name").textContent = username;
        document.getElementById("user-avatar").textContent = username.charAt(0).toUpperCase();
        showApiKeyBox();
        loadScenarios();
    }
}

function clearSession() {
    store.del("rp_api_key");
    store.del("rp_user_id");
    store.del("rp_username");
    store.del("rp_active_scenario_id");
    store.del("rp_active_conv_id");
    store.del("rp_ai_char_id");
    store.del("rp_user_char_id");
    if (chatSocket) {
        chatSocket.onclose = null; // Prevent reconnect storms when deliberately clearing session
        chatSocket.close();
    }
}

function logout() {
    clearSession();
    location.reload();
}

/* ---------- HTTP Network Engine ---------- */
async function api(method, path, body = null) {
    const url = `${API_BASE}${path}`;
    const headers = { "Content-Type": "application/json" };
    const apiKey = store.get("rp_api_key");
    if (apiKey) headers["X-API-Key"] = apiKey;

    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);
    try {
        const res = await fetch(url, opts);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || res.statusText);
        return data;
    } catch (err) {
        toast(err.message, "error");
        throw err;
    }
}

function getApiKey() { return store.get("rp_api_key"); }

/* ---------- UI Interface Managers ---------- */
function toast(msg, type = "ok") {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.className = "";
    if (type === "error") el.classList.add("error");
    else el.classList.add("success");
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 3000);
}

function showTab(tab) {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.textContent.toLowerCase().includes(tab)));
    document.getElementById("login-tab").classList.toggle("hidden", tab !== "login");
    document.getElementById("register-tab").classList.toggle("hidden", tab !== "register");
}

function navTo(section) {
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.toggle("active", b.textContent.toLowerCase().includes(section)));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `${section}-panel`));
    if (section === "characters") loadScenariosForSelect();
    if (section === "chat") { loadScenariosForSelect(); loadCharactersForChat(); }
}

function showApiKeyBox() {
    document.getElementById("api-key-display").classList.remove("hidden");
    document.getElementById("stored-api-key").textContent = getApiKey();
}

function copyApiKey() {
    navigator.clipboard.writeText(getApiKey()).then(() => toast("API key copied!"));
}

/* ---------- Authentication Handlers ---------- */
async function doRegister() {
    const username = document.getElementById("reg-username").value.trim();
    const password = document.getElementById("reg-password").value;
    const email = document.getElementById("reg-email").value.trim();
    if (!username || !password) return toast("Username and password required", "error");

    const data = await api("POST", "/users/register", { username, password, email: email || null });
    if (data.api_key) {
        store.set("rp_api_key", data.api_key);
        store.set("rp_user_id", data.id);
        store.set("rp_username", data.username);
        showApiKeyBox();
        toast("Registered! Login to continue.");
        showTab('login');
        document.getElementById("login-username").value = username;
    }
}

async function doLogin() {
    const username = document.getElementById("login-username").value.trim();
    const password = document.getElementById("login-password").value;
    if (!username || !password) return toast("Username and password required", "error");

    const data = await api("POST", "/users/login", { username, password });
    if (data.api_key) {
        store.set("rp_api_key", data.api_key);
        store.set("rp_user_id", data.id);
        store.set("rp_username", data.username);

        document.getElementById("auth-section").classList.add("hidden");
        document.getElementById("app-section").classList.remove("hidden");
        document.getElementById("user-bar").classList.remove("hidden");
        document.getElementById("user-name").textContent = data.username;
        document.getElementById("user-avatar").textContent = data.username.charAt(0).toUpperCase();

        toast("Logged in successfully!");
        loadScenarios();
    }
}

/* ---------- Scenario Management ---------- */
async function createScenario() {
    const title = document.getElementById("sc-title").value.trim();
    if (!title) return toast("Title is required", "error");
    const body = {
        title,
        greeting: document.getElementById("sc-greeting").value.trim(),
        place: document.getElementById("sc-place").value.trim(),
        time: document.getElementById("sc-time").value.trim(),
        introduction: document.getElementById("sc-introduction").value.trim(),
        is_public: false,
    };
    await api("POST", "/scenarios", body);
    toast("Scenario created successfully");
    clearScenarioForm();
    loadScenarios();
}

function clearScenarioForm() {
    ["sc-title", "sc-greeting", "sc-place", "sc-time", "sc-introduction"].forEach((id) => (document.getElementById(id).value = ""));
}

async function loadScenarios() {
    const list = document.getElementById("scenarios-list");
    const rows = await api("GET", "/scenarios");
    if (!rows.length) { list.innerHTML = "<p>No scenarios found.</p>"; return; }
    list.innerHTML = rows.map((s) => `
        <div class="card" onclick="pickScenario(${s.id})">
            <div class="card-title">✨ ${esc(s.title)}</div>
            <div class="card-meta">📍 ${esc(s.place || "—")} | ⏳ ${esc(s.time || "—")}</div>
            <div class="card-meta">${esc(s.introduction || "No introduction provided.")}</div>
        </div>
    `).join("");
}

function pickScenario(id) {
    store.set("rp_active_scenario_id", id);
    toast(`Scenario #${id} selected`);
    navTo("characters");
}

function loadScenariosForSelect() {
    const sel = document.getElementById("char-scenario-select");
    const chatSel = document.getElementById("chat-scenario-select");
    api("GET", "/scenarios").then((rows) => {
        sel.innerHTML = '<option value="">Select Target Scenario *</option>';
        chatSel.innerHTML = '<option value="">Select Scenario *</option>';
        rows.forEach((s) => {
            const opt = new Option(s.title, s.id);
            sel.add(opt.cloneNode(true));
            chatSel.add(opt);
        });
        const active = store.get("rp_active_scenario_id");
        if (active) { sel.value = active; chatSel.value = active; }
    });
}

/* ---------- Character Configuration ---------- */
async function createCharacter() {
    const scenario_id = parseInt(document.getElementById("char-scenario-select").value, 10);
    if (!scenario_id) return toast("Select a scenario first", "error");
    const name = document.getElementById("char-name").value.trim();
    if (!name) return toast("Name is required", "error");

    const likes = document.getElementById("char-likes").value.split(",").map((x) => x.trim()).filter(Boolean);
    const dislikes = document.getElementById("char-dislikes").value.split(",").map((x) => x.trim()).filter(Boolean);

    const body = {
        scenario_id,
        is_ai: document.getElementById("char-is-ai").checked,
        name,
        gender: document.getElementById("char-gender").value.trim() || null,
        age: parseInt(document.getElementById("char-age").value, 10) || null,
        personality: document.getElementById("char-personality").value.trim() || null,
        likes: likes.length ? likes : null,
        dislikes: dislikes.length ? dislikes : null,
        backstory: document.getElementById("char-backstory").value.trim() || null,
        example_dialogue: document.getElementById("char-example-dialogue").value.trim() || null,
        greeting: document.getElementById("char-greeting").value.trim() || null,
        scenario: document.getElementById("char-scenario-desc").value.trim() || null,
        role_description: document.getElementById("char-role-desc").value.trim() || null,
    };

    await api("POST", "/characters", body);
    toast("Character created successfully");
    loadCharacters(scenario_id);
}

async function loadCharacters(scenarioId) {
    const list = document.getElementById("characters-list");
    if (!scenarioId) { list.innerHTML = "<p>Select a scenario to view characters.</p>"; return; }
    const rows = await api("GET", `/characters?scenario_id=${scenarioId}`);
    if (!rows.length) { list.innerHTML = "<p>No characters yet.</p>"; return; }
    list.innerHTML = rows.map((c) => `
        <div class="card">
            <div class="card-title">
                <span class="tag ${c.is_ai ? "ai" : "user"}">${c.is_ai ? "AI" : "User"}</span>
                ${esc(c.name)}
            </div>
            <div class="card-meta"><b>Personality:</b> ${esc(c.personality || "N/A")}</div>
            <div class="card-meta"><b>Role:</b> ${esc(c.role_description || "N/A")}</div>
            <button class="btn-outline" style="margin-top: 10px;" onclick="selectChatChar(${c.id}, ${c.is_ai ? 1 : 0})">
                Select for Chat
            </button>
        </div>
    `).join("");
}

function selectChatChar(id, isAi) {
    if (isAi) store.set("rp_ai_char_id", id);
    else store.set("rp_user_char_id", id);
    loadCharactersForChat();
    toast(`Character selected for chat`);
}

function loadCharactersForChat() {
    const aiSel = document.getElementById("chat-ai-char-select");
    const userSel = document.getElementById("chat-user-char-select");
    const scenarioId = store.get("rp_active_scenario_id");
    if (!scenarioId) { aiSel.innerHTML = userSel.innerHTML = ""; return; }
    api("GET", `/characters?scenario_id=${scenarioId}`).then((rows) => {
        aiSel.innerHTML = '<option value="">Select AI Character *</option>';
        userSel.innerHTML = '<option value="">Select Your Character</option>';
        rows.forEach((c) => {
            const opt = new Option(`${c.is_ai ? "[AI]" : "[User]"} ${c.name}`, c.id);
            if (c.is_ai) aiSel.add(opt);
            else userSel.add(opt);
        });
        const activeAi = store.get("rp_ai_char_id");
        const activeUser = store.get("rp_user_char_id");
        if (activeAi) aiSel.value = activeAi;
        if (activeUser) userSel.value = activeUser;
    });
}

/* ---------- State / System Node Utilities ---------- */
function updateWsStatus(status, text) {
    const indicator = document.querySelector(".status-indicator");
    const badge = document.getElementById("ws-status");
    if (!badge) return;

    if (status === 'connected') {
        if (indicator) indicator.classList.add("connected");
        badge.textContent = "Live Stream Connected";
        badge.style.color = "var(--success, #28a745)";
    } else if (status === 'connecting') {
        if (indicator) indicator.classList.remove("connected");
        badge.textContent = text || "Connecting...";
        badge.style.color = "#ffc107";
    } else {
        if (indicator) indicator.classList.remove("connected");
        badge.textContent = text || "Disconnected";
        badge.style.color = "var(--error, #dc3545)";
    }
}

/**
 * Toggles interface components when an LLM streaming request is executing
 */
function setFormLock(locked) {
    isStreamingActive = locked;
    const input = document.getElementById("chat-msg-input");
    const btn = document.getElementById("chat-send-btn");

    if (input) input.disabled = locked;
    if (btn) {
        btn.disabled = locked;
        btn.textContent = locked ? "⚡..." : "Send";
    }

    // HTML Element Suggestion: Add an optional global container with an ID of "agent-state-container"
    const stateContainer = document.getElementById("agent-state-container");
    if (stateContainer) {
        stateContainer.classList.toggle("processing-active", locked);
    }
}

/* ---------- Dynamic Event-Driven Streaming Chat ---------- */
async function startConversation() {
    const scenario_id = parseInt(document.getElementById("chat-scenario-select").value, 10);
    const ai_character_id = parseInt(document.getElementById("chat-ai-char-select").value, 10);
    const user_character_id = parseInt(document.getElementById("chat-user-char-select").value, 10) || null;
    if (!scenario_id || !ai_character_id) return toast("Select scenario and AI character required", "error");

    const conv = await api("POST", "/chat/start", { scenario_id, ai_character_id, user_character_id });
    store.set("rp_active_conv_id", conv.id);
    store.set("rp_active_scenario_id", scenario_id);
    store.set("rp_ai_char_id", ai_character_id);
    if (user_character_id) store.set("rp_user_char_id", user_character_id);

    document.getElementById("active-chat").classList.remove("hidden");
    document.getElementById("conv-id").textContent = conv.id;
    toast(`Session #${conv.id} activated`);

    connectWebSocket(conv.id);
    loadHistory();
}

let chatReconnectTimeout = 1000;

async function connectWebSocket(convId) {
    if (chatSocket) {
        chatSocket.onclose = null;
        chatSocket.close();
    }
    const apiKey = getApiKey();
    if (!apiKey) return;

    // Recover stream checkpoints if they exist
    const lastSeenSeq = store.get(`chat_last_seq_${convId}`);
    let ticket;
    try { ticket = (await api('POST', `/chat/ticket/${convId}`)).ticket; }
    catch (err) { updateWsStatus('disconnected', 'Authentication required'); return; }
    let wsUrl = `${WS_BASE}/chat/ws/${convId}?ticket=${ticket}`;
    if (lastSeenSeq) {
        wsUrl += `&last_seen_seq=${lastSeenSeq}`;
        console.log(`[WS] Attempting recovery playback starting from sequence: ${lastSeenSeq}`);
    } else {
        console.log(`[WS] Initiating a fresh, clean session stream.`);
    }

    chatSocket = new WebSocket(wsUrl);

    updateWsStatus('connecting', 'Connecting pipeline...');

    chatSocket.onopen = () => {
        updateWsStatus('connected');
        chatReconnectTimeout = 1000; // Reset connection timer backoff
    };

    chatSocket.onmessage = (event) => {
        try {
            const wrappedData = JSON.parse(event.data);

            // Track backend stream checkpoint sequence
            if (wrappedData.stream_sequence_id) {
                store.set(`chat_last_seq_${convId}`, wrappedData.stream_sequence_id);
            }

            // Unwrap the message and pass it to our existing UI rendering engine
            const packet = wrappedData.event_body || (wrappedData.error ? {event: "state_change", payload: {state: "error", error_detail: wrappedData.error}} : null);
            if (!packet) return;

            // -------------------------------------------------------------
            // PATTERN 1: State Tracking Notification Events
            // -------------------------------------------------------------
            if (packet.event === "state_change") {
                const state = packet.payload.state;
                const message = packet.payload.message;

                // HTML Element Suggestion: Bind text status feedback directly inside a dedicated element id="agent-state-text"
                const textEl = document.getElementById("agent-state-text");
                if (textEl) textEl.textContent = `[System Status]: ${message}`;

                if (state === "processing_memory" || state === "typing") {
                    setFormLock(true);
                } else if (state === "completed") {
                } else if (state === "error") {
                    setFormLock(false);
                    currentStreamingBubble = null;
                    toast(packet.payload.error_detail || "Generation tracking error caught", "error");
                }
            }

            // -------------------------------------------------------------
            // PATTERN 2: Real-time Token Stream Appending
            // -------------------------------------------------------------
            else if (packet.event === "text_chunk") {
                setFormLock(true);
                const chunk = packet.payload.chunk;
                const index = packet.payload.index;

                const box = document.getElementById("chat-messages");

                // Initialize text target slot on head token delivery
                if (index === 0 || !currentStreamingBubble) {
                    currentStreamingBubble = document.createElement("div");
                    currentStreamingBubble.className = "msg ai streaming-frame";
                    currentStreamingBubble.setAttribute("data-raw-content", "");
                    box.appendChild(currentStreamingBubble);
                }

                // Append and patch localized raw tokens continuously
                let currentRaw = currentStreamingBubble.getAttribute("data-raw-content") || "";
                currentRaw += chunk;
                currentStreamingBubble.setAttribute("data-raw-content", currentRaw);

                // Live format text rendering token transformations
                currentStreamingBubble.innerHTML = formatRoleplayText(currentRaw);
                box.scrollTop = box.scrollHeight;
            }

            // -------------------------------------------------------------
            // PATTERN 3: Event-Driven Persistence Confirmations
            // -------------------------------------------------------------
            else if (packet.event === "message_completed") {
                if (packet.payload.sender === "director") setFormLock(false);
                const msgId = packet.payload.message_id;
                const sender = packet.payload.sender;
                const content = packet.payload.full_content;

                // Handle system updates gracefully if fallback scenarios occurred
                if ((sender === "ai" || sender === "director") && currentStreamingBubble) {
                    currentStreamingBubble.classList.remove("streaming-frame");
                    currentStreamingBubble.setAttribute("id", `msg-index-${msgId}`);
                    currentStreamingBubble.innerHTML = formatRoleplayText(content);
                    currentStreamingBubble = null;
                } else if (sender === "ai" || sender === "director") {
                    if (!document.getElementById(`msg-index-${msgId}`)) {
                        appendMessage(sender, content);
                        document.getElementById("chat-messages").lastElementChild.id = `msg-index-${msgId}`;
                    }
                } else if (sender === "user") {
                    // Update user nodes to map primary keys assigned by ChroniclerAgent
                    const userNodes = document.querySelectorAll(".msg.user:not([id])");
                    if (userNodes.length > 0) {
                        userNodes[userNodes.length - 1].setAttribute("id", `msg-index-${msgId}`);
                    }
                }
            }

            // -------------------------------------------------------------
            // PATTERN 4: Director Gate Rejection
            // -------------------------------------------------------------
            else if (packet.event === "action_blocked") {
                setFormLock(false);
                currentStreamingBubble = null;
                const reason = packet.payload && packet.payload.reason;
                toast(reason || "Action rejected by the director.", "error");
            }
            // -------------------------------------------------------------
            // PATTERN 5: Director State / Narration Updates
            // -------------------------------------------------------------
            else if (packet.event === "director_state_change") {
                const state = packet.payload && packet.payload.state;
                const message = packet.payload && packet.payload.message;
                const textEl = document.getElementById("agent-state-text");
                if (textEl && message) textEl.textContent = `[Director]: ${message}`;
                if (state === "completed") setFormLock(false);
                if (state === "error") {
                    setFormLock(false);
                    currentStreamingBubble = null;
                    toast((packet.payload && packet.payload.error_detail) || "Director error", "error");
                }
            }
            else if (packet.event === "director_text_chunk") {
                const chunk = packet.payload && packet.payload.chunk;
                const index = packet.payload && packet.payload.index;
                const box = document.getElementById("chat-messages");
                if (index === 0 || !currentStreamingBubble || currentStreamingBubble.classList.contains("ai")) {
                    // start a fresh director bubble
                    currentStreamingBubble = document.createElement("div");
                    currentStreamingBubble.className = "msg director streaming-frame";
                    currentStreamingBubble.setAttribute("data-raw-content", "");
                    box.appendChild(currentStreamingBubble);
                }
                let currentRaw = currentStreamingBubble.getAttribute("data-raw-content") || "";
                currentRaw += chunk || "";
                currentStreamingBubble.setAttribute("data-raw-content", currentRaw);
                currentStreamingBubble.innerHTML = formatRoleplayText(currentRaw);
                box.scrollTop = box.scrollHeight;
            }
            else if (packet.event === "engine_state_updated") {
                const textEl = document.getElementById("agent-state-text");
                if (textEl) textEl.textContent = "[Engine]: world state updated";
            }

            // Legacy interface mappings back compatibility pass
            else if (!packet.event && packet.content && packet.sender) {
                appendMessage(packet.sender, packet.content);
            }
        } catch (e) {
            console.error("Failed to safely parse inbound WS streaming package:", e);
        }
    };

    chatSocket.onclose = (e) => {
        if (e.code === 1008) { setFormLock(false); updateWsStatus('disconnected', 'Access denied'); return; }
        console.warn(`[WS] Connection severed cleanly. Retrying bridge in ${chatReconnectTimeout}ms...`, e.reason);
        updateWsStatus('disconnected', `Retrying (${Math.round(chatReconnectTimeout / 1000)}s)...`);
        setFormLock(false);

        setTimeout(() => {
            chatReconnectTimeout = Math.min(chatReconnectTimeout * 2, 30000); // Exponential backoff capped at 30s
            // Ensure we only reconnect if the user hasn't switched conversations
            if (parseInt(store.get("rp_active_conv_id"), 10) === parseInt(convId, 10)) {
                connectWebSocket(convId);
            }
        }, chatReconnectTimeout);
    };

    chatSocket.onerror = (err) => {
        updateWsStatus('disconnected', 'WS Pipeline Error');
        setFormLock(false);
        console.error('WebSocket subsystem crash context:', err);
    };
}

async function sendMessage() {
    if (isStreamingActive) return; // Prevent prompt concurrency conflicts

    const input = document.getElementById("chat-msg-input");
    const content = input.value.trim();
    const requestId = crypto.randomUUID();
    if (!content) return;
    const convId = store.get("rp_active_conv_id");
    if (!convId) return toast("Initialize session first", "error");

    // Display immediately on interface layer
    appendMessage("user", content);
    input.value = "";
    setFormLock(true);

    // Pipe transaction updates across live channels
    if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
        chatSocket.send(JSON.stringify({ content, request_id: requestId }));
    } else {
        // Safe out-of-band automated backend fallbacks
        try {
            await api("POST", "/chat/send", { conversation_id: parseInt(convId, 10), content, request_id: requestId });
            setTimeout(loadHistory, 1200);
        } catch (e) {
            setFormLock(false);
            console.error(e);
        }
    }
}

function handleKeyPress(e) {
    if (e.key === 'Enter' && !isStreamingActive) {
        sendMessage();
    }
}

let lastHistoryCount = 0;
let lastHistoryConversation = null;
async function loadHistory() {
    const convId = store.get("rp_active_conv_id");
    if (!convId) return;
    const rows = await api("GET", `/chat/history/${convId}`);

    if (convId === lastHistoryConversation && rows.length === lastHistoryCount && document.getElementById("chat-messages").children.length > 0) {
        return;
    }

    lastHistoryConversation = convId;
    lastHistoryCount = rows.length;
    const box = document.getElementById("chat-messages");
    box.innerHTML = "";
    rows.forEach((m) => {
        const div = document.createElement("div");
        div.className = `msg ${m.sender}`;
        if (m.id) div.setAttribute("id", `msg-index-${m.id}`);
        div.innerHTML = formatRoleplayText(m.content);
        box.appendChild(div);
    });
    box.scrollTop = box.scrollHeight;
}

function appendMessage(sender, content) {
    const box = document.getElementById("chat-messages");
    const div = document.createElement("div");
    div.className = `msg ${sender}`;
    div.innerHTML = formatRoleplayText(content);
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

/* ---------- Text String Engine & Escape Sanitizers ---------- */
function esc(raw) {
    const div = document.createElement("div");
    div.textContent = raw;
    return div.innerHTML;
}

/**
 * Text Processor: Escapes HTML strings safely and highlights roleplay segments 
 * enclosed in asterisks (e.g., *smiles*) by wrapping them in descriptive CSS tags.
 * * CSS Implementation Suggestion:
 * Add this selector rule to your site stylesheet:
 * .msg .action-bubble {
 * font-style: italic;
 * color: var(--rp-action-color, #888896);
 * }
 */
function formatRoleplayText(rawString) {
    let clean = esc(rawString);

    // Process double asterisks bold mappings first
    clean = clean.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Process isolated single asterisk actions/feelings tags
    clean = clean.replace(/\*(.*?)\*/g, '<span class="action-bubble">*$1*</span>');

    // Translate structural line returns safely 
    return clean.replace(/\n/g, '<br>');
}

/* ---------- Application Bootstrap Initialization ---------- */
window.addEventListener("DOMContentLoaded", () => {
    loadSession();
    const convId = store.get("rp_active_conv_id");
    if (convId && document.getElementById("app-section").classList.contains("hidden") === false) {
        document.getElementById("active-chat").classList.remove("hidden");
        document.getElementById("conv-id").textContent = convId;
        connectWebSocket(convId);
        loadHistory();
    }
});
