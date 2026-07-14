const API_BASE = "http://127.0.0.1:3000";
const CHAT_STORAGE_KEY = "deadlock-coach.chat-history.v1";
const SETTINGS_STORAGE_KEY = "deadlock-coach.settings.v1";
const MAX_STORED_CONVERSATIONS = 24;
const DEFAULT_WINDOW_MATCHES = 20;
const RECENT_MATCH_PREVIEW_LIMIT = 12;
const WINDOW_OPTIONS = [
  { label: "Last 20 matches", matches: 20 },
  { label: "Last 30 matches", matches: 30 },
  { label: "Last 50 matches", matches: 50 },
];

const providerOptions = {
  openai: {
    label: "OpenAI",
    models: ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
    apiKeyLabel: "OpenAI API key",
    apiKeyPlaceholder: "sk-...",
  },
  gemini_api: {
    label: "Gemini API",
    models: ["gemini-flash-latest", "gemini-2.0-flash", "gemini-1.5-pro"],
    apiKeyLabel: "Google API key",
    apiKeyPlaceholder: "AIza...",
  },
  litellm_proxy: {
    label: "LiteLLM Proxy",
    models: ["gpt-5.4", "openai/gpt-4o-mini", "openai/gpt-4o", "openai/gpt-4.1-mini"],
    apiKeyLabel: "Proxy API key",
    apiKeyPlaceholder: "Proxy or OpenAI key",
  },
};

const state = {
  screen: "coach",
  selectedHero: "",
  selectedPlayerKey: "",
  selectedWindow: "",
  messages: [],
  chatSessionId: "",
  currentConversationId: "",
  conversations: [],
  draft: "",
  apiStatus: "checking",
  trackedAccounts: [],
  accountSummary: null,
  recentMatches: [],
  selectedAccount: null,
  summaryBusy: false,
  requestInFlight: false,
  accountSearchQuery: "",
  accountSearchResults: [],
  accountSearchStatus: "",
  accountSearchBusy: false,
  accountSyncBusyId: null,
  accountMenuOpen: false,
  historyExpanded: false,
  settingsOpen: false,
  bootstrapSettings: null,
  requestAbortController: null,
  requestSequence: 0,
  settingsDraft: {
    provider: "openai",
    model: "gpt-4o-mini",
    apiKey: "",
  },
  settingsStatus: "",
  expandedEvidence: {},
};

let threadShouldPinToBottom = false;
let accountSearchDebounceHandle = null;
let accountSearchRequestSequence = 0;

const navItems = [
  { id: "coach", title: "Coach", meta: "Conversation" },
];
const validScreenIds = new Set(navItems.map((item) => item.id));

const baseOptions = {
  heroes: ["Lash", "Infernus", "Wraith", "Pocket", "Seven"],
  windows: WINDOW_OPTIONS.map((option) => option.label),
};

const screenCopy = {
  coach: {
    title: "Coach",
    subtitle: "Ask what to queue next, which hero is stable, what changed this patch, how your win rates look, or what to test next.",
  },
};

function storageAvailable() {
  try {
    return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
  } catch (_error) {
    return false;
  }
}

function defaultSettingsDraft() {
  return {
    provider: "openai",
    model: "gpt-4o-mini",
    apiKey: "",
  };
}

function normalizeScreen(screen) {
  return validScreenIds.has(screen) ? screen : "coach";
}

function normalizeSettingsDraft(value = {}) {
  const provider = providerOptions[value.provider] ? value.provider : "openai";
  const models = providerOptions[provider].models;
  const requestedModel = String(value.model || "").trim();
  return {
    provider,
    model: models.includes(requestedModel) ? requestedModel : models[0],
    apiKey: String(value.apiKey || ""),
  };
}

function loadStoredSettings() {
  if (!storageAvailable()) return defaultSettingsDraft();

  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return defaultSettingsDraft();
    const parsed = JSON.parse(raw);
    return normalizeSettingsDraft(parsed);
  } catch (_error) {
    return defaultSettingsDraft();
  }
}

async function loadBootstrapSettings() {
  try {
    const response = await fetch(`${API_BASE}/api/dev/runtime-settings`);
    if (!response.ok) return null;
    const payload = await response.json();
    return normalizeSettingsDraft({
      provider: payload.provider,
      model: payload.model,
      apiKey: payload.api_key,
    });
  } catch (_error) {
    return null;
  }
}

function saveStoredSettings() {
  if (!storageAvailable()) return;

  try {
    window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(state.settingsDraft));
  } catch (_error) {
    // Ignore storage failures in MVP mode.
  }
}

function createConversationTitle(messages) {
  const firstUserMessage = messages.find((message) => message.role === "user" && String(message.text || "").trim());
  if (!firstUserMessage) return "New chat";

  const normalized = String(firstUserMessage.text).trim().replace(/\s+/g, " ");
  return normalized.length > 42 ? `${normalized.slice(0, 42)}...` : normalized;
}

function createConversationRecord(seed = {}) {
  const now = new Date().toISOString();
  return {
    id: seed.id || `chat_${Math.random().toString(36).slice(2, 10)}`,
    title: seed.title || "New chat",
    createdAt: seed.createdAt || now,
    updatedAt: seed.updatedAt || now,
    messages: Array.isArray(seed.messages) ? seed.messages : [],
    chatSessionId: seed.chatSessionId || "",
    selectedPlayerKey: seed.selectedPlayerKey || "",
    selectedHero: seed.selectedHero || "",
    selectedWindow: seed.selectedWindow || "",
  };
}

function estimatedRankLabel(account) {
  if (account.last_team_avg_rank) {
    return `Estimated rank: ${account.last_team_avg_rank}`;
  }
  if (account.last_team_avg_badge != null) {
    return `Estimated rank badge: ${account.last_team_avg_badge}`;
  }
  return null;
}

function trashIconSvg() {
  return `
    <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path d="M6.25 2.25h3.5l.45 1.25h2.05a.75.75 0 1 1 0 1.5h-.6l-.52 6.05A1.75 1.75 0 0 1 9.38 12.75H6.62a1.75 1.75 0 0 1-1.75-1.7L4.35 5H3.75a.75.75 0 1 1 0-1.5H5.8l.45-1.25Zm.6 1.25h2.3l-.16-.45h-1.98l-.16.45Zm-1 1.5.51 5.92a.25.25 0 0 0 .25.23h2.78a.25.25 0 0 0 .25-.23L10.15 5h-3.7Zm1.18 1.2a.6.6 0 0 1 .6.6v2.75a.6.6 0 1 1-1.2 0V6.8a.6.6 0 0 1 .6-.6Zm1.94 0a.6.6 0 0 1 .6.6v2.75a.6.6 0 1 1-1.2 0V6.8a.6.6 0 0 1 .6-.6Z" fill="currentColor"/>
    </svg>
  `;
}

function normalizeStoredMessage(message = {}) {
  return {
    role: message.role === "assistant" ? "assistant" : "user",
    text: String(message.text || ""),
    insight: String(message.insight || ""),
    bullets: Array.isArray(message.bullets) ? message.bullets.map((item) => String(item || "")).filter(Boolean) : [],
    coachAnswer: message.coachAnswer || null,
    confidence: message.confidence || null,
    evidenceGraph: Array.isArray(message.evidenceGraph) ? message.evidenceGraph : [],
    trace: message.trace || null,
    structuredOutput: message.structuredOutput || null,
    source: String(message.source || ""),
    warning: String(message.warning || ""),
  };
}

function normalizeStoredConversation(value = {}) {
  return createConversationRecord({
    id: value.id,
    title: value.title,
    createdAt: value.createdAt,
    updatedAt: value.updatedAt,
    messages: Array.isArray(value.messages) ? value.messages.map(normalizeStoredMessage) : [],
    chatSessionId: value.chatSessionId,
    selectedPlayerKey: value.selectedPlayerKey,
    selectedHero: value.selectedHero,
    selectedWindow: value.selectedWindow,
  });
}

function loadStoredConversations() {
  if (!storageAvailable()) return [];

  try {
    const raw = window.localStorage.getItem(CHAT_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map(normalizeStoredConversation)
      .filter((conversation) => hasConversationContent(conversation))
      .sort((left, right) => new Date(right.updatedAt) - new Date(left.updatedAt))
      .slice(0, MAX_STORED_CONVERSATIONS);
  } catch (_error) {
    return [];
  }
}

function saveStoredConversations() {
  if (!storageAvailable()) return;

  try {
    const conversations = state.conversations
      .filter((conversation) => hasConversationContent(conversation))
      .slice(0, MAX_STORED_CONVERSATIONS)
      .map((conversation) => ({
        id: conversation.id,
        title: conversation.title,
        createdAt: conversation.createdAt,
        updatedAt: conversation.updatedAt,
        messages: Array.isArray(conversation.messages) ? conversation.messages.map(normalizeStoredMessage) : [],
        chatSessionId: conversation.chatSessionId || "",
        selectedPlayerKey: conversation.selectedPlayerKey || "",
        selectedHero: conversation.selectedHero || "",
        selectedWindow: conversation.selectedWindow || "",
      }));
    window.localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(conversations));
  } catch (_error) {
    // Ignore storage failures in MVP mode.
  }
}

function clearStoredConversations() {
  if (!storageAvailable()) return;

  try {
    window.localStorage.removeItem(CHAT_STORAGE_KEY);
  } catch (_error) {
    // Ignore storage failures in MVP mode.
  }
}

function hasConversationContent(conversation) {
  if (!conversation || !Array.isArray(conversation.messages)) return false;
  return conversation.messages.some((message) => String(message.text || "").trim());
}

function historyConversations() {
  return state.conversations.filter((conversation) => hasConversationContent(conversation));
}

function currentConversation() {
  return state.conversations.find((conversation) => conversation.id === state.currentConversationId) || null;
}

function visibleConversations() {
  const conversations = historyConversations();
  if (state.historyExpanded) return conversations;

  const activeConversation =
    conversations.find((conversation) => conversation.id === state.currentConversationId) || conversations[0] || null;
  return activeConversation ? [activeConversation] : [];
}

function syncCurrentConversation() {
  const index = state.conversations.findIndex((conversation) => conversation.id === state.currentConversationId);
  if (index < 0) return;

  const previous = state.conversations[index];
  state.conversations[index] = {
    ...previous,
    title: createConversationTitle(state.messages),
    updatedAt: new Date().toISOString(),
    messages: state.messages
      .filter((message) => !message.loading)
      .map((message) => ({
        role: message.role,
        text: message.text,
        insight: message.insight || "",
        bullets: Array.isArray(message.bullets) ? message.bullets : [],
        coachAnswer: message.coachAnswer || null,
        confidence: message.confidence || null,
        evidenceGraph: Array.isArray(message.evidenceGraph) ? message.evidenceGraph : [],
        trace: message.trace || null,
        structuredOutput: message.structuredOutput || null,
        source: message.source || "",
        warning: message.warning || "",
      })),
    chatSessionId: state.chatSessionId || "",
    selectedPlayerKey: state.selectedPlayerKey || "",
    selectedHero: state.selectedHero || "",
    selectedWindow: state.selectedWindow || "",
  };
  state.conversations.sort((left, right) => new Date(right.updatedAt) - new Date(left.updatedAt));
  saveStoredConversations();
}

function applyConversation(conversation) {
  const previousPlayerKey = state.selectedPlayerKey || "";
  state.currentConversationId = conversation.id;
  state.expandedEvidence = {};
  state.messages = Array.isArray(conversation.messages)
    ? conversation.messages.map((message) => ({
        role: message.role,
        text: message.text,
        insight: message.insight || "",
        bullets: Array.isArray(message.bullets) ? message.bullets : [],
        coachAnswer: message.coachAnswer || null,
        confidence: message.confidence || null,
        evidenceGraph: Array.isArray(message.evidenceGraph) ? message.evidenceGraph : [],
        trace: message.trace || null,
        structuredOutput: message.structuredOutput || null,
        source: message.source || "",
        warning: message.warning || "",
        loading: false,
        stats: [],
      }))
    : [];
  state.chatSessionId = conversation.chatSessionId || "";
  state.selectedPlayerKey = conversation.selectedPlayerKey || previousPlayerKey;
  state.selectedHero = conversation.selectedHero || "";
  state.selectedWindow = conversation.selectedWindow || "";
  state.accountSummary = null;
  state.selectedAccount = null;
  state.draft = "";
  state.screen = "coach";
}

function createNewConversation() {
  const conversation = createConversationRecord({
    selectedPlayerKey: state.selectedPlayerKey || "",
    selectedWindow: state.selectedWindow || "",
  });
  state.conversations = [conversation, ...state.conversations.filter((item) => item.id !== conversation.id)];
  applyConversation(conversation);
  saveStoredConversations();
}

function removeConversation(conversationId) {
  const index = state.conversations.findIndex((conversation) => conversation.id === conversationId);
  if (index < 0) return false;

  const removingCurrent = state.currentConversationId === conversationId;
  state.conversations = state.conversations.filter((conversation) => conversation.id !== conversationId);

  if (!state.conversations.length) {
    createNewConversation();
    return true;
  }

  if (removingCurrent) {
    const nextConversation = state.conversations[Math.min(index, state.conversations.length - 1)] || state.conversations[0];
    if (nextConversation) {
      applyConversation(nextConversation);
    }
  }

  saveStoredConversations();
  return true;
}

function initializeConversations() {
  const stored = loadStoredConversations();
  if (stored.length) {
    state.conversations = stored;
    applyConversation(stored[0]);
    return;
  }

  state.conversations = [];
  createNewConversation();
}

function initializeSettings() {
  state.settingsDraft = loadStoredSettings();
}

async function hydrateSettingsFromBackend() {
  const defaultDraft = defaultSettingsDraft();
  const bootstrapSettings = await loadBootstrapSettings();
  if (!bootstrapSettings) return;
  state.bootstrapSettings = bootstrapSettings;

  const hasOnlyDefaults =
    state.settingsDraft.provider === defaultDraft.provider && state.settingsDraft.model === defaultDraft.model;
  const hasNoKey = !String(state.settingsDraft.apiKey || "").trim();
  const looksLikeOldDirectOpenAiSetup =
    state.settingsDraft.provider === "openai" &&
    bootstrapSettings.provider === "litellm_proxy" &&
    String(state.settingsDraft.apiKey || "").trim() !== "" &&
    state.settingsDraft.apiKey === bootstrapSettings.apiKey;

  if (!hasNoKey && !looksLikeOldDirectOpenAiSetup) return;

  state.settingsDraft = normalizeSettingsDraft({
    provider: hasOnlyDefaults || looksLikeOldDirectOpenAiSetup ? bootstrapSettings.provider : state.settingsDraft.provider,
    model: hasOnlyDefaults || looksLikeOldDirectOpenAiSetup ? bootstrapSettings.model : state.settingsDraft.model,
    apiKey: bootstrapSettings.apiKey || state.settingsDraft.apiKey,
  });
  saveStoredSettings();
  renderApp();
}

function formatConversationTime(value) {
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "";

  const diffMs = Date.now() - timestamp;
  const diffMinutes = Math.floor(diffMs / 60000);
  if (diffMinutes < 1) return "Now";
  if (diffMinutes < 60) return `${diffMinutes}m`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d`;

  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(timestamp));
}

function playerOptions() {
  return state.trackedAccounts.map((account) => ({
    key: `account:${account.account_id}`,
    label: account.label || account.persona_name || `Account ${account.account_id}`,
    accountId: account.account_id,
    personaName: account.persona_name || null,
    avatarUrl: account.avatar_url || null,
  }));
}

function selectedPlayerOption() {
  return playerOptions().find((option) => option.key === state.selectedPlayerKey) || null;
}

function selectedAccountId() {
  return selectedPlayerOption()?.accountId ?? null;
}

function activeContextEntries(options = {}) {
  const { includePlayer = true } = options;
  const player = selectedPlayerOption();
  return [
    includePlayer && player ? { label: "Player", value: player.label } : null,
    state.selectedHero ? { label: "Hero", value: state.selectedHero } : null,
    state.selectedWindow ? { label: "Window", value: state.selectedWindow } : null,
  ].filter(Boolean);
}

function windowToMatchCount(windowLabel) {
  const option = WINDOW_OPTIONS.find((entry) => entry.label === windowLabel);
  return option ? option.matches : DEFAULT_WINDOW_MATCHES;
}

function formatPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

function formatDecimal(value) {
  return Number(value || 0).toFixed(1);
}

function formatRecord(wins, games) {
  return `${wins}-${Math.max(games - wins, 0)}`;
}

function formatGameCount(value) {
  const games = Number(value || 0);
  return `${games} game${games === 1 ? "" : "s"}`;
}

function formatTimeSeconds(value) {
  const seconds = Number(value || 0);
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60)
    .toString()
    .padStart(2, "0");
  return `${minutes}:${remainder}`;
}

function formatCompactDate(value) {
  const timestamp = Number(value || 0) * 1000;
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(timestamp));
}

function formatItemPhase(value) {
  const seconds = Number(value || 0);
  if (!Number.isFinite(seconds) || seconds < 0) return "unknown";
  if (seconds < 8 * 60) return "early";
  if (seconds < 18 * 60) return "mid";
  return "late";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderInlineMarkup(value) {
  let html = escapeHtml(value);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  return html;
}

function normalizeAssistantText(value) {
  return String(value || "")
    .replace(/\r/g, "")
    .replace(/:\s+-\s+/g, ":\n- ")
    .replace(/([.?!])\s+-\s+(?=[A-Z0-9])/g, "$1\n- ")
    .replace(/\s+-\s+(?=[A-Z][A-Za-z0-9 /'()]{0,40}:)/g, "\n- ")
    .replace(/([.?!])\s+(\d+\.\s+)/g, "$1\n$2")
    .replace(/\n{3,}/g, "\n\n");
}

function renderAssistantText(value) {
  const text = normalizeAssistantText(value).trim();
  if (!text) return "<p>No reply returned.</p>";

  const renderList = (lines, ordered = false) => {
    const tag = ordered ? "ol" : "ul";
    const className = ordered
      ? "assistant-answer__list assistant-answer__list--ordered"
      : "assistant-answer__list";
    const stripped = lines.map((line) =>
      ordered ? line.replace(/^\d+\.\s+/, "") : line.replace(/^[-*]\s+/, ""),
    );
    return `
      <${tag} class="${className}">
        ${stripped.map((line) => `<li>${renderInlineMarkup(line)}</li>`).join("")}
      </${tag}>
    `;
  };

  const renderMixedBlock = (lines) => {
    const segments = [];
    let paragraphBuffer = [];
    let listBuffer = [];
    let listOrdered = false;

    const flushParagraph = () => {
      if (!paragraphBuffer.length) return;
      segments.push(`<p>${paragraphBuffer.map((line) => renderInlineMarkup(line)).join("<br>")}</p>`);
      paragraphBuffer = [];
    };

    const flushList = () => {
      if (!listBuffer.length) return;
      segments.push(renderList(listBuffer, listOrdered));
      listBuffer = [];
    };

    lines.forEach((line) => {
      const isBullet = /^[-*]\s+/.test(line);
      const isNumbered = /^\d+\.\s+/.test(line);
      if (isBullet || isNumbered) {
        if (!listBuffer.length) {
          flushParagraph();
          listOrdered = isNumbered;
        } else if (listOrdered !== isNumbered) {
          flushList();
          listOrdered = isNumbered;
        }
        listBuffer.push(line);
        return;
      }

      flushList();
      paragraphBuffer.push(line);
    });

    flushParagraph();
    flushList();
    return segments.join("");
  };

  const blocks = text.split(/\n\s*\n/).map((block) => block.trim()).filter(Boolean);
  return blocks
    .map((block) => {
      const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
      if (!lines.length) return "";

      if (lines.every((line) => /^[-*]\s+/.test(line))) {
        return renderList(lines);
      }

      if (lines.every((line) => /^\d+\.\s+/.test(line))) {
        return renderList(lines, true);
      }

      if (lines.some((line) => /^[-*]\s+/.test(line) || /^\d+\.\s+/.test(line))) {
        return renderMixedBlock(lines);
      }

      return `<p>${lines.map((line) => renderInlineMarkup(line)).join("<br>")}</p>`;
    })
    .join("");
}

function joinCoachLabels(items) {
  const labels = Array.isArray(items) ? items.map((item) => String(item || "").trim()).filter(Boolean) : [];
  if (!labels.length) return "";
  if (labels.length === 1) return labels[0];
  if (labels.length === 2) return `${labels[0]} and ${labels[1]}`;
  return `${labels.slice(0, -1).join(", ")}, and ${labels[labels.length - 1]}`;
}

function renderCoachAnswerContract(message) {
  const answer = message.coachAnswer;
  if (!answer || typeof answer !== "object") return renderAssistantText(message.text);

  const headline = String(answer.headline || "").trim();
  const supportingPoints = Array.isArray(answer.supporting_points)
    ? answer.supporting_points.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  const nextStep = String(answer.next_step || "").trim();
  const caveat = String(answer.caveat || "").trim();
  const build = answer.build && typeof answer.build === "object" ? answer.build : null;

  if (!build) {
    if (!supportingPoints.length && !nextStep && !caveat) {
      return renderAssistantText(message.text);
    }

    const blocks = [];
    if (headline) {
      blocks.push(`<p>${renderInlineMarkup(headline)}</p>`);
    }
    if (supportingPoints.length) {
      blocks.push(`
        <ul class="assistant-answer__list">
          ${supportingPoints.map((item) => `<li>${renderInlineMarkup(item)}</li>`).join("")}
        </ul>
      `);
    }
    if (nextStep) {
      blocks.push(`<p>${renderInlineMarkup(nextStep)}</p>`);
    }
    if (caveat) {
      blocks.push(`<p>${renderInlineMarkup(caveat)}</p>`);
    }
    return blocks.join("");
  }

  const lines = [];
  if (build.lane_early?.length) {
    lines.push(`Lane/early usually looks like ${joinCoachLabels(build.lane_early)}.`);
  }
  if (build.mid_game?.length) {
    lines.push(`Mid game usually turns into ${joinCoachLabels(build.mid_game)}.`);
  }
  if (build.stable_core?.length) {
    lines.push(`Your stable core is ${joinCoachLabels(build.stable_core)}.`);
  }
  if (Array.isArray(build.late_branches) && build.late_branches.length >= 2) {
    build.late_branches.slice(0, 2).forEach((branch, index) => {
      const lateItems = joinCoachLabels(branch.late_items || []);
      const finishers = joinCoachLabels(branch.t4_finishers || []);
      if (lateItems && finishers) {
        lines.push(`Late branch ${index + 1}: add ${lateItems}, then close with ${finishers} as the T4 finisher.`);
      } else if (lateItems) {
        lines.push(`Late branch ${index + 1}: add ${lateItems}.`);
      } else if (finishers) {
        lines.push(`Late branch ${index + 1}: close with ${finishers} as the T4 finisher.`);
      }
    });
  } else {
    if (build.late_items?.length) {
      lines.push(`Later in the game you usually add ${joinCoachLabels(build.late_items)}.`);
    }
    if (build.t4_finishers?.length) {
      lines.push(`Your main T4 finishers are ${joinCoachLabels(build.t4_finishers)}.`);
    }
  }
  if (build.flex_items?.length) {
    lines.push(`Common flex slots around that are ${joinCoachLabels(build.flex_items)}.`);
  }

  const blocks = [];
  if (headline) {
    blocks.push(`<p>${renderInlineMarkup(headline)}</p>`);
  }
  if (lines.length) {
    blocks.push(`
      <ul class="assistant-answer__list">
        ${lines.map((line) => `<li>${renderInlineMarkup(line)}</li>`).join("")}
      </ul>
    `);
  }
  if (supportingPoints.length) {
    blocks.push(`
      <ul class="assistant-answer__list">
        ${supportingPoints.map((item) => `<li>${renderInlineMarkup(item)}</li>`).join("")}
      </ul>
    `);
  }
  if (nextStep) {
    blocks.push(`<p>${renderInlineMarkup(nextStep)}</p>`);
  }
  if (caveat) {
    blocks.push(`<p>${renderInlineMarkup(caveat)}</p>`);
  }
  return blocks.join("") || renderAssistantText(message.text);
}

function buildRequestContext() {
  const player = selectedPlayerOption();
  return {
    account_id: player?.accountId ?? null,
    player_label: player?.personaName ?? player?.label ?? null,
    hero_name: state.selectedHero || null,
    window_matches: windowToMatchCount(state.selectedWindow),
  };
}

function buildChatHistory() {
  return state.messages
    .filter((message) => !message.loading && String(message.text || "").trim())
    .slice(-8)
    .map((message) => ({
      role: message.role,
      text: message.text,
      insight: message.insight || null,
      confidence: message.confidence || null,
    }));
}

function buildRuntimeSettings() {
  const bootstrap = state.bootstrapSettings;
  if (!bootstrap) return null;

  if (
    state.settingsDraft.provider === bootstrap.provider &&
    state.settingsDraft.model === bootstrap.model &&
    state.settingsDraft.apiKey === bootstrap.apiKey
  ) {
    return null;
  }

  return {
    provider: state.settingsDraft.provider,
    model: state.settingsDraft.model,
    api_key: state.settingsDraft.apiKey || null,
  };
}

function fallbackWarningText(reason) {
  const text = String(reason || "").trim();
  if (!text) return "The live coach did not answer, so this is a local fallback.";
  if (text.includes("invalid `OPENAI_API_KEY`") || text.includes("invalid_api_key")) {
    return "The live coach is offline because the configured OpenAI API key was rejected.";
  }
  if (text.includes("missing Cloud Run auth") || text.includes("identity token")) {
    return "The live coach is offline because the LiteLLM proxy needs a fresh Google Cloud login on this machine.";
  }
  if (text.includes("outbound API connectivity")) {
    return "The live coach is offline because the backend could not reach the model provider.";
  }
  return "The live coach did not answer, so this is a local fallback.";
}

function formatAssistantPayload(payload, originalQuestion) {
  if (payload.source !== "local_fallback") {
    return {
      insight: payload.insight || "",
      text: payload.reply || "No reply returned.",
      bullets: Array.isArray(payload.evidence) ? payload.evidence : [],
      coachAnswer: payload.coach_answer || null,
      confidence: payload.confidence || null,
      evidenceGraph: Array.isArray(payload.evidence_graph) ? payload.evidence_graph : [],
      trace: payload.trace || null,
      structuredOutput: payload.structured_output || null,
      source: payload.source || "",
      warning: "",
    };
  }

  const warning = fallbackWarningText(payload.fallback_reason);
  const isUtilityQuestion = /what day is it|what date is it|what time is it/i.test(String(originalQuestion || ""));
  return {
    insight: isUtilityQuestion ? payload.insight || "Utility reply" : "Local fallback",
    text: payload.reply || warning,
    bullets: isUtilityQuestion ? [] : Array.isArray(payload.evidence) ? payload.evidence : [],
    coachAnswer: payload.coach_answer || null,
    confidence: payload.confidence || null,
    evidenceGraph: Array.isArray(payload.evidence_graph) ? payload.evidence_graph : [],
    trace: payload.trace || null,
    structuredOutput: payload.structured_output || null,
    source: payload.source || "",
    warning: isUtilityQuestion ? "" : warning,
  };
}

async function parseJsonResponse(response) {
  const rawText = await response.text();
  if (!rawText) return {};

  try {
    return JSON.parse(rawText);
  } catch (_error) {
    return {
      error: rawText,
    };
  }
}

function replacePendingAssistantMessage(nextMessage) {
  const pendingIndex = [...state.messages].reverse().findIndex((message) => message.loading);
  if (pendingIndex < 0) {
    state.messages.push(nextMessage);
    return;
  }

  const resolvedIndex = state.messages.length - 1 - pendingIndex;
  state.messages[resolvedIndex] = nextMessage;
}

function completePendingAssistantMessage({
  insight = "",
  text,
  bullets = [],
  coachAnswer = null,
  confidence = null,
  evidenceGraph = [],
  trace = null,
  structuredOutput = null,
  source = "",
  warning = "",
}) {
  replacePendingAssistantMessage({
    role: "assistant",
    loading: false,
    insight,
    text,
    bullets,
    coachAnswer,
    confidence,
    evidenceGraph,
    trace,
    structuredOutput,
    source,
    warning,
    stats: [],
  });
}

function heroSelectOptions() {
  const summaryHeroes = (state.accountSummary?.hero_performance || []).map((item) => item.hero_label);
  return [...new Set([...summaryHeroes, ...baseOptions.heroes])];
}

function apiStatusLabel() {
  return "";
}

function initials(value) {
  return String(value || "?")
    .trim()
    .slice(0, 2)
    .toUpperCase();
}

function reportPlan() {
  const summary = state.accountSummary;
  if (!summary) return null;

  const hero = summary.focus?.top_hero;
  const item = summary.focus?.top_item;
  const keep = hero
    ? `${hero.hero_label} is still your heaviest recent sample at ${hero.games} games. Keep the pool narrow until results stabilize.`
    : "Keep the pool narrow until there is a clear reliable hero in the sample.";
  const resolvedMatches = Number(summary.resolved_outcome_matches || 0);
  const unknownMatches = Number(summary.unknown_outcome_matches || 0);
  const watch =
    resolvedMatches <= 0
      ? `Watch the data quality first: outcomes are still unresolved for ${unknownMatches || summary.total_matches} tracked matches in this sample.`
      : summary.win_rate < 45
        ? `Watch the verified form dip: ${formatPercent(summary.win_rate)} over ${resolvedMatches} resolved matches is a stabilize-first signal.`
        : `Watch whether the verified pace holds: ${formatPercent(summary.win_rate)} over ${resolvedMatches} resolved matches can still swing quickly.`;
  const test = item
    ? `Test one build-phase adjustment around ${item.item_label}. Right now it looks more like a ${formatItemPhase(item.avg_bought_at_s)}-game anchor than part of your opening core.`
    : "Test one build branch instead of changing hero pool and build path at the same time.";

  return { keep, watch, test };
}

async function loadAccountSummary() {
  const accountId = selectedAccountId();
  if (!accountId) {
    state.accountSummary = null;
    state.recentMatches = [];
    state.selectedAccount = null;
    renderApp();
    return;
  }

  state.summaryBusy = true;
  renderApp();

  try {
    const windowMatches = windowToMatchCount(state.selectedWindow);
    const [summaryResponse, recentMatchesResponse] = await Promise.all([
      fetch(`${API_BASE}/api/summary?account_id=${encodeURIComponent(accountId)}&window_matches=${windowMatches}`),
      fetch(
        `${API_BASE}/api/recent-matches?account_id=${encodeURIComponent(accountId)}&window_matches=${Math.min(windowMatches, RECENT_MATCH_PREVIEW_LIMIT)}`,
      ),
    ]);
    if (!summaryResponse.ok || !recentMatchesResponse.ok) {
      throw new Error(`Backend returned ${summaryResponse.ok ? recentMatchesResponse.status : summaryResponse.status}`);
    }

    const [summaryPayload, recentMatchesPayload] = await Promise.all([
      summaryResponse.json(),
      recentMatchesResponse.json(),
    ]);
    state.accountSummary = summaryPayload.account_summary || null;
    state.selectedAccount = summaryPayload.selected_account || null;
    state.recentMatches = Array.isArray(recentMatchesPayload.matches) ? recentMatchesPayload.matches : [];
    state.apiStatus = "online";
  } catch (_error) {
    state.accountSummary = null;
    state.recentMatches = [];
    state.selectedAccount = null;
    state.apiStatus = "offline";
  } finally {
    state.summaryBusy = false;
    renderApp();
  }
}

async function loadBackendStatus() {
  let loadedAccounts = false;
  try {
    const accountsResponse = await fetch(`${API_BASE}/api/accounts`);
    if (!accountsResponse.ok) {
      throw new Error(`Accounts route returned ${accountsResponse.status}`);
    }
    const accountsPayload = await accountsResponse.json();
    state.trackedAccounts = Array.isArray(accountsPayload.accounts) ? accountsPayload.accounts : [];
    if (!state.selectedPlayerKey && state.trackedAccounts.length === 1) {
      state.selectedPlayerKey = `account:${state.trackedAccounts[0].account_id}`;
    }
    loadedAccounts = true;
    state.apiStatus = "online";
  } catch (_error) {
    state.trackedAccounts = [];
    state.apiStatus = "offline";
  }

  try {
    const healthResponse = await fetch(`${API_BASE}/api/health`);
    if (healthResponse.ok) {
      state.apiStatus = "online";
    } else if (!loadedAccounts) {
      state.apiStatus = "offline";
    }
  } catch (_error) {
    if (!loadedAccounts) {
      state.apiStatus = "offline";
    }
  }

  await loadAccountSummary();
}

async function searchAccounts() {
  const query = state.accountSearchQuery.trim();
  if (!query || state.accountSearchBusy) return;

  const requestId = ++accountSearchRequestSequence;
  state.accountSearchBusy = true;
  state.accountSearchStatus = "Searching...";
  paintAccountSearchSurface();

  try {
    const response = await fetch(`${API_BASE}/api/account-search?q=${encodeURIComponent(query)}&limit=6`);
    if (!response.ok) throw new Error(`Backend returned ${response.status}`);

    const payload = await response.json();
    if (requestId !== accountSearchRequestSequence) return;
    state.accountSearchResults = Array.isArray(payload.results) ? payload.results : [];
    state.accountSearchStatus = state.accountSearchResults.length
      ? `Found ${state.accountSearchResults.length} account${state.accountSearchResults.length === 1 ? "" : "s"}`
      : "No matching accounts found.";
    state.apiStatus = "online";
  } catch (_error) {
    if (requestId !== accountSearchRequestSequence) return;
    state.accountSearchResults = [];
    state.accountSearchStatus = "Could not search accounts right now.";
    state.apiStatus = "offline";
  } finally {
    if (requestId === accountSearchRequestSequence) {
      state.accountSearchBusy = false;
      paintAccountSearchSurface();
    }
  }
}

function clearAccountSearchSurface() {
  state.accountSearchBusy = false;
  state.accountSearchStatus = "";
  state.accountSearchResults = [];
  accountSearchRequestSequence += 1;
  if (accountSearchDebounceHandle) {
    window.clearTimeout(accountSearchDebounceHandle);
    accountSearchDebounceHandle = null;
  }
  paintAccountSearchSurface();
}

function scheduleAccountSearch() {
  if (accountSearchDebounceHandle) {
    window.clearTimeout(accountSearchDebounceHandle);
  }

  const query = state.accountSearchQuery.trim();
  if (!query) {
    clearAccountSearchSurface();
    return;
  }

  accountSearchDebounceHandle = window.setTimeout(() => {
    accountSearchDebounceHandle = null;
    searchAccounts();
  }, 180);
}

async function syncAccount(account) {
  if (!account || state.accountSyncBusyId === account.account_id) return;

  const previousPlayerKey = state.selectedPlayerKey;
  const hadConversationState = Boolean(state.chatSessionId) || state.messages.length > 0;
  state.accountSyncBusyId = account.account_id;
  state.accountSearchStatus = `Syncing ${account.persona_name || account.account_id}...`;
  renderApp();

  try {
    const response = await fetch(`${API_BASE}/api/accounts/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        account_id: account.account_id,
        hydrate_matches: 20,
        profile: account,
      }),
    });
    if (!response.ok) throw new Error(`Backend returned ${response.status}`);

    const payload = await response.json();
    state.trackedAccounts = Array.isArray(payload.accounts) ? payload.accounts : state.trackedAccounts;
    state.selectedPlayerKey = `account:${account.account_id}`;
    state.chatSessionId = "";
    state.selectedHero = "";
    state.selectedWindow = "";
    state.accountSummary = payload.summary || state.accountSummary;
    state.accountSearchResults = [];
    state.accountSearchQuery = "";
    state.accountSearchStatus = `Synced ${account.persona_name || account.account_id}`;
    state.accountMenuOpen = false;
    state.apiStatus = "online";
    if (previousPlayerKey !== state.selectedPlayerKey && hadConversationState) {
      createNewConversation();
    }
    await loadAccountSummary();
  } catch (_error) {
    state.accountSearchStatus = "Sync failed. Check the backend and try again.";
    state.apiStatus = "offline";
  } finally {
    state.accountSyncBusyId = null;
    renderApp();
  }
}

async function resetSession() {
  createNewConversation();
  renderApp();
  await loadAccountSummary();
}

async function clearContext() {
  state.selectedHero = "";
  state.selectedWindow = "";
  renderApp();
  await loadAccountSummary();
}

function disconnectAccount() {
  const shouldForkConversation =
    Boolean(state.chatSessionId) ||
    state.messages.length > 0 ||
    Boolean(state.selectedHero) ||
    Boolean(state.selectedWindow);

  state.selectedPlayerKey = "";
  state.accountSummary = null;
  state.recentMatches = [];
  state.selectedAccount = null;
  state.accountMenuOpen = false;
  state.selectedHero = "";
  state.selectedWindow = "";
  state.chatSessionId = "";

  if (shouldForkConversation) {
    createNewConversation();
  } else {
    renderApp();
  }
}

function renderSidebar() {
  const nav = document.getElementById("sidebar-nav");
  const bottom = document.getElementById("sidebar-bottom");
  const historyItems = historyConversations();
  const visibleHistory = visibleConversations();
  const hiddenHistoryCount = Math.max(historyItems.length - visibleHistory.length, 0);
  nav.innerHTML = `
    <div class="sidebar__group sidebar__group--views">
      <div class="sidebar__nav-list">
        ${navItems
          .map(
            (item) => `
              <button class="sidebar__item ${state.screen === item.id ? "is-active" : ""}" data-screen="${item.id}" type="button">
                <span class="sidebar__item-title">${item.title}</span>
                <span class="sidebar__item-meta">${item.meta}</span>
              </button>
            `,
          )
          .join("")}
      </div>
    </div>
    <div class="sidebar__group sidebar__group--history">
      <div class="sidebar__section-head">
        <button class="sidebar__section-toggle" id="toggle-history" type="button" aria-expanded="${state.historyExpanded ? "true" : "false"}" ${
          historyItems.length ? "" : "disabled"
        }>
          <span class="sidebar__label">Chats</span>
          ${historyItems.length ? `<span class="sidebar__chevron ${state.historyExpanded ? "is-open" : ""}">></span>` : ""}
        </button>
      </div>
      ${
        historyItems.length
          ? `
            <div class="chat-history ${state.historyExpanded ? "is-expanded" : "is-collapsed"}">
              ${visibleHistory
                .map(
                  (conversation) => `
                    <div class="chat-history__entry ${conversation.id === state.currentConversationId ? "is-active" : ""}">
                      <button
                        class="chat-history__item ${conversation.id === state.currentConversationId ? "is-active" : ""}"
                        data-conversation-id="${conversation.id}"
                        type="button"
                      >
                        <span class="chat-history__row">
                          <span class="chat-history__title">${escapeHtml(conversation.title || "New chat")}</span>
                          <span class="chat-history__meta">${formatConversationTime(conversation.updatedAt)}</span>
                        </span>
                      </button>
                      <button
                        class="chat-history__remove"
                        data-remove-conversation="${conversation.id}"
                        type="button"
                        aria-label="Remove chat ${escapeHtml(conversation.title || "New chat")}"
                        title="Remove chat"
                      >
                        ${trashIconSvg()}
                      </button>
                    </div>
                  `,
                )
                .join("")}
              ${
                !state.historyExpanded && hiddenHistoryCount > 0
                  ? `<button class="chat-history__older" id="show-older-chats" type="button">${hiddenHistoryCount} older chat${hiddenHistoryCount === 1 ? "" : "s"}</button>`
                  : ""
              }
            </div>
          `
          : `<div class="sidebar__empty-copy">No chats yet in this session.</div>`
      }
    </div>
  `;

  bottom.innerHTML = `
    <div class="sidebar__group sidebar__group--utility">
      <button class="sidebar__utility" id="toggle-settings" type="button" aria-expanded="${state.settingsOpen ? "true" : "false"}">
        <span class="sidebar__utility-label">Settings</span>
        <span class="sidebar__chevron ${state.settingsOpen ? "is-open" : ""}">></span>
      </button>
      ${
        state.settingsOpen
          ? `
            <div class="sidebar__settings-panel">
              <div class="sidebar__settings-head">
                <div class="sidebar__settings-title">Model routing</div>
                <div class="sidebar__settings-copy">Leave this alone unless you want to override the backend default.</div>
              </div>
              <label class="sidebar__field">
                <span>Provider</span>
                <select id="settings-provider">
                  ${Object.entries(providerOptions)
                    .map(
                      ([value, option]) =>
                        `<option value="${value}" ${state.settingsDraft.provider === value ? "selected" : ""}>${option.label}</option>`,
                    )
                    .join("")}
                </select>
              </label>
              <label class="sidebar__field">
                <span>Model</span>
                <select id="settings-model">
                  ${providerOptions[state.settingsDraft.provider].models
                    .map(
                      (model) =>
                        `<option value="${model}" ${state.settingsDraft.model === model ? "selected" : ""}>${model}</option>`,
                    )
                    .join("")}
                </select>
              </label>
              <label class="sidebar__field">
                <span>${providerOptions[state.settingsDraft.provider].apiKeyLabel}</span>
                <input
                  class="sidebar__input"
                  id="settings-api-key"
                  type="password"
                  autocomplete="off"
                  spellcheck="false"
                  placeholder="${providerOptions[state.settingsDraft.provider].apiKeyPlaceholder}"
                  value="${escapeHtml(state.settingsDraft.apiKey)}"
                />
              </label>
              <div class="sidebar__settings-actions">
                <button class="sidebar__settings-save" id="save-settings" type="button">Save</button>
              </div>
              ${state.settingsStatus ? `<div class="sidebar__settings-status">${escapeHtml(state.settingsStatus)}</div>` : ""}
            </div>
          `
          : ""
      }
    </div>
  `;

  document.getElementById("toggle-history")?.addEventListener("click", () => {
    state.historyExpanded = !state.historyExpanded;
    renderApp();
  });

  document.getElementById("show-older-chats")?.addEventListener("click", () => {
    state.historyExpanded = true;
    renderApp();
  });

  document.getElementById("toggle-settings")?.addEventListener("click", () => {
    state.settingsOpen = !state.settingsOpen;
    renderApp();
    if (state.settingsOpen) {
      requestAnimationFrame(() => {
        document.getElementById("toggle-settings")?.scrollIntoView({ block: "start", behavior: "smooth" });
      });
    }
  });

  const providerSelect = document.getElementById("settings-provider");
  const modelSelect = document.getElementById("settings-model");
  const apiKeyInput = document.getElementById("settings-api-key");
  const saveSettingsButton = document.getElementById("save-settings");

  providerSelect?.addEventListener("change", () => {
    const provider = providerOptions[providerSelect.value] ? providerSelect.value : "openai";
    state.settingsDraft.provider = provider;
    state.settingsDraft.model = providerOptions[provider].models[0];
    state.settingsStatus = "";
    renderApp();
  });

  modelSelect?.addEventListener("change", () => {
    state.settingsDraft.model = modelSelect.value;
    state.settingsStatus = "";
  });

  apiKeyInput?.addEventListener("input", () => {
    state.settingsDraft.apiKey = apiKeyInput.value;
    state.settingsStatus = "";
  });

  saveSettingsButton?.addEventListener("click", () => {
    saveStoredSettings();
    state.settingsStatus = "Saved locally";
    renderApp();
  });

  nav.querySelectorAll("[data-screen]").forEach((button) => {
    button.addEventListener("click", () => {
      state.screen = normalizeScreen(button.dataset.screen);
      renderApp();
    });
  });

  nav.querySelectorAll("[data-conversation-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const conversation = state.conversations.find((item) => item.id === button.dataset.conversationId);
      if (!conversation) return;
      applyConversation(conversation);
      renderApp();
      await loadAccountSummary();
    });
  });

  nav.querySelectorAll("[data-remove-conversation]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const removed = removeConversation(button.dataset.removeConversation);
      if (!removed) return;
      renderApp();
      await loadAccountSummary();
    });
  });
}

function renderHeader() {
  state.screen = normalizeScreen(state.screen);
  const copy = screenCopy[state.screen];
  const activeContext = activeContextEntries({ includePlayer: false });
  const isCoach = state.screen === "coach";

  document.getElementById("screen-title").textContent = copy.title;
  document.getElementById("screen-subtitle").textContent = copy.subtitle;
  document.getElementById("workspace-header").classList.toggle("workspace__header--coach", isCoach);
  document.getElementById("workspace-meta").innerHTML = activeContext.length
    ? activeContext.map((item) => `<div class="workspace__tag">${item.label}: ${item.value}</div>`).join("")
    : "";
  renderAccountDock();

  document.getElementById("new-session").onclick = resetSession;
}

function renderAccountDock() {
  const mount = document.getElementById("account-dock");
  const selectedPlayer = selectedPlayerOption();
  const hasTrackedAccounts = state.trackedAccounts.length > 0;

  mount.innerHTML = `
    <div class="account-dock ${state.accountMenuOpen ? "is-open" : ""}">
      <button class="account-dock__trigger" id="account-dock-trigger" type="button">
        ${
          selectedPlayer?.avatarUrl
            ? `<img class="account-dock__avatar" src="${selectedPlayer.avatarUrl}" alt="${selectedPlayer.label}" />`
            : `<div class="account-dock__avatar account-dock__avatar--fallback">${initials(selectedPlayer?.label || "S")}</div>`
        }
        <span class="account-dock__label">${selectedPlayer ? selectedPlayer.label : hasTrackedAccounts ? "Choose player" : "Sign in"}</span>
      </button>
      ${
        state.accountMenuOpen
          ? `
            <div class="account-dock__panel">
              <div class="account-dock__panel-head">
                <div class="sidebar__label">${selectedPlayer ? "Switch Steam player" : hasTrackedAccounts ? "Choose synced player" : "Sign in with Steam"}</div>
                ${selectedPlayer ? '<button class="sidebar__clear" id="disconnect-account" type="button">Remove</button>' : ""}
              </div>
              <div class="account-search-decoys" aria-hidden="true">
                <input tabindex="-1" type="text" autocomplete="username" />
                <input tabindex="-1" type="password" autocomplete="new-password" />
              </div>
              <div class="steam-search-bar steam-search-bar--dock">
                <div class="steam-search-bar__kind">Player</div>
                <input
                  id="account-search-input"
                  type="text"
                  name="deadlock-player-search"
                  placeholder="Steam name, id or profile URL..."
                  autocomplete="off"
                  autocapitalize="none"
                  autocorrect="off"
                  spellcheck="false"
                  data-form-type="other"
                  aria-autocomplete="list"
                  aria-controls="account-results"
                />
              </div>
              <div class="account-search__status" id="account-search-status"></div>
              <div class="account-results account-results--dock" id="account-results"></div>
            </div>
          `
          : ""
      }
    </div>
  `;

  document.getElementById("account-dock-trigger").onclick = () => {
    state.accountMenuOpen = !state.accountMenuOpen;
    renderHeader();
  };

  if (!state.accountMenuOpen) return;

  const accountSearchInput = document.getElementById("account-search-input");
  paintAccountSearchSurface();

  accountSearchInput.oninput = (event) => {
    state.accountSearchQuery = event.target.value;
    scheduleAccountSearch();
  };

  accountSearchInput.onkeydown = (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      searchAccounts();
    }
  };

  accountSearchInput.focus();

  document.getElementById("disconnect-account")?.addEventListener("click", () => {
    disconnectAccount();
  });
}

async function selectTrackedAccount(account) {
  if (!account) return;

  const previousPlayerKey = state.selectedPlayerKey;
  const hadConversationState = Boolean(state.chatSessionId) || state.messages.length > 0;
  state.selectedPlayerKey = `account:${account.account_id}`;
  state.chatSessionId = "";
  state.selectedHero = "";
  state.selectedWindow = "";
  state.accountMenuOpen = false;
  state.accountSearchQuery = "";
  clearAccountSearchSurface();

  if (previousPlayerKey !== state.selectedPlayerKey && hadConversationState) {
    createNewConversation();
  } else {
    renderApp();
  }
  await loadAccountSummary();
}

function paintAccountSearchSurface() {
  const accountSearchInput = document.getElementById("account-search-input");
  const accountSearchStatus = document.getElementById("account-search-status");
  const accountResults = document.getElementById("account-results");

  if (!accountSearchInput || !accountSearchStatus || !accountResults) return;

  if (accountSearchInput.value !== state.accountSearchQuery) {
    accountSearchInput.value = state.accountSearchQuery;
  }
  const showingTrackedAccounts = !state.accountSearchQuery.trim();
  const visibleAccounts = showingTrackedAccounts ? state.trackedAccounts : state.accountSearchResults;
  if (state.accountSearchStatus) {
    accountSearchStatus.textContent = state.accountSearchStatus;
  } else if (showingTrackedAccounts && visibleAccounts.length) {
    accountSearchStatus.textContent = "Pick a synced player or search another Steam account.";
  } else if (showingTrackedAccounts) {
    accountSearchStatus.textContent = "Search Steam to sync a player.";
  } else {
    accountSearchStatus.textContent = "";
  }

  accountResults.innerHTML = visibleAccounts
    .map(
      (account) => `
        <div class="account-result account-result--rich">
          <div class="account-result__identity">
            ${
              account.avatar_url
                ? `<img class="account-result__avatar" src="${account.avatar_url}" alt="${account.persona_name || account.account_id}" />`
                : `<div class="account-result__avatar account-result__avatar--fallback">${initials(account.persona_name || account.account_id)}</div>`
            }
            <div class="account-result__copy">
              <div class="account-result__title">${account.persona_name || `Account ${account.account_id}`}</div>
              <div class="account-result__meta">
                ${[
                  account.country_code || null,
                  account.matches != null ? `${account.matches} tracked` : null,
                  account.matches_played_last_30d != null ? `${account.matches_played_last_30d} matches / 30d` : null,
                  estimatedRankLabel(account),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
            </div>
          </div>
          <button class="account-result__action" ${
            showingTrackedAccounts ? `data-select-account="${account.account_id}"` : `data-sync-account="${account.account_id}"`
          } type="button" ${
            showingTrackedAccounts
              ? selectedAccountId() === account.account_id
                ? "disabled"
                : ""
              : state.accountSyncBusyId === account.account_id
                ? "disabled"
                : ""
          }>
            ${
              showingTrackedAccounts
                ? selectedAccountId() === account.account_id
                  ? "Active"
                  : "Use"
                : state.accountSyncBusyId === account.account_id
                  ? "Syncing"
                  : "Sync"
            }
          </button>
        </div>
      `,
    )
    .join("");

  accountResults.querySelectorAll("[data-sync-account]").forEach((button) => {
    button.addEventListener("click", () => {
      const account = state.accountSearchResults.find((item) => item.account_id === Number(button.dataset.syncAccount));
      syncAccount(account);
    });
  });

  accountResults.querySelectorAll("[data-select-account]").forEach((button) => {
    button.addEventListener("click", () => {
      const account = state.trackedAccounts.find((item) => item.account_id === Number(button.dataset.selectAccount));
      selectTrackedAccount(account);
    });
  });
}

function renderContextRail() {
  const optionalContext = activeContextEntries({ includePlayer: false });
  return `
    <aside class="context-rail">
      <div class="context-rail__head">
        <div class="sidebar__label">Add Context</div>
        <button class="sidebar__clear" id="clear-context" type="button">Reset</button>
      </div>
      ${
        optionalContext.length
          ? `
            <div class="context-summary" id="context-summary">
              ${optionalContext.map((item) => `<div class="context-chip">${item.label}: ${item.value}</div>`).join("")}
            </div>
          `
          : ""
      }
      <label class="sidebar__field">
        <span>Hero</span>
        <select id="hero-select"></select>
      </label>
      <label class="sidebar__field">
        <span>Window</span>
        <select id="window-select"></select>
      </label>
    </aside>
  `;
}

function wireContextRail() {
  const heroSelect = document.getElementById("hero-select");
  const windowSelect = document.getElementById("window-select");
  if (!heroSelect || !windowSelect) return;

  heroSelect.innerHTML = ['<option value="">Not set</option>']
    .concat(heroSelectOptions().map((hero) => `<option value="${hero}" ${state.selectedHero === hero ? "selected" : ""}>${hero}</option>`))
    .join("");

  windowSelect.innerHTML = [`<option value="">Auto (${DEFAULT_WINDOW_MATCHES} recent matches)</option>`]
    .concat(
      baseOptions.windows.map(
        (windowName) => `<option value="${windowName}" ${state.selectedWindow === windowName ? "selected" : ""}>${windowName}</option>`,
      ),
    )
    .join("");

  heroSelect.onchange = () => {
    state.selectedHero = heroSelect.value;
    renderApp();
  };

  windowSelect.onchange = async () => {
    state.selectedWindow = windowSelect.value;
    renderApp();
    await loadAccountSummary();
  };

  document.getElementById("clear-context").onclick = () => {
    clearContext();
  };
}

function renderWelcome() {
  const player = selectedPlayerOption();
  const hasTrackedAccounts = state.trackedAccounts.length > 0;
  return `
    <div class="welcome">
      <h1 class="welcome__title">How can I help in Deadbase?</h1>
      <div class="welcome__subtitle">${
        player
          ? `${player.label} is synced. Ask about heroes, win rates, builds, patches, matchups, or what to practice next.`
          : hasTrackedAccounts
            ? "Choose a synced player above for grounded coaching, or ask a theory question about a hero, item, or matchup."
            : "Ask about heroes, win rates, builds, patches, matchups, or what to practice next."
      }</div>
    </div>
  `;
}

function evidenceItemsForMessage(message) {
  const graphItems = Array.isArray(message.evidenceGraph) ? message.evidenceGraph.filter((item) => item?.detail) : [];
  if (graphItems.length) {
    return graphItems.map((item) => ({
      label: String(item.source_type || "").replaceAll("_", " "),
      detail: String(item.detail || ""),
    }));
  }

  const bullets = Array.isArray(message.bullets) ? message.bullets.filter(Boolean) : [];
  return bullets.map((detail) => ({ label: "", detail: String(detail) }));
}

function evidenceToggleKey(index) {
  return `${state.currentConversationId || "conversation"}:${index}`;
}

function renderEvidencePanel(message, key) {
  const items = evidenceItemsForMessage(message);
  if (!items.length || !state.expandedEvidence[key]) return "";

  return `
    <div class="assistant-evidence-panel">
      ${items
        .map(
          (item) => `
            <div class="assistant-evidence-panel__item">
              ${item.label ? `<div class="assistant-evidence-panel__label">${escapeHtml(item.label)}</div>` : ""}
              <div class="assistant-evidence-panel__detail">${renderInlineMarkup(item.detail)}</div>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function shouldShowLimitedSampleChip(message) {
  if (message.confidence?.level !== "low") return false;

  const graphItems = Array.isArray(message.evidenceGraph) ? message.evidenceGraph : [];
  if (graphItems.some((item) => item?.source_type === "player_telemetry")) return true;

  const scope = message.structuredOutput?.routing?.information_need?.scope;
  return scope === "player_specific";
}

function renderAssistantContracts(message, key) {
  const chips = [];
  if (shouldShowLimitedSampleChip(message)) {
    chips.push('<div class="assistant-contracts__chip assistant-contracts__chip--confidence">Limited sample</div>');
  }

  const evidenceItems = evidenceItemsForMessage(message);
  if (evidenceItems.length) {
    chips.push(
      `<button class="assistant-contracts__chip assistant-contracts__chip--toggle" data-evidence-toggle="${escapeHtml(key)}" type="button" aria-expanded="${state.expandedEvidence[key] ? "true" : "false"}">${evidenceItems.length} evidence anchor${evidenceItems.length === 1 ? "" : "s"}</button>`,
    );
  }

  if (!chips.length) return "";
  return `<div class="assistant-contracts">${chips.join("")}</div>`;
}

function renderMessages() {
  return state.messages
    .map((message, index) => {
      const evidenceKey = evidenceToggleKey(index);
      if (message.role === "user") {
        return `
          <div class="message message--user">
            <div class="message__meta">You</div>
            <div class="message__bubble message__bubble--user">${escapeHtml(message.text).replace(/\n/g, "<br>")}</div>
          </div>
        `;
      }

      return `
        <div class="message message--assistant">
          <div class="message__meta">${message.loading ? "Coach is thinking" : "Coach"}</div>
          <div class="assistant-answer">
            ${!message.loading ? renderAssistantContracts(message, evidenceKey) : ""}
            ${!message.loading ? renderEvidencePanel(message, evidenceKey) : ""}
            ${message.warning && !message.loading ? `<div class="assistant-answer__warning">${escapeHtml(message.warning)}</div>` : ""}
            <div class="assistant-answer__text">${renderCoachAnswerContract(message)}</div>
          </div>
        </div>
      `;
    })
    .join("");
}

function composerHintLabel() {
  if (state.requestInFlight) return "Coach is thinking...";
  return apiStatusLabel();
}

function renderCoachScreen() {
  const composerHint = composerHintLabel();
  return `
    <section class="coach-screen coach-screen--workspace">
      <div class="coach-shell">
        <div class="thread-wrap">
          <div class="thread ${state.messages.length === 0 ? "thread--empty" : ""}">
            ${state.messages.length === 0 ? renderWelcome() : renderMessages()}
          </div>
        </div>
      </div>

      <div class="composer">
        <div class="composer__inner">
          <div class="composer__box">
            <textarea class="composer__input" id="composer-input" rows="1" placeholder="Ask what to queue, what to fix, which build path is strongest, or what to test next.">${state.draft}</textarea>
            <div class="composer__actions">
              ${composerHint ? `<div class="composer__hint">${composerHint}</div>` : ""}
              <button class="composer__submit ${state.requestInFlight ? "composer__submit--stop" : ""}" id="composer-submit" type="button">
                ${state.requestInFlight ? "Stop" : "Send"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  `;
}

function renderMain() {
  state.screen = normalizeScreen(state.screen);
  const host = document.getElementById("screen-host");
  host.innerHTML = renderCoachScreen();
  wireCoachEvents();
}

async function submitQuery(query) {
  const text = query.trim();
  if (!text || state.requestInFlight) return;
  let backendReachable = false;
  const requestId = ++state.requestSequence;
  const controller = new AbortController();
  const timeoutHandle = window.setTimeout(() => {
    controller.abort("timeout");
  }, 45000);

  state.screen = "coach";
  state.requestInFlight = true;
  state.requestAbortController = controller;
  state.messages.push({ role: "user", text });
  state.messages.push({
    role: "assistant",
    loading: true,
    insight: "Preparing answer",
    text: "Thinking…",
    bullets: [],
    stats: [],
  });
  state.draft = "";
  threadShouldPinToBottom = true;
  renderApp();

  try {
    const response = await fetch(`${API_BASE}/api/adk/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        message: text,
        context: buildRequestContext(),
        session_id: state.chatSessionId || null,
        history: buildChatHistory(),
        runtime_settings: buildRuntimeSettings(),
      }),
    });

    const payload = await parseJsonResponse(response);
    backendReachable = true;
    if (!response.ok) {
      throw new Error(payload.error || `Backend returned ${response.status}`);
    }
    if (requestId !== state.requestSequence) return;

    state.chatSessionId = payload.session_id || state.chatSessionId;
    state.accountSummary = payload.summary || state.accountSummary;
    const assistantPayload = formatAssistantPayload(payload, text);
    completePendingAssistantMessage({
      insight: assistantPayload.insight,
      text: assistantPayload.text,
      bullets: assistantPayload.bullets,
      coachAnswer: assistantPayload.coachAnswer,
      confidence: assistantPayload.confidence,
      evidenceGraph: assistantPayload.evidenceGraph,
      trace: assistantPayload.trace,
      structuredOutput: assistantPayload.structuredOutput,
      source: assistantPayload.source,
      warning: assistantPayload.warning,
    });
    state.apiStatus = "online";
  } catch (error) {
    if (requestId !== state.requestSequence) return;

    const aborted = controller.signal.aborted || error?.name === "AbortError";
    if (aborted) {
      const timedOut = controller.signal.reason === "timeout";
      completePendingAssistantMessage({
        insight: timedOut ? "Timed out" : "Stopped",
        text: timedOut
          ? "The coach took too long to finish that reply. Try again, or ask the question in a narrower way."
          : "Stopped before the coach finished the reply.",
        bullets: timedOut ? ["Try a shorter prompt or retry now that the session is warm."] : [],
      });
      state.apiStatus = backendReachable ? "online" : state.apiStatus;
    } else {
      completePendingAssistantMessage({
        text:
          error?.message ||
          "I could not reach the local Deadbase backend. Start it on port 3000, then try again.",
        bullets: [
          "Start the backend with `.venv/bin/python -m deadlock_coach serve --host 127.0.0.1 --port 3000`.",
          "Set `OPENAI_API_KEY` for OpenAI, or `GOOGLE_API_KEY` / `GEMINI_API_KEY` for Gemini, before launching the backend.",
        ],
      });
      state.apiStatus = backendReachable ? "online" : "offline";
    }
  } finally {
    window.clearTimeout(timeoutHandle);
    if (requestId === state.requestSequence) {
      state.requestAbortController = null;
      state.requestInFlight = false;
    }
    threadShouldPinToBottom = true;
    renderApp();
  }
}

function cancelActiveRequest(reason = "stopped") {
  if (!state.requestInFlight || !state.requestAbortController) return;
  state.requestAbortController.abort(reason);
}

function wireCoachEvents() {
  document.querySelectorAll("[data-free-ask]").forEach((button) => {
    button.addEventListener("click", () => {
      submitQuery(button.dataset.freeAsk);
    });
  });

  const input = document.getElementById("composer-input");
  const submit = document.getElementById("composer-submit");

  if (!input || !submit) return;

  submit.onclick = () => {
    if (state.requestInFlight) {
      cancelActiveRequest("stopped");
      return;
    }
    submitQuery(input.value);
  };

  input.oninput = () => {
    state.draft = input.value;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
  };

  input.onkeydown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (state.requestInFlight) return;
      submitQuery(input.value);
    }
  };

  input.focus();

  document.querySelectorAll("[data-evidence-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.getAttribute("data-evidence-toggle");
      if (!key) return;
      state.expandedEvidence[key] = !state.expandedEvidence[key];
      renderApp();
    });
  });
}

function captureCoachViewport() {
  if (state.screen !== "coach") return null;

  const wrap = document.querySelector(".thread-wrap");
  if (!wrap) return null;

  const maxScrollTop = Math.max(wrap.scrollHeight - wrap.clientHeight, 0);
  const scrollTop = Math.min(wrap.scrollTop, maxScrollTop);
  return {
    scrollTop,
    distanceFromBottom: maxScrollTop - scrollTop,
  };
}

function renderApp() {
  const previousViewport = captureCoachViewport();
  syncCurrentConversation();
  renderSidebar();
  renderHeader();
  renderMain();
  syncCoachViewport(previousViewport);
}

function syncCoachViewport(previousViewport = null) {
  const input = document.getElementById("composer-input");
  if (input) {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
  }

  if (state.screen !== "coach") return;
  const wrap = document.querySelector(".thread-wrap");
  if (!wrap) return;

  const restoreViewport = () => {
    const maxScrollTop = Math.max(wrap.scrollHeight - wrap.clientHeight, 0);
    if (threadShouldPinToBottom) {
      wrap.scrollTop = maxScrollTop;
      return;
    }

    if (!previousViewport) return;
    if (previousViewport.distanceFromBottom <= 4) {
      wrap.scrollTop = maxScrollTop;
      return;
    }
    wrap.scrollTop = Math.min(previousViewport.scrollTop, maxScrollTop);
  };

  restoreViewport();
  requestAnimationFrame(() => {
    restoreViewport();
    if (threadShouldPinToBottom) {
      threadShouldPinToBottom = false;
    }
  });
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) return;

  let shouldRender = false;
  if (state.settingsOpen && !target.closest(".sidebar__group--utility")) {
    state.settingsOpen = false;
    shouldRender = true;
  }

  if (state.accountMenuOpen && !target.closest(".account-dock")) {
    state.accountMenuOpen = false;
    shouldRender = true;
  }

  if (shouldRender) {
    renderApp();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;

  if (state.requestInFlight) {
    cancelActiveRequest("stopped");
    return;
  }

  if (!state.settingsOpen && !state.accountMenuOpen) return;
  state.settingsOpen = false;
  state.accountMenuOpen = false;
  renderApp();
});

initializeSettings();
initializeConversations();
renderApp();
hydrateSettingsFromBackend();
loadBackendStatus();
