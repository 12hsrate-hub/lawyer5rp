const errorsHost = document.getElementById("admin-errors");
const messageHost = document.getElementById("admin-message");
const totalsHost = document.getElementById("admin-totals");
const examImportHost = document.getElementById("admin-exam-import");
const performanceHost = document.getElementById("admin-performance");
const usersHost = document.getElementById("admin-users");
const eventsHost = document.getElementById("admin-events");
const adminEventsHost = document.getElementById("admin-admin-events");
const endpointsHost = document.getElementById("admin-top-endpoints");
const activeFiltersHost = document.getElementById("admin-active-filters");
const userSearchField = document.getElementById("admin-user-search");
const userSortField = document.getElementById("admin-user-sort");
const blockedOnlyField = document.getElementById("admin-filter-blocked");
const testerOnlyField = document.getElementById("admin-filter-tester");
const gkaOnlyField = document.getElementById("admin-filter-gka");
const unverifiedOnlyField = document.getElementById("admin-filter-unverified");
const resetFiltersButton = document.getElementById("admin-reset-filters");
const exportUsersButton = document.getElementById("admin-export-users");
const eventSearchField = document.getElementById("admin-event-search");
const eventTypeField = document.getElementById("admin-event-type");
const failedEventsOnlyField = document.getElementById("admin-filter-failed-events");
const exportEventsButton = document.getElementById("admin-export-events");
const liveRefreshField = document.getElementById("admin-live-refresh");
const liveIntervalField = document.getElementById("admin-live-interval");
const liveStatusHost = document.getElementById("admin-live-status");
const refreshNowButton = document.getElementById("admin-refresh-now");
const userModalBody = document.getElementById("admin-user-modal-body");

const { apiFetch, parsePayload, showText, clearText, escapeHtml, createModalController } = window.OGPWeb;
const ADMIN_COLLAPSE_STORAGE_KEY = "ogp_admin_collapsible_sections";

let adminSearchTimer = null;
let adminLiveTimer = null;
let selectedUser = null;
const userIndex = new Map();

const userModal = createModalController({
  modal: document.getElementById("admin-user-modal"),
});

function loadCollapsibleState() {
  try {
    return JSON.parse(window.localStorage.getItem(ADMIN_COLLAPSE_STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveCollapsibleState(state) {
  try {
    window.localStorage.setItem(ADMIN_COLLAPSE_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Ignore storage failures.
  }
}

function setCollapsibleExpanded(button, expanded, state = null) {
  const targetId = button?.getAttribute("data-collapsible-target") || "";
  const content = targetId ? document.getElementById(targetId) : null;
  const section = button?.closest("[data-collapsible-section]");
  const sectionKey = section?.getAttribute("data-collapsible-section") || targetId;

  if (!button || !content || !sectionKey) {
    return;
  }

  button.setAttribute("aria-expanded", expanded ? "true" : "false");
  button.textContent = expanded ? "РЎРєСЂС‹С‚СЊ" : "РџРѕРєР°Р·Р°С‚СЊ";
  content.hidden = !expanded;
  section.dataset.collapsibleOpen = expanded ? "true" : "false";

  const nextState = state || loadCollapsibleState();
  nextState[sectionKey] = expanded;
  saveCollapsibleState(nextState);
}

function initCollapsibles() {
  const savedState = loadCollapsibleState();
  const buttons = Array.from(document.querySelectorAll("[data-collapsible-target]"));

  buttons.forEach((button) => {
    const targetId = button.getAttribute("data-collapsible-target") || "";
    const content = targetId ? document.getElementById(targetId) : null;
    const section = button.closest("[data-collapsible-section]");
    const sectionKey = section?.getAttribute("data-collapsible-section") || targetId;
    if (!content || !sectionKey) {
      return;
    }

    const defaultExpanded = button.getAttribute("data-expanded-default") !== "false";
    const expanded = Object.prototype.hasOwnProperty.call(savedState, sectionKey)
      ? Boolean(savedState[sectionKey])
      : defaultExpanded;

    setCollapsibleExpanded(button, expanded, savedState);

    button.addEventListener("click", () => {
      const isExpanded = button.getAttribute("aria-expanded") === "true";
      setCollapsibleExpanded(button, !isExpanded);
    });
  });
}

function describeApiPath(path) {
  const normalized = String(path || "").trim();
  if (!normalized) {
    return "РЎРёСЃС‚РµРјРЅС‹Р№ Р·Р°РїСЂРѕСЃ Р±РµР· СѓРєР°Р·Р°РЅРЅРѕРіРѕ РїСѓС‚Рё.";
  }

  const patterns = [
    [/^\/api\/admin\/overview$/, "Р—Р°РіСЂСѓР·РєР° РІСЃРµР№ Р°РґРјРёРЅ-РїР°РЅРµР»Рё: СЃРІРѕРґРєР°, РїРѕР»СЊР·РѕРІР°С‚РµР»Рё, СЃРѕР±С‹С‚РёСЏ Рё СЃС‚Р°С‚РёСЃС‚РёРєР°."],
    [/^\/api\/admin\/users\.csv$/, "Р’С‹РіСЂСѓР·РєР° CSV СЃРѕ СЃРїРёСЃРєРѕРј РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№ РїРѕ С‚РµРєСѓС‰РёРј С„РёР»СЊС‚СЂР°Рј."],
    [/^\/api\/admin\/events\.csv$/, "Р’С‹РіСЂСѓР·РєР° CSV СЃРѕ СЃРїРёСЃРєРѕРј СЃРѕР±С‹С‚РёР№ РїРѕ С‚РµРєСѓС‰РёРј С„РёР»СЊС‚СЂР°Рј."],
    [/^\/api\/admin\/users\/[^/]+\/verify-email$/, "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ РІСЂСѓС‡РЅСѓСЋ РїРѕРґС‚РІРµСЂР¶РґР°РµС‚ email РІС‹Р±СЂР°РЅРЅРѕРіРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ."],
    [/^\/api\/admin\/users\/[^/]+\/block$/, "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ Р±Р»РѕРєРёСЂСѓРµС‚ РґРѕСЃС‚СѓРї РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ Рє Р°РєРєР°СѓРЅС‚Сѓ."],
    [/^\/api\/admin\/users\/[^/]+\/unblock$/, "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ СЃРЅРёРјР°РµС‚ Р±Р»РѕРєРёСЂРѕРІРєСѓ Рё РІРѕР·РІСЂР°С‰Р°РµС‚ РґРѕСЃС‚СѓРї Рє Р°РєРєР°СѓРЅС‚Сѓ."],
    [/^\/api\/admin\/users\/[^/]+\/grant-tester$/, "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ РІС‹РґР°РµС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ СЃС‚Р°С‚СѓСЃ С‚РµСЃС‚РµСЂР°."],
    [/^\/api\/admin\/users\/[^/]+\/revoke-tester$/, "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ СЃРЅРёРјР°РµС‚ Сѓ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ СЃС‚Р°С‚СѓСЃ С‚РµСЃС‚РµСЂР°."],
    [/^\/api\/admin\/users\/[^/]+\/grant-gka$/, "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ РїСЂРёСЃРІР°РёРІР°РµС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ С‚РёРї Р“РљРђ-Р—Р“РљРђ."],
    [/^\/api\/admin\/users\/[^/]+\/revoke-gka$/, "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ СЃРЅРёРјР°РµС‚ Сѓ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ С‚РёРї Р“РљРђ-Р—Р“РљРђ."],
    [/^\/api\/admin\/users\/[^/]+\/email$/, "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ РІСЂСѓС‡РЅСѓСЋ РјРµРЅСЏРµС‚ email РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ."],
    [/^\/api\/admin\/users\/[^/]+\/reset-password$/, "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ РІСЂСѓС‡РЅСѓСЋ Р·Р°РґР°РµС‚ РЅРѕРІС‹Р№ РїР°СЂРѕР»СЊ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ."],
    [/^\/api\/complaint-draft$/, "РЎРѕС…СЂР°РЅРµРЅРёРµ, Р·Р°РіСЂСѓР·РєР° РёР»Рё РѕС‡РёСЃС‚РєР° С‡РµСЂРЅРѕРІРёРєР° Р¶Р°Р»РѕР±С‹ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ."],
    [/^\/api\/generate$/, "Р“РµРЅРµСЂР°С†РёСЏ РёС‚РѕРіРѕРІРѕР№ Р¶Р°Р»РѕР±С‹ РїРѕ Р·Р°РїРѕР»РЅРµРЅРЅРѕР№ С„РѕСЂРјРµ."],
    [/^\/api\/generate-rehab$/, "Р“РµРЅРµСЂР°С†РёСЏ Р·Р°СЏРІР»РµРЅРёСЏ РЅР° СЂРµР°Р±РёР»РёС‚Р°С†РёСЋ."],
    [/^\/api\/ai\/suggest$/, "AI СѓР»СѓС‡С€Р°РµС‚ Рё РїРµСЂРµРїРёСЃС‹РІР°РµС‚ РѕРїРёСЃР°РЅРёРµ Р¶Р°Р»РѕР±С‹."],
    [/^\/api\/ai\/extract-principal$/, "AI СЂР°СЃРїРѕР·РЅР°РµС‚ РґР°РЅРЅС‹Рµ РґРѕРІРµСЂРёС‚РµР»СЏ СЃ РёР·РѕР±СЂР°Р¶РµРЅРёСЏ РґРѕРєСѓРјРµРЅС‚Р°."],
    [/^\/api\/auth\/login$/, "Р’С…РѕРґ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РІ Р°РєРєР°СѓРЅС‚."],
    [/^\/api\/auth\/register$/, "Р РµРіРёСЃС‚СЂР°С†РёСЏ РЅРѕРІРѕРіРѕ Р°РєРєР°СѓРЅС‚Р°."],
    [/^\/api\/auth\/logout$/, "Р’С‹С…РѕРґ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РёР· Р°РєРєР°СѓРЅС‚Р°."],
    [/^\/api\/auth\/forgot-password$/, "Р—Р°РїСѓСЃРє РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёСЏ РїР°СЂРѕР»СЏ."],
    [/^\/api\/auth\/reset-password$/, "РЎР±СЂРѕСЃ РїР°СЂРѕР»СЏ РїРѕ С‚РѕРєРµРЅСѓ РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёСЏ."],
    [/^\/api\/profile$/, "Р—Р°РіСЂСѓР·РєР° РёР»Рё СЃРѕС…СЂР°РЅРµРЅРёРµ РґР°РЅРЅС‹С… РїСЂРѕС„РёР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ."],
    [/^\/api\/exam-import\/sync$/, "РРјРїРѕСЂС‚ РЅРѕРІС‹С… РѕС‚РІРµС‚РѕРІ РЅР° СЌРєР·Р°РјРµРЅС‹ РёР· Google Sheets."],
    [/^\/api\/exam-import\/score$/, "РњР°СЃСЃРѕРІР°СЏ РїСЂРѕРІРµСЂРєР° РёРјРїРѕСЂС‚РёСЂРѕРІР°РЅРЅС‹С… СЌРєР·Р°РјРµРЅР°С†РёРѕРЅРЅС‹С… РѕС‚РІРµС‚РѕРІ."],
    [/^\/api\/exam-import\/rows\/\d+$/, "РџСЂРѕСЃРјРѕС‚СЂ РґРµС‚Р°Р»РµР№ РїРѕ РѕРґРЅРѕР№ РёРјРїРѕСЂС‚РёСЂРѕРІР°РЅРЅРѕР№ СЃС‚СЂРѕРєРµ СЌРєР·Р°РјРµРЅР°."],
    [/^\/api\/exam-import\/rows\/\d+\/score$/, "РџСЂРѕРІРµСЂРєР° Рё РѕС†РµРЅРєР° РѕРґРЅРѕР№ РєРѕРЅРєСЂРµС‚РЅРѕР№ СЃС‚СЂРѕРєРё СЌРєР·Р°РјРµРЅР°."],
  ];

  for (const [pattern, description] of patterns) {
    if (pattern.test(normalized)) {
      return description;
    }
  }

  return "РўРµС…РЅРёС‡РµСЃРєРёР№ API-Р·Р°РїСЂРѕСЃ. Р”Р»СЏ СЌС‚РѕРіРѕ РїСѓС‚Рё РµС‰Рµ РЅРµ РґРѕР±Р°РІР»РµРЅРѕ С‡РµР»РѕРІРµРєРѕС‡РёС‚Р°РµРјРѕРµ РѕРїРёСЃР°РЅРёРµ.";
}

function describeEventType(eventType) {
  const normalized = String(eventType || "").trim().toLowerCase();
  const descriptions = {
    api_request: "РћР±С‹С‡РЅС‹Р№ Р·Р°РїСЂРѕСЃ Рє API РїСЂРёР»РѕР¶РµРЅРёСЏ.",
    complaint_generated: "РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ СЃРіРµРЅРµСЂРёСЂРѕРІР°Р» Р¶Р°Р»РѕР±Сѓ.",
    rehab_generated: "РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ СЃРіРµРЅРµСЂРёСЂРѕРІР°Р» Р·Р°СЏРІР»РµРЅРёРµ РЅР° СЂРµР°Р±РёР»РёС‚Р°С†РёСЋ.",
    complaint_draft_saved: "РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ СЃРѕС…СЂР°РЅРёР» С‡РµСЂРЅРѕРІРёРє Р¶Р°Р»РѕР±С‹.",
    complaint_draft_cleared: "РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РѕС‡РёСЃС‚РёР» С‡РµСЂРЅРѕРІРёРє Р¶Р°Р»РѕР±С‹.",
    ai_suggest: "AI РѕР±СЂР°Р±РѕС‚Р°Р» Рё СѓР»СѓС‡С€РёР» С‚РµРєСЃС‚ Р¶Р°Р»РѕР±С‹.",
    ai_extract_principal: "AI СЂР°СЃРїРѕР·РЅР°Р» РґР°РЅРЅС‹Рµ СЃ РґРѕРєСѓРјРµРЅС‚Р°.",
    ai_exam_scoring: "AI РїСЂРѕРІРµСЂРёР» СЌРєР·Р°РјРµРЅР°С†РёРѕРЅРЅС‹Рµ РѕС‚РІРµС‚С‹ Рё РІРµСЂРЅСѓР» СЃС‚Р°С‚РёСЃС‚РёРєСѓ РїРѕ cache, СЌРІСЂРёСЃС‚РёРєР°Рј Рё LLM.",
    exam_import_sync_error: "РРјРїРѕСЂС‚ РёР· Google Sheets Р·Р°РІРµСЂС€РёР»СЃСЏ РѕС€РёР±РєРѕР№.",
    exam_import_score_failures: "Р’Рѕ РІСЂРµРјСЏ РјР°СЃСЃРѕРІРѕР№ РїСЂРѕРІРµСЂРєРё СЌРєР·Р°РјРµРЅРѕРІ С‡Р°СЃС‚СЊ СЃС‚СЂРѕРє РЅРµ РѕР±СЂР°Р±РѕС‚Р°Р»Р°СЃСЊ.",
    exam_import_row_score_error: "РџСЂРѕРІРµСЂРєР° РѕРґРЅРѕР№ СЃС‚СЂРѕРєРё СЌРєР·Р°РјРµРЅР° Р·Р°РІРµСЂС€РёР»Р°СЃСЊ РѕС€РёР±РєРѕР№.",
    admin_verify_email: "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ РїРѕРґС‚РІРµСЂРґРёР» email РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ.",
    admin_block_user: "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ Р·Р°Р±Р»РѕРєРёСЂРѕРІР°Р» РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ.",
    admin_unblock_user: "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ СЂР°Р·Р±Р»РѕРєРёСЂРѕРІР°Р» РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ.",
    admin_grant_tester: "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ РІС‹РґР°Р» СЃС‚Р°С‚СѓСЃ С‚РµСЃС‚РµСЂР°.",
    admin_revoke_tester: "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ СЃРЅСЏР» СЃС‚Р°С‚СѓСЃ С‚РµСЃС‚РµСЂР°.",
    admin_grant_gka: "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ РїСЂРёСЃРІРѕРёР» С‚РёРї Р“РљРђ-Р—Р“РљРђ.",
    admin_revoke_gka: "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ СЃРЅСЏР» С‚РёРї Р“РљРђ-Р—Р“РљРђ.",
    admin_update_email: "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ РёР·РјРµРЅРёР» email РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ.",
    admin_reset_password: "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ Р·Р°РґР°Р» РЅРѕРІС‹Р№ РїР°СЂРѕР»СЊ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ.",
  };
  return descriptions[normalized] || "РЎРёСЃС‚РµРјРЅРѕРµ СЃРѕР±С‹С‚РёРµ Р±РµР· РґРѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕРіРѕ РѕРїРёСЃР°РЅРёСЏ.";
}

function showMessage(text) {
  showText(messageHost, text);
}

function clearMessage() {
  clearText(messageHost);
}

function formatNumber(value) {
  return new Intl.NumberFormat("ru-RU").format(Number(value || 0));
}

function renderBadge(text, tone = "neutral") {
  return `<span class="admin-badge admin-badge--${tone}">${escapeHtml(text)}</span>`;
}

function renderFilterChip(label, key) {
  return `
    <button type="button" class="admin-filter-chip" data-clear-filter="${escapeHtml(key)}">
      <span>${escapeHtml(label)}</span>
      <span class="admin-filter-chip__close" aria-hidden="true">Г—</span>
    </button>
  `;
}

function renderLoadingState(host, options = {}) {
  if (!host) {
    return;
  }
  const count = Number(options.count || 3);
  const compact = Boolean(options.compact);
  const lines = Array.from({ length: count })
    .map(
      () => `
        <div class="admin-loading-row${compact ? " admin-loading-row--compact" : ""}">
          <span class="admin-skeleton admin-skeleton--title"></span>
          <span class="admin-skeleton admin-skeleton--text"></span>
        </div>
      `,
    )
    .join("");

  host.innerHTML = `
    <div class="admin-loading" aria-live="polite" aria-busy="true">
      <p class="legal-section__description">Р—Р°РіСЂСѓР¶Р°РµРј РґР°РЅРЅС‹Рµ...</p>
      ${lines}
    </div>
  `;
}

function showOverviewLoading() {
  renderLoadingState(totalsHost, { count: 6 });
  renderLoadingState(performanceHost, { count: 4, compact: true });
  renderLoadingState(examImportHost, { count: 3 });
  renderLoadingState(endpointsHost, { count: 3, compact: true });
  renderLoadingState(usersHost, { count: 4, compact: true });
  renderLoadingState(adminEventsHost, { count: 3, compact: true });
  renderLoadingState(eventsHost, { count: 3, compact: true });
}

function setLiveStatus(text, tone = "muted") {
  if (!liveStatusHost) {
    return;
  }
  liveStatusHost.className = `admin-badge admin-badge--${tone}`;
  liveStatusHost.textContent = text;
}

function renderTotals(totals) {
  const items = [
    ["РџРѕР»СЊР·РѕРІР°С‚РµР»Рё", totals.users_total, "Р’СЃРµРіРѕ Р°РєРєР°СѓРЅС‚РѕРІ РІ СЃРёСЃС‚РµРјРµ"],
    ["API-Р·Р°РїСЂРѕСЃС‹", totals.api_requests_total, "РќР°РєРѕРїР»РµРЅРЅР°СЏ Р°РєС‚РёРІРЅРѕСЃС‚СЊ API"],
    ["Р–Р°Р»РѕР±С‹", totals.complaints_total, "РЎРіРµРЅРµСЂРёСЂРѕРІР°РЅРЅС‹Рµ Р¶Р°Р»РѕР±С‹"],
    ["Р РµР°Р±РёР»РёС‚Р°С†РёРё", totals.rehabs_total, "РЎРіРµРЅРµСЂРёСЂРѕРІР°РЅРЅС‹Рµ СЂРµР°Р±РёР»РёС‚Р°С†РёРё"],
    ["AI suggest", totals.ai_suggest_total, "РўРµРєСЃС‚РѕРІС‹Рµ AI-РѕРїРµСЂР°С†РёРё"],
    ["AI OCR", totals.ai_ocr_total, "Р Р°СЃРїРѕР·РЅР°РІР°РЅРёРµ РґРѕРєСѓРјРµРЅС‚РѕРІ"],
    ["AI-РїСЂРѕРІРµСЂРєРё СЌРєР·Р°РјРµРЅРѕРІ", totals.ai_exam_scoring_total || 0, "РЎРєРѕР»СЊРєРѕ СЂР°Р· Р·Р°РїСѓСЃРєР°Р»Р°СЃСЊ AI-РїСЂРѕРІРµСЂРєР° СЌРєР·Р°РјРµРЅРѕРІ"],
    ["РЎС‚СЂРѕРєРё СЌРєР·Р°РјРµРЅР°", totals.ai_exam_scoring_rows || 0, "РЎРєРѕР»СЊРєРѕ СЃС‚СЂРѕРє СЌРєР·Р°РјРµРЅР° СЂРµР°Р»СЊРЅРѕ РїСЂРѕРІРµСЂРµРЅРѕ"],
    ["РћС‚РІРµС‚С‹ СЌРєР·Р°РјРµРЅР°", totals.ai_exam_scoring_answers || 0, "РЎРєРѕР»СЊРєРѕ РѕС‚РІРµС‚РѕРІ РїСЂРѕС€Р»Рѕ С‡РµСЂРµР· РѕС†РµРЅРёРІР°РЅРёРµ"],
    ["Р‘РµР· LLM", totals.ai_exam_heuristic_total || 0, "РћС‚РІРµС‚С‹, Р·Р°РєСЂС‹С‚С‹Рµ Р±РµР· РѕР±СЂР°С‰РµРЅРёСЏ Рє РјРѕРґРµР»Рё"],
    ["РџРѕРїР°РґР°РЅРёСЏ РІ РєСЌС€", totals.ai_exam_cache_total || 0, "РћС‚РІРµС‚С‹, РІР·СЏС‚С‹Рµ РёР· РєСЌС€Р°"],
    ["РћС‚РІРµС‚С‹ С‡РµСЂРµР· LLM", totals.ai_exam_llm_total || 0, "РћС‚РІРµС‚С‹, СЂРµР°Р»СЊРЅРѕ СѓС€РµРґС€РёРµ РІ РјРѕРґРµР»СЊ"],
    ["Р’С‹Р·РѕРІС‹ LLM", totals.ai_exam_llm_calls_total || 0, "РЎРєРѕР»СЊРєРѕ batch-РІС‹Р·РѕРІРѕРІ СЃРґРµР»Р°Р»Рё Рє РјРѕРґРµР»Рё"],
    ["РћС€РёР±РєРё СЌРєР·Р°РјРµРЅР°", totals.ai_exam_failure_total || 0, "РћС€РёР±РєРё РѕС†РµРЅРёРІР°РЅРёСЏ СЌРєР·Р°РјРµРЅРѕРІ Рё РёРјРїРѕСЂС‚Р°"],
    ["Р’С…РѕРґСЏС‰РёР№ С‚СЂР°С„РёРє", `${formatNumber(totals.request_bytes_total)} B`, "РЎСѓРјРјР°СЂРЅС‹Р№ СЂР°Р·РјРµСЂ Р·Р°РїСЂРѕСЃРѕРІ"],
    ["РСЃС…РѕРґСЏС‰РёР№ С‚СЂР°С„РёРє", `${formatNumber(totals.response_bytes_total)} B`, "РЎСѓРјРјР°СЂРЅС‹Р№ СЂР°Р·РјРµСЂ РѕС‚РІРµС‚РѕРІ"],
    ["Р РµСЃСѓСЂСЃРЅС‹Рµ РµРґРёРЅРёС†С‹", formatNumber(totals.resource_units_total), "РЈСЃР»РѕРІРЅР°СЏ РЅР°РіСЂСѓР·РєР°"],
    ["РЎСЂРµРґРЅРёР№ API РѕС‚РІРµС‚", `${formatNumber(totals.avg_api_duration_ms)} ms`, "РЎСЂРµРґРЅСЏСЏ РґР»РёС‚РµР»СЊРЅРѕСЃС‚СЊ API"],
    ["РЎРѕР±С‹С‚РёСЏ Р·Р° 24 С‡Р°СЃР°", totals.events_last_24h, "РџРѕСЃР»РµРґРЅСЏСЏ СЃСѓС‚РѕС‡РЅР°СЏ Р°РєС‚РёРІРЅРѕСЃС‚СЊ"],
  ];

  totalsHost.innerHTML = items
    .map(
      ([label, value, hint]) => `
        <article class="legal-subcard admin-total-card">
          <div class="legal-field__label">${escapeHtml(label)}</div>
          <div class="legal-section__title">${escapeHtml(String(value))}</div>
          <p class="legal-section__description">${escapeHtml(hint)}</p>
        </article>
      `,
    )
    .join("");
}

function renderPerformance(payload) {
  if (!performanceHost) {
    return;
  }
  const isCached = Boolean(payload?.cached);
  const totals = payload?.totals || {};
  const latency = payload?.latency || {};
  const rates = payload?.rates || {};
  const top = Array.isArray(payload?.top_endpoints) ? payload.top_endpoints : [];
  const snapshotAt = String(payload?.snapshot_at || "вЂ”");

  performanceHost.innerHTML = `
    <article class="legal-status-card">
      <span class="legal-status-card__label">РЎРЅРёРјРѕРє</span>
      <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(snapshotAt)}</strong>
      <span class="admin-user-cell__secondary">${renderBadge(isCached ? "cache" : "live", isCached ? "muted" : "success-soft")}</span>
    </article>
    <article class="legal-status-card">
      <span class="legal-status-card__label">p95 / p50 (ms)</span>
      <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(latency.p95_ms ?? "вЂ”"))} / ${escapeHtml(String(latency.p50_ms ?? "вЂ”"))}</strong>
      <span class="admin-user-cell__secondary">РћС€РёР±РѕРє: ${escapeHtml(String(totals.failed_requests ?? 0))} РёР· ${escapeHtml(String(totals.total_requests ?? 0))}</span>
    </article>
    <article class="legal-status-card">
      <span class="legal-status-card__label">RPS</span>
      <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(rates.requests_per_second ?? "вЂ”"))}</strong>
      <span class="admin-user-cell__secondary">РћРєРЅРѕ: ${escapeHtml(String(payload?.window_minutes ?? "вЂ”"))} РјРёРЅ</span>
    </article>
    <article class="legal-status-card">
      <span class="legal-status-card__label">РўРѕРї endpoint</span>
      <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(top[0]?.path || "вЂ”"))}</strong>
      <span class="admin-user-cell__secondary">Р—Р°РїСЂРѕСЃРѕРІ: ${escapeHtml(String(top[0]?.count || 0))}</span>
    </article>
  `;
}

function renderTopEndpoints(items) {
  if (!items.length) {
    endpointsHost.innerHTML = '<p class="legal-section__description">РџРѕРєР° РЅРµС‚ РґР°РЅРЅС‹С… РїРѕ API-Р·Р°РїСЂРѕСЃР°Рј.</p>';
    return;
  }

  endpointsHost.innerHTML = `
    <div class="legal-table-shell">
      <table class="legal-table admin-table admin-table--compact">
        <thead><tr><th>Р­РЅРґРїРѕРёРЅС‚</th><th>Р§С‚Рѕ РґРµР»Р°РµС‚</th><th>Р—Р°РїСЂРѕСЃРѕРІ</th></tr></thead>
        <tbody>
          ${items
            .map(
              (item) => `
                <tr>
                  <td class="admin-table__path" title="${escapeHtml(item.path || "-")}">${escapeHtml(item.path || "-")}</td>
                  <td>${escapeHtml(describeApiPath(item.path || ""))}</td>
                  <td>${escapeHtml(String(item.count || 0))}</td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderExamImport(summary) {
  if (!examImportHost) {
    return;
  }

  if (!summary) {
    examImportHost.innerHTML = '<p class="legal-section__description">РџРѕРєР° РЅРµС‚ РґР°РЅРЅС‹С… РїРѕ РёРјРїРѕСЂС‚Сѓ СЌРєР·Р°РјРµРЅРѕРІ.</p>';
    return;
  }

  const lastSync = summary.last_sync || {};
  const lastScore = summary.last_score || {};
  const recentFailures = [...(summary.recent_failures || []), ...(summary.recent_row_failures || [])];

  examImportHost.innerHTML = `
    <div class="admin-exam-grid">
      <article class="legal-status-card">
        <span class="legal-status-card__label">РћР¶РёРґР°СЋС‚ РѕС†РµРЅРёРІР°РЅРёСЏ</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(summary.pending_scores || 0))}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">РџРѕСЃР»РµРґРЅСЏСЏ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(lastSync.created_at || "вЂ”")}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">РџРѕСЃР»РµРґРЅРµРµ РѕС†РµРЅРёРІР°РЅРёРµ</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(lastScore.created_at || "вЂ”")}</strong>
      </article>
    </div>
    <div class="admin-exam-meta">
      <div class="admin-user-cell">
        <strong>${escapeHtml(lastSync.path || "/api/exam-import/sync")}</strong>
        <span class="admin-user-cell__secondary">${escapeHtml(lastSync.status_code ? `РЎС‚Р°С‚СѓСЃ ${lastSync.status_code}` : "Р—Р°РїСѓСЃРєРѕРІ РїРѕРєР° РЅРµ Р±С‹Р»Рѕ")}</span>
      </div>
      <div class="admin-user-cell">
        <strong>${escapeHtml(lastScore.path || "/api/exam-import/score")}</strong>
        <span class="admin-user-cell__secondary">${escapeHtml(lastScore.status_code ? `РЎС‚Р°С‚СѓСЃ ${lastScore.status_code}` : "РџСЂРѕРІРµСЂРѕРє РїРѕРєР° РЅРµ Р±С‹Р»Рѕ")}</span>
      </div>
    </div>
    ${
      recentFailures.length
        ? `
          <div class="legal-table-shell">
            <table class="legal-table admin-table admin-table--compact">
              <thead>
                <tr><th>Р’СЂРµРјСЏ</th><th>РўРёРї</th><th>РџСѓС‚СЊ</th><th>Р§С‚Рѕ СЃР»СѓС‡РёР»РѕСЃСЊ</th></tr>
              </thead>
              <tbody>
                ${recentFailures
                  .map(
                    (event) => `
                      <tr>
                        <td>${escapeHtml(event.created_at || "-")}</td>
                        <td>${renderBadge(event.event_type || "-", "danger")}</td>
                        <td class="admin-table__path" title="${escapeHtml(event.path || "-")}">${escapeHtml(event.path || "-")}</td>
                        <td>${escapeHtml((event.meta && (event.meta.error || event.meta.error_type)) || describeEventType(event.event_type || ""))}</td>
                      </tr>
                    `,
                  )
                  .join("")}
              </tbody>
            </table>
          </div>
        `
        : '<p class="legal-section__description">РџРѕСЃР»РµРґРЅРёС… РѕС€РёР±РѕРє РёРјРїРѕСЂС‚Р° СЌРєР·Р°РјРµРЅРѕРІ Рё AI-РѕС†РµРЅРёРІР°РЅРёСЏ РЅРµ РЅР°Р№РґРµРЅРѕ.</p>'
    }
  `;
}

function renderActiveFilters(filters) {
  if (!activeFiltersHost) {
    return;
  }

  const chips = [];
  if (filters.search) chips.push(renderFilterChip(`РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ: ${filters.search}`, "search"));
  if (filters.user_sort && filters.user_sort !== "complaints") {
    const sortLabels = {
      api_requests: "РЎРѕСЂС‚РёСЂРѕРІРєР°: API-Р°РєС‚РёРІРЅРѕСЃС‚СЊ",
      last_seen: "РЎРѕСЂС‚РёСЂРѕРІРєР°: РїРѕСЃР»РµРґРЅСЏСЏ Р°РєС‚РёРІРЅРѕСЃС‚СЊ",
      created_at: "РЎРѕСЂС‚РёСЂРѕРІРєР°: РґР°С‚Р° СЂРµРіРёСЃС‚СЂР°С†РёРё",
      username: "РЎРѕСЂС‚РёСЂРѕРІРєР°: username",
    };
    chips.push(renderFilterChip(sortLabels[filters.user_sort] || `РЎРѕСЂС‚РёСЂРѕРІРєР°: ${filters.user_sort}`, "user_sort"));
  }
  if (filters.blocked_only) chips.push(renderFilterChip("РўРѕР»СЊРєРѕ Р·Р°Р±Р»РѕРєРёСЂРѕРІР°РЅРЅС‹Рµ", "blocked_only"));
  if (filters.tester_only) chips.push(renderFilterChip("РўРѕР»СЊРєРѕ С‚РµСЃС‚РµСЂС‹", "tester_only"));
  if (filters.gka_only) chips.push(renderFilterChip("РўРѕР»СЊРєРѕ Р“РљРђ-Р—Р“РљРђ", "gka_only"));
  if (filters.unverified_only) chips.push(renderFilterChip("РўРѕР»СЊРєРѕ Р±РµР· РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ email", "unverified_only"));
  if (filters.event_search) chips.push(renderFilterChip(`РЎРѕР±С‹С‚РёСЏ: ${filters.event_search}`, "event_search"));
  if (filters.event_type) chips.push(renderFilterChip(`РўРёРї: ${filters.event_type}`, "event_type"));
  if (filters.failed_events_only) chips.push(renderFilterChip("РўРѕР»СЊРєРѕ РѕС€РёР±РєРё", "failed_events_only"));

  if (!chips.length) {
    activeFiltersHost.innerHTML = "";
    activeFiltersHost.hidden = true;
    return;
  }

  activeFiltersHost.innerHTML = chips.join("");
  activeFiltersHost.hidden = false;
}

function renderUserStatuses(user) {
  const badges = [
    user.email_verified ? renderBadge("Email OK", "success") : renderBadge("Email РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅ", "muted"),
    user.access_blocked ? renderBadge("Р—Р°Р±Р»РѕРєРёСЂРѕРІР°РЅ", "danger") : renderBadge("РђРєС‚РёРІРµРЅ", "success-soft"),
    user.is_tester ? renderBadge("РўРµСЃС‚РµСЂ", "info") : renderBadge("РћР±С‹С‡РЅС‹Р№", "neutral"),
    user.is_gka ? renderBadge("Р“РљРђ-Р—Р“РљРђ", "info") : null,
  ];
  return `<div class="admin-badge-row">${badges.filter(Boolean).join("")}</div>`;
}

function renderUserActivity(user) {
  return `
    <div class="admin-activity">
      <div class="admin-activity__main">
        <strong>${escapeHtml(String(user.complaints || 0))}</strong><span>Р¶Р°Р»РѕР±</span>
        <strong>${escapeHtml(String(user.rehabs || 0))}</strong><span>rehab</span>
      </div>
      <div class="admin-activity__meta">
        <span>AI: ${escapeHtml(String((user.ai_suggestions || 0) + (user.ai_ocr_requests || 0)))}</span>
        <span>API: ${escapeHtml(String(user.api_requests || 0))}</span>
        <span>RU: ${escapeHtml(String(user.resource_units || 0))}</span>
      </div>
    </div>
  `;
}

function renderUsers(users, userSort = "complaints") {
  userIndex.clear();
  users.forEach((user) => {
    userIndex.set(String(user.username || "").toLowerCase(), user);
  });

  if (!users.length) {
    usersHost.innerHTML = '<p class="legal-section__description">РџРѕ С‚РµРєСѓС‰РµРјСѓ С„РёР»СЊС‚СЂСѓ РїРѕР»СЊР·РѕРІР°С‚РµР»Рё РЅРµ РЅР°Р№РґРµРЅС‹.</p>';
    return;
  }

  usersHost.innerHTML = `
    <div class="admin-section-toolbar">
      <p class="legal-section__description">РџРѕРєР°Р·Р°РЅРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№: ${escapeHtml(String(users.length))}. РЎРѕСЂС‚РёСЂРѕРІРєР°: ${escapeHtml(String(userSort))}</p>
    </div>
    <div class="legal-table-shell">
      <table class="legal-table admin-table">
        <thead>
          <tr>
            <th>РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ</th>
            <th>РЎС‚Р°С‚СѓСЃС‹</th>
            <th>РђРєС‚РёРІРЅРѕСЃС‚СЊ</th>
            <th>РџРѕСЃР»РµРґРЅСЏСЏ Р°РєС‚РёРІРЅРѕСЃС‚СЊ</th>
            <th>РЈРїСЂР°РІР»РµРЅРёРµ</th>
          </tr>
        </thead>
        <tbody>
          ${users
            .map(
              (user) => `
                <tr class="admin-user-row">
                  <td>
                    <div class="admin-user-cell">
                      <strong class="admin-user-cell__name">${escapeHtml(user.username || "-")}</strong>
                      <span class="admin-user-cell__secondary" title="${escapeHtml(user.email || "-")}">${escapeHtml(user.email || "-")}</span>
                    </div>
                  </td>
                  <td>${renderUserStatuses(user)}</td>
                  <td>${renderUserActivity(user)}</td>
                  <td>
                    <div class="admin-user-cell">
                      <strong>${escapeHtml(user.last_seen_at || "вЂ”")}</strong>
                      <span class="admin-user-cell__secondary">${escapeHtml(user.access_blocked_reason || "Р‘РµР· РїСЂРёС‡РёРЅС‹ Р±Р»РѕРєРёСЂРѕРІРєРё")}</span>
                    </div>
                  </td>
                  <td>
                    <button type="button" class="secondary-button admin-user-open-btn" data-open-user="${escapeHtml(user.username || "")}">РЈРїСЂР°РІР»РµРЅРёРµ</button>
                  </td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderEvents(events) {
  if (!events.length) {
    eventsHost.innerHTML = '<p class="legal-section__description">РЎРѕР±С‹С‚РёР№ РїРѕ С‚РµРєСѓС‰РµРјСѓ С„РёР»СЊС‚СЂСѓ РЅРµС‚.</p>';
    return;
  }

  eventsHost.innerHTML = `
    <div class="admin-section-toolbar">
      <p class="legal-section__description">РџРѕРєР°Р·Р°РЅРѕ СЃРѕР±С‹С‚РёР№: ${escapeHtml(String(events.length))}</p>
    </div>
    <div class="legal-table-shell">
      <table class="legal-table admin-table admin-table--compact">
        <thead>
          <tr>
            <th>Р’СЂРµРјСЏ</th>
            <th>РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ</th>
            <th>РўРёРї</th>
            <th>РџСѓС‚СЊ</th>
            <th>РЎС‚Р°С‚СѓСЃ</th>
            <th>ms</th>
            <th>Р РµСЃСѓСЂСЃС‹</th>
          </tr>
        </thead>
        <tbody>
          ${events
            .map((event) => {
              const statusValue = event.status_code ?? "вЂ”";
              const statusTone = Number(event.status_code || 0) >= 400 ? "danger" : "neutral";
              return `
                <tr>
                  <td>${escapeHtml(event.created_at || "-")}</td>
                  <td>${escapeHtml(event.username || "-")}</td>
                  <td>
                    <div class="admin-user-cell">
                      ${renderBadge(event.event_type || "-", "neutral")}
                      <span class="admin-user-cell__secondary">${escapeHtml(describeEventType(event.event_type || ""))}</span>
                    </div>
                  </td>
                  <td>
                    <div class="admin-user-cell">
                      <strong class="admin-table__path" title="${escapeHtml(event.path || "-")}">${escapeHtml(event.path || "-")}</strong>
                      <span class="admin-user-cell__secondary">${escapeHtml(describeApiPath(event.path || ""))}</span>
                    </div>
                  </td>
                  <td>${renderBadge(String(statusValue), statusTone)}</td>
                  <td>${escapeHtml(String(event.duration_ms ?? "-"))}</td>
                  <td>${escapeHtml(String(event.resource_units ?? 0))}</td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderAdminAudit(events) {
  if (!adminEventsHost) {
    return;
  }

  const adminEvents = events.filter((event) => String(event.event_type || "").startsWith("admin_"));
  if (!adminEvents.length) {
    adminEventsHost.innerHTML = '<p class="legal-section__description">РђРґРјРёРЅ-РґРµР№СЃС‚РІРёР№ РїРѕ С‚РµРєСѓС‰РµРјСѓ С„РёР»СЊС‚СЂСѓ РїРѕРєР° РЅРµ РІРёРґРЅРѕ.</p>';
    return;
  }

  adminEventsHost.innerHTML = `
    <div class="admin-section-toolbar">
      <p class="legal-section__description">РџРѕРєР°Р·Р°РЅРѕ Р°РґРјРёРЅ-РґРµР№СЃС‚РІРёР№: ${escapeHtml(String(adminEvents.length))}</p>
    </div>
    <div class="legal-table-shell">
      <table class="legal-table admin-table admin-table--compact">
        <thead>
          <tr>
            <th>Р’СЂРµРјСЏ</th>
            <th>РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ</th>
            <th>Р”РµР№СЃС‚РІРёРµ</th>
            <th>Р—Р°РїСЂРѕСЃ</th>
            <th>РЎС‚Р°С‚СѓСЃ</th>
          </tr>
        </thead>
        <tbody>
          ${adminEvents
            .map((event) => {
              const statusValue = event.status_code ?? "вЂ”";
              const statusTone = Number(event.status_code || 0) >= 400 ? "danger" : "success-soft";
              return `
                <tr>
                  <td>${escapeHtml(event.created_at || "-")}</td>
                  <td>${escapeHtml(event.username || "-")}</td>
                  <td>
                    <div class="admin-user-cell">
                      ${renderBadge(event.event_type || "-", "info")}
                      <span class="admin-user-cell__secondary">${escapeHtml(describeEventType(event.event_type || ""))}</span>
                    </div>
                  </td>
                  <td>
                    <div class="admin-user-cell">
                      <strong class="admin-table__path" title="${escapeHtml(event.path || "-")}">${escapeHtml(event.path || "-")}</strong>
                      <span class="admin-user-cell__secondary">${escapeHtml(describeApiPath(event.path || ""))}</span>
                    </div>
                  </td>
                  <td>${renderBadge(String(statusValue), statusTone)}</td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function currentFilters() {
  return {
    search: userSearchField?.value?.trim() || "",
    user_sort: userSortField?.value?.trim() || "complaints",
    blocked_only: Boolean(blockedOnlyField?.checked),
    tester_only: Boolean(testerOnlyField?.checked),
    gka_only: Boolean(gkaOnlyField?.checked),
    unverified_only: Boolean(unverifiedOnlyField?.checked),
    event_search: eventSearchField?.value?.trim() || "",
    event_type: eventTypeField?.value?.trim() || "",
    failed_events_only: Boolean(failedEventsOnlyField?.checked),
  };
}

function buildQuery(paramsObject, allowedKeys) {
  const params = new URLSearchParams();
  allowedKeys.forEach((key) => {
    const value = paramsObject[key];
    if (value === undefined || value === null || value === "" || value === false) {
      return;
    }
    params.set(key, value === true ? "true" : String(value));
  });
  return params.toString();
}

function buildOverviewUrl() {
  const query = buildQuery(currentFilters(), [
    "search",
    "user_sort",
    "blocked_only",
    "tester_only",
    "gka_only",
    "unverified_only",
    "event_search",
    "event_type",
    "failed_events_only",
  ]);
  return query ? `/api/admin/overview?${query}` : "/api/admin/overview";
}

function buildUsersCsvUrl() {
  const query = buildQuery(currentFilters(), [
    "search",
    "user_sort",
    "blocked_only",
    "tester_only",
    "gka_only",
    "unverified_only",
  ]);
  return query ? `/api/admin/users.csv?${query}` : "/api/admin/users.csv";
}

function buildEventsCsvUrl() {
  const query = buildQuery(currentFilters(), ["event_search", "event_type", "failed_events_only"]);
  return query ? `/api/admin/events.csv?${query}` : "/api/admin/events.csv";
}

function renderUserModal(user) {
  if (!userModalBody || !user) {
    return;
  }

  userModalBody.innerHTML = `
    <div class="legal-status-row legal-status-row--three">
      <article class="legal-status-card">
        <span class="legal-status-card__label">РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(user.username || "-")}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Email</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(user.email || "-")}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">РџРѕСЃР»РµРґРЅСЏСЏ Р°РєС‚РёРІРЅРѕСЃС‚СЊ</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(user.last_seen_at || "вЂ”")}</strong>
      </article>
    </div>

    <div class="legal-subcard admin-user-detail-card">
      <div class="legal-subcard__header">
        <div>
          <span class="legal-field__label">РЎС‚Р°С‚СѓСЃС‹</span>
          <p class="legal-section__description">РљР»СЋС‡РµРІС‹Рµ С„Р»Р°РіРё Рё РїСЂРёС‡РёРЅР° Р±Р»РѕРєРёСЂРѕРІРєРё.</p>
        </div>
      </div>
      ${renderUserStatuses(user)}
      <div class="admin-user-detail-grid">
        <div><span class="legal-field__label">РџСЂРёС‡РёРЅР° Р±Р»РѕРєРёСЂРѕРІРєРё</span><div class="admin-user-detail-text">${escapeHtml(user.access_blocked_reason || "РќРµ СѓРєР°Р·Р°РЅР°")}</div></div>
        <div><span class="legal-field__label">РЎРѕР·РґР°РЅ</span><div class="admin-user-detail-text">${escapeHtml(user.created_at || "вЂ”")}</div></div>
      </div>
    </div>

    <div class="legal-subcard admin-user-detail-card">
      <div class="legal-subcard__header">
        <div>
          <span class="legal-field__label">РђРєС‚РёРІРЅРѕСЃС‚СЊ</span>
          <p class="legal-section__description">РљСЂР°С‚РєР°СЏ СЃРІРѕРґРєР° РїРѕ РґРµР№СЃС‚РІРёСЏРј РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ.</p>
        </div>
      </div>
      <div class="admin-user-summary-grid">
        <article class="legal-status-card"><span class="legal-status-card__label">Р–Р°Р»РѕР±С‹</span><strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(user.complaints || 0))}</strong></article>
        <article class="legal-status-card"><span class="legal-status-card__label">Rehab</span><strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(user.rehabs || 0))}</strong></article>
        <article class="legal-status-card"><span class="legal-status-card__label">AI</span><strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String((user.ai_suggestions || 0) + (user.ai_ocr_requests || 0)))}</strong></article>
        <article class="legal-status-card"><span class="legal-status-card__label">API</span><strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(user.api_requests || 0))}</strong></article>
        <article class="legal-status-card"><span class="legal-status-card__label">Р РµСЃСѓСЂСЃС‹</span><strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(user.resource_units || 0))}</strong></article>
      </div>
    </div>

    <div class="legal-subcard admin-user-detail-card">
      <div class="legal-subcard__header">
        <div>
          <span class="legal-field__label">Р‘С‹СЃС‚СЂС‹Рµ РґРµР№СЃС‚РІРёСЏ</span>
          <p class="legal-section__description">РЈРїСЂР°РІР»РµРЅРёРµ РґРѕСЃС‚СѓРїРѕРј Рё СѓС‡РµС‚РЅРѕР№ Р·Р°РїРёСЃСЊСЋ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ.</p>
        </div>
      </div>
      <div class="admin-user-actions">
        <button type="button" class="ghost-button" data-verify-email="${escapeHtml(user.username || "")}">РџРѕРґС‚РІРµСЂРґРёС‚СЊ email</button>
        <button type="button" class="ghost-button" data-change-email="${escapeHtml(user.username || "")}" data-current-email="${escapeHtml(user.email || "")}">РЎРјРµРЅРёС‚СЊ email</button>
        <button type="button" class="ghost-button" data-reset-password="${escapeHtml(user.username || "")}">РЎР±СЂРѕСЃРёС‚СЊ РїР°СЂРѕР»СЊ</button>
        ${
          user.is_tester
            ? `<button type="button" class="ghost-button" data-revoke-tester="${escapeHtml(user.username || "")}">РЎРЅСЏС‚СЊ С‚РµСЃС‚РµСЂР°</button>`
            : `<button type="button" class="ghost-button" data-grant-tester="${escapeHtml(user.username || "")}">Р’С‹РґР°С‚СЊ С‚РµСЃС‚РµСЂР°</button>`
        }
        ${
          user.is_gka
            ? `<button type="button" class="ghost-button" data-revoke-gka="${escapeHtml(user.username || "")}">РЎРЅСЏС‚СЊ Р“РљРђ-Р—Р“РљРђ</button>`
            : `<button type="button" class="ghost-button" data-grant-gka="${escapeHtml(user.username || "")}">Р’С‹РґР°С‚СЊ Р“РљРђ-Р—Р“РљРђ</button>`
        }
        ${
          user.access_blocked
            ? `<button type="button" class="ghost-button" data-unblock-user="${escapeHtml(user.username || "")}">Р Р°Р·Р±Р»РѕРєРёСЂРѕРІР°С‚СЊ</button>`
            : `<button type="button" class="ghost-button" data-block-user="${escapeHtml(user.username || "")}">Р—Р°Р±Р»РѕРєРёСЂРѕРІР°С‚СЊ</button>`
        }
      </div>
    </div>
  `;
}

function openUserModal(username) {
  const user = userIndex.get(String(username || "").toLowerCase());
  if (!user) {
    return;
  }
  selectedUser = user.username || "";
  renderUserModal(user);
  userModal.open();
}

async function loadAdminPerformance({ silent = false } = {}) {
  if (!silent) {
    renderLoadingState(performanceHost, { count: 4, compact: true });
  }
  try {
    const response = await apiFetch("/api/admin/performance?window_minutes=30&top_endpoints=6");
    if (!response.ok) {
      const payload = await parsePayload(response);
      if (!silent) {
        showText(errorsHost, payload.detail || "Не удалось загрузить метрики производительности.");
      }
      return;
    }
    const payload = await parsePayload(response);
    renderPerformance(payload);
  } catch (error) {
    if (!silent) {
      showText(errorsHost, error?.message || "Не удалось загрузить метрики производительности.");
    }
  }
}

async function loadAdminOverview({ silent = false } = {}) {
  if (!silent) {
    clearText(errorsHost);
    clearMessage();
    showOverviewLoading();
  } else {
    setLiveStatus("Live: обновление...", "info");
  }

  try {
    const response = await apiFetch(buildOverviewUrl());
    if (!response.ok) {
      const payload = await parsePayload(response);
      if (!silent) {
        showText(errorsHost, payload.detail || "Не удалось загрузить данные админ-панели.");
      } else {
        setLiveStatus("Live: ошибка обновления", "danger");
      }
      return;
    }

    const payload = await parsePayload(response);
    renderActiveFilters(currentFilters());
    renderTotals(payload.totals || {});
    renderExamImport(payload.exam_import || null);
    renderTopEndpoints(payload.top_endpoints || []);
    renderUsers(payload.users || [], payload.filters?.user_sort || "complaints");
    renderAdminAudit(payload.recent_events || []);
    renderEvents(payload.recent_events || []);

    if (selectedUser && userIndex.has(String(selectedUser).toLowerCase())) {
      renderUserModal(userIndex.get(String(selectedUser).toLowerCase()));
    }
    if (silent) {
      setLiveStatus(`Live: синхронно ${new Date().toLocaleTimeString("ru-RU")}`, "success-soft");
    }
  } catch (error) {
    if (!silent) {
      showText(errorsHost, error?.message || "Не удалось загрузить данные админ-панели.");
    } else {
      setLiveStatus("Live: ошибка обновления", "danger");
    }
  }
}
function scheduleOverviewReload() {
  if (adminSearchTimer) {
    clearTimeout(adminSearchTimer);
  }
  adminSearchTimer = window.setTimeout(() => {
    loadAdminOverview();
  }, 300);
}

function clearLiveTimer() {
  if (!adminLiveTimer) {
    return;
  }
  window.clearInterval(adminLiveTimer);
  adminLiveTimer = null;
}

function scheduleLiveRefresh() {
  clearLiveTimer();
  if (!liveRefreshField?.checked) {
    setLiveStatus("Live: выключено", "muted");
    return;
  }

  const intervalSeconds = Number(liveIntervalField?.value || 30);
  const safeIntervalMs = Math.max(10, intervalSeconds) * 1000;
  setLiveStatus(`Live: интервал ${Math.max(10, intervalSeconds)}с`, "info");

  adminLiveTimer = window.setInterval(async () => {
    if (document.hidden) {
      return;
    }
    await Promise.all([
      loadAdminOverview({ silent: true }),
      loadAdminPerformance({ silent: true }),
    ]);
  }, safeIntervalMs);
}

function resetFilters() {
  if (userSearchField) userSearchField.value = "";
  if (userSortField) userSortField.value = "complaints";
  if (blockedOnlyField) blockedOnlyField.checked = false;
  if (testerOnlyField) testerOnlyField.checked = false;
  if (gkaOnlyField) gkaOnlyField.checked = false;
  if (unverifiedOnlyField) unverifiedOnlyField.checked = false;
  if (eventSearchField) eventSearchField.value = "";
  if (eventTypeField) eventTypeField.value = "";
  if (failedEventsOnlyField) failedEventsOnlyField.checked = false;
  loadAdminOverview();
}

function clearFilter(key) {
  if (key === "search" && userSearchField) userSearchField.value = "";
  if (key === "user_sort" && userSortField) userSortField.value = "complaints";
  if (key === "blocked_only" && blockedOnlyField) blockedOnlyField.checked = false;
  if (key === "tester_only" && testerOnlyField) testerOnlyField.checked = false;
  if (key === "gka_only" && gkaOnlyField) gkaOnlyField.checked = false;
  if (key === "unverified_only" && unverifiedOnlyField) unverifiedOnlyField.checked = false;
  if (key === "event_search" && eventSearchField) eventSearchField.value = "";
  if (key === "event_type" && eventTypeField) eventTypeField.value = "";
  if (key === "failed_events_only" && failedEventsOnlyField) failedEventsOnlyField.checked = false;
  loadAdminOverview();
}

function downloadCsv(url) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

async function performAdminAction(url, successText, body = null) {
  clearText(errorsHost);
  clearMessage();
  try {
    const response = await apiFetch(url, {
      method: "POST",
      body: body ? JSON.stringify(body) : null,
    });
    if (!response.ok) {
      const payload = await parsePayload(response);
      showText(errorsHost, payload.detail || "РќРµ СѓРґР°Р»РѕСЃСЊ РІС‹РїРѕР»РЅРёС‚СЊ РґРµР№СЃС‚РІРёРµ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂР°.");
      return;
    }
    showMessage(successText);
    await loadAdminOverview();
  } catch (error) {
    showText(errorsHost, error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ РІС‹РїРѕР»РЅРёС‚СЊ РґРµР№СЃС‚РІРёРµ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂР°.");
  }
}

async function handleAdminAction(target) {
  const verifyUsername = target.getAttribute("data-verify-email");
  if (verifyUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(verifyUsername)}/verify-email`, "Email РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РїРѕРґС‚РІРµСЂР¶РґРµРЅ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂРѕРј.");
    return true;
  }

  const unblockUsername = target.getAttribute("data-unblock-user");
  if (unblockUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(unblockUsername)}/unblock`, "Р”РѕСЃС‚СѓРї РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅ.");
    return true;
  }

  const blockUsername = target.getAttribute("data-block-user");
  if (blockUsername) {
    const reason = window.prompt("РџСЂРёС‡РёРЅР° Р±Р»РѕРєРёСЂРѕРІРєРё (РЅРµРѕР±СЏР·Р°С‚РµР»СЊРЅРѕ):", "") || "";
    await performAdminAction(`/api/admin/users/${encodeURIComponent(blockUsername)}/block`, "Р”РѕСЃС‚СѓРї РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ Р·Р°Р±Р»РѕРєРёСЂРѕРІР°РЅ.", { reason });
    return true;
  }

  const grantTesterUsername = target.getAttribute("data-grant-tester");
  if (grantTesterUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(grantTesterUsername)}/grant-tester`, "РЎС‚Р°С‚СѓСЃ С‚РµСЃС‚РµСЂР° РІС‹РґР°РЅ.");
    return true;
  }

  const revokeTesterUsername = target.getAttribute("data-revoke-tester");
  if (revokeTesterUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(revokeTesterUsername)}/revoke-tester`, "РЎС‚Р°С‚СѓСЃ С‚РµСЃС‚РµСЂР° СЃРЅСЏС‚.");
    return true;
  }

  const grantGkaUsername = target.getAttribute("data-grant-gka");
  if (grantGkaUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(grantGkaUsername)}/grant-gka`, "РўРёРї Р“РљРђ-Р—Р“РљРђ РїСЂРёСЃРІРѕРµРЅ.");
    return true;
  }

  const revokeGkaUsername = target.getAttribute("data-revoke-gka");
  if (revokeGkaUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(revokeGkaUsername)}/revoke-gka`, "РўРёРї Р“РљРђ-Р—Р“РљРђ СЃРЅСЏС‚.");
    return true;
  }

  const changeEmailUsername = target.getAttribute("data-change-email");
  if (changeEmailUsername) {
    const currentEmail = target.getAttribute("data-current-email") || "";
    const email = window.prompt("РќРѕРІС‹Р№ email РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ:", currentEmail) || "";
    if (!email.trim()) {
      return true;
    }
    await performAdminAction(`/api/admin/users/${encodeURIComponent(changeEmailUsername)}/email`, "Email РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РѕР±РЅРѕРІР»РµРЅ.", { email });
    return true;
  }

  const resetPasswordUsername = target.getAttribute("data-reset-password");
  if (resetPasswordUsername) {
    const password = window.prompt("РќРѕРІС‹Р№ РїР°СЂРѕР»СЊ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ:") || "";
    if (!password.trim()) {
      return true;
    }
    await performAdminAction(`/api/admin/users/${encodeURIComponent(resetPasswordUsername)}/reset-password`, "РџР°СЂРѕР»СЊ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РѕР±РЅРѕРІР»РµРЅ.", { password });
    return true;
  }

  return false;
}

usersHost.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }

  const openUser = target.getAttribute("data-open-user");
  if (openUser) {
    openUserModal(openUser);
  }
});

userModalBody?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  await handleAdminAction(target);
});

userSearchField?.addEventListener("input", scheduleOverviewReload);
userSortField?.addEventListener("change", loadAdminOverview);
blockedOnlyField?.addEventListener("change", loadAdminOverview);
testerOnlyField?.addEventListener("change", loadAdminOverview);
gkaOnlyField?.addEventListener("change", loadAdminOverview);
unverifiedOnlyField?.addEventListener("change", loadAdminOverview);
eventSearchField?.addEventListener("input", scheduleOverviewReload);
eventTypeField?.addEventListener("change", loadAdminOverview);
failedEventsOnlyField?.addEventListener("change", loadAdminOverview);
resetFiltersButton?.addEventListener("click", resetFilters);
exportUsersButton?.addEventListener("click", () => downloadCsv(buildUsersCsvUrl()));
exportEventsButton?.addEventListener("click", () => downloadCsv(buildEventsCsvUrl()));
liveRefreshField?.addEventListener("change", scheduleLiveRefresh);
liveIntervalField?.addEventListener("change", scheduleLiveRefresh);
refreshNowButton?.addEventListener("click", async () => {
  await Promise.all([
    loadAdminOverview(),
    loadAdminPerformance(),
  ]);
});
activeFiltersHost?.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const chip = target.closest("[data-clear-filter]");
  if (!(chip instanceof HTMLElement)) {
    return;
  }
  clearFilter(chip.getAttribute("data-clear-filter") || "");
});

userModal.bind(
  document.getElementById("admin-user-modal-close"),
  document.getElementById("admin-user-modal-ok"),
);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    userModal.close();
  }
});

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    return;
  }
  if (liveRefreshField?.checked) {
    Promise.all([
      loadAdminOverview({ silent: true }),
      loadAdminPerformance({ silent: true }),
    ]);
  }
});

initCollapsibles();
Promise.all([
  loadAdminOverview(),
  loadAdminPerformance(),
]).then(() => {
  scheduleLiveRefresh();
});

