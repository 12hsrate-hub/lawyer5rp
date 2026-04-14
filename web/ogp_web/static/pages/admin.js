const errorsHost = document.getElementById("admin-errors");
const messageHost = document.getElementById("admin-message");
const totalsHost = document.getElementById("admin-totals");
const examImportHost = document.getElementById("admin-exam-import");
const performanceHost = document.getElementById("admin-performance");
const usersHost = document.getElementById("admin-users");
const eventsHost = document.getElementById("admin-events");
const adminEventsHost = document.getElementById("admin-admin-events");
const errorExplorerHost = document.getElementById("admin-errors-explorer");
const costSummaryHost = document.getElementById("admin-cost-summary");
const modelPolicyHost = document.getElementById("admin-model-policy");
const aiPipelineHost = document.getElementById("admin-ai-pipeline");
const roleHistoryHost = document.getElementById("admin-role-history");
const endpointsHost = document.getElementById("admin-top-endpoints");
const syntheticHost = document.getElementById("admin-synthetic");
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
const userModalTitle = document.getElementById("admin-user-modal-title");
const userModalBody = document.getElementById("admin-user-modal-body");
const actionModalTitle = document.getElementById("admin-action-modal-title");
const actionModalDescription = document.getElementById("admin-action-modal-description");
const actionModalErrors = document.getElementById("admin-action-modal-errors");
const actionReasonField = document.getElementById("admin-action-reason-field");
const actionReasonInput = document.getElementById("admin-action-reason");
const actionEmailField = document.getElementById("admin-action-email-field");
const actionEmailInput = document.getElementById("admin-action-email");
const actionPasswordField = document.getElementById("admin-action-password-field");
const actionPasswordInput = document.getElementById("admin-action-password");
const actionQuotaField = document.getElementById("admin-action-quota-field");
const actionQuotaInput = document.getElementById("admin-action-quota");
const actionConfirmButton = document.getElementById("admin-action-confirm");
const actionCancelButton = document.getElementById("admin-action-cancel");
const catalogModalTitle = document.getElementById("admin-catalog-modal-title");
const catalogModalErrors = document.getElementById("admin-catalog-modal-errors");
const catalogForm = document.getElementById("admin-catalog-form");
const catalogTitleInput = document.getElementById("admin-catalog-title");
const catalogJsonInput = document.getElementById("admin-catalog-json");
const catalogJsonError = document.getElementById("admin-catalog-json-error");
const catalogPublishedHost = document.getElementById("admin-catalog-published");
const catalogDraftHost = document.getElementById("admin-catalog-draft");
const catalogSaveButton = document.getElementById("admin-catalog-save");
const catalogCancelButton = document.getElementById("admin-catalog-cancel");
const catalogHost = document.getElementById("admin-catalog");

const {
  apiFetch,
  parsePayload,
  setStateSuccess,
  setStateError,
  setStateIdle,
  escapeHtml,
  createModalController,
  redirectIfUnauthorized,
} = window.OGPWeb;
const ExamView = window.OGPExamImportView;
const ADMIN_COLLAPSE_STORAGE_KEY = "ogp_admin_collapsible_sections";
const LAW_REBUILD_TASK_STORAGE_KEY = "ogp_admin_law_rebuild_task_id";
const DEFAULT_USER_MODAL_TITLE = userModalTitle?.textContent || "Карточка пользователя";

let adminSearchTimer = null;
let adminLiveTimer = null;
let lawRebuildPollTimer = null;
let selectedUser = null;
let pendingAction = null;
let selectedBulkUsers = new Set();
const userIndex = new Map();
let activeCatalogEntity = String(catalogHost?.dataset.catalogEntity || "servers");
let activeSyntheticSuite = "";
let pendingCatalogContext = null;
let activeLawServerCode = "";
let lawServerOptions = [];

function catalogEndpoint(entityType, itemId = "") {
  const suffix = itemId ? `/${encodeURIComponent(itemId)}` : "";
  return `/api/admin/catalog/${encodeURIComponent(entityType)}${suffix}`;
}

function withLawServerQuery(path) {
  const selected = String(activeLawServerCode || "").trim();
  if (!selected) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}server_code=${encodeURIComponent(selected)}`;
}

function getLawServerSelect() {
  return document.getElementById("law-sources-server-select");
}

function getLawRebuildTaskStorageKey(serverCode = activeLawServerCode) {
  const normalized = String(serverCode || "").trim().toLowerCase();
  return normalized ? `${LAW_REBUILD_TASK_STORAGE_KEY}:${normalized}` : LAW_REBUILD_TASK_STORAGE_KEY;
}

function getStoredLawRebuildTaskId(serverCode = activeLawServerCode) {
  return String(window.localStorage.getItem(getLawRebuildTaskStorageKey(serverCode)) || "").trim();
}

function setStoredLawRebuildTaskId(taskId, serverCode = activeLawServerCode) {
  const normalizedTaskId = String(taskId || "").trim();
  const storageKey = getLawRebuildTaskStorageKey(serverCode);
  if (!normalizedTaskId) {
    window.localStorage.removeItem(storageKey);
    return;
  }
  window.localStorage.setItem(storageKey, normalizedTaskId);
}

function clearStoredLawRebuildTaskId(serverCode = activeLawServerCode) {
  window.localStorage.removeItem(getLawRebuildTaskStorageKey(serverCode));
}
function formatCatalogPreviewValue(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "string") {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

function renderCatalogPreview(payload) {
  const host = document.getElementById("catalog-preview");
  const summaryHost = document.getElementById("catalog-preview-summary");
  const bodyHost = document.getElementById("catalog-preview-body");
  if (!host || !summaryHost || !bodyHost) {
    return;
  }
  const item = payload?.item || {};
  const effectivePayload = payload?.effective_payload || {};
  const effectiveVersion = payload?.effective_version || {};
  summaryHost.innerHTML = `
    <strong>${escapeHtml(String(item.title || "—"))}</strong>
    <span class="admin-user-cell__secondary">status: ${escapeHtml(String(item.status || item.state || "draft"))}</span>
    <span class="admin-user-cell__secondary">version: ${escapeHtml(String(effectiveVersion?.version_number ?? item.current_published_version_id ?? item.version_number ?? "—"))}</span>
  `;
  bodyHost.textContent = formatCatalogPreviewValue(effectivePayload);
  host.hidden = false;
}

function renderLawServerSelector() {
  const select = getLawServerSelect();
  if (!(select instanceof HTMLSelectElement)) {
    return;
  }
  const options = lawServerOptions.length ? lawServerOptions : [{ code: activeLawServerCode, title: activeLawServerCode }];
  const safeOptions = options.filter((item) => String(item?.code || "").trim());
  select.innerHTML = safeOptions
    .map((item) => {
      const code = String(item.code || "").trim().toLowerCase();
      const title = String(item.title || code).trim();
      const isSelected = code === String(activeLawServerCode || "").trim().toLowerCase();
      return `<option value="${escapeHtml(code)}" ${isSelected ? "selected" : ""}>${escapeHtml(`${title} (${code})`)}</option>`;
    })
    .join("");
}

async function loadLawServerOptions() {
  if (!catalogHost || activeCatalogEntity !== "laws") return;
  const response = await apiFetch("/api/admin/runtime-servers");
  const payload = await parsePayload(response);
  if (!response.ok) {
    lawServerOptions = [];
    return;
  }
  const rows = Array.isArray(payload?.items) ? payload.items : [];
  lawServerOptions = rows
    .filter((item) => item && String(item.code || "").trim())
    .map((item) => ({
      code: String(item.code || "").trim().toLowerCase(),
      title: String(item.title || "").trim(),
      is_active: Boolean(item.is_active),
    }));
  if (!activeLawServerCode) {
    const firstActive = lawServerOptions.find((item) => item.is_active);
    if (firstActive?.code) {
      activeLawServerCode = firstActive.code;
    } else if (lawServerOptions[0]?.code) {
      activeLawServerCode = lawServerOptions[0].code;
    }
  }
  renderLawServerSelector();
}

async function loadLawSourcesManager() {
  if (!catalogHost || activeCatalogEntity !== "laws") {
    return;
  }
  stopLawRebuildPolling();
  const select = getLawServerSelect();
  if (select instanceof HTMLSelectElement && select.value) {
    activeLawServerCode = String(select.value || "").trim().toLowerCase();
  }
  const response = await apiFetch(withLawServerQuery("/api/admin/law-sources"));
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось загрузить источники законов."));
    return;
  }
  const payloadServerCode = String(payload?.server_code || "").trim().toLowerCase();
  if (payloadServerCode) {
    activeLawServerCode = payloadServerCode;
  }
  renderLawServerSelector();
  const textarea = document.getElementById("law-sources-textarea");
  const statusHost = document.getElementById("law-sources-status");
  if (textarea) {
    textarea.value = Array.isArray(payload?.source_urls) ? payload.source_urls.join("\n") : "";
  }
  if (statusHost) {
    const activeVersionId = payload?.active_law_version?.id ?? "—";
    const chunkCount = payload?.bundle_meta?.chunk_count ?? payload?.active_law_version?.chunk_count ?? "—";
    const origin = String(payload?.source_origin || "unknown");
    statusHost.textContent = `Источник ссылок: ${origin}. Активная версия закона: ${activeVersionId}. Статей в индексе: ${chunkCount}.`;
  }
  await loadLawSourcesHistory();
  await loadLawSourcesDependencies();
  setLawActionButtonsDisabled(false);
  const storedTaskId = getStoredLawRebuildTaskId();
  if (storedTaskId) {
    setLawActionButtonsDisabled(true);
    await pollLawRebuildTask(storedTaskId);
  }
}

function renderLawSourcesHistory(payload) {
  const host = document.getElementById("law-sources-history");
  if (!host) {
    return;
  }
  const items = Array.isArray(payload?.items) ? payload.items : [];
  if (!items.length) {
    host.innerHTML = '<p class="legal-section__description">История пересборок пока пуста.</p>';
    return;
  }
  host.innerHTML = `
    <ul class="legal-section__description">
      ${items
        .map((item) => `<li>Версия #${escapeHtml(String(item.id || "—"))} • articles: ${escapeHtml(String(item.chunk_count || 0))} • generated: ${escapeHtml(String(item.generated_at_utc || "—"))}</li>`)
        .join("")}
    </ul>
  `;
}

async function loadLawSourcesHistory() {
  const response = await apiFetch(withLawServerQuery("/api/admin/law-sources/history?limit=8"));
  const payload = await parsePayload(response);
  if (!response.ok) {
    return;
  }
  renderLawSourcesHistory(payload);
}

function renderLawSourcesDependencies(payload) {
  const host = document.getElementById("law-sources-dependencies");
  if (!host) {
    return;
  }
  const rows = Array.isArray(payload?.servers) ? payload.servers : [];
  if (!rows.length) {
    host.innerHTML = '<p class="legal-section__description">Нет данных по зависимостям источников.</p>';
    return;
  }
  host.innerHTML = `
    <div class="legal-section__description"><strong>Связь серверов и источников законов</strong></div>
    <table class="legal-table">
      <thead><tr><th>Сервер</th><th>Источников</th><th>Общих источников</th><th>Связан с серверами</th></tr></thead>
      <tbody>
        ${rows
          .map((row) => `<tr>
            <td>${escapeHtml(String(row?.server_name || row?.server_code || "—"))}</td>
            <td>${escapeHtml(String(row?.source_count || 0))}</td>
            <td>${escapeHtml(String(row?.shared_source_count || 0))}</td>
            <td>${escapeHtml(String((row?.shared_with_servers || []).join(", ") || "—"))}</td>
          </tr>`)
          .join("")}
      </tbody>
    </table>
  `;
}

async function loadLawSourcesDependencies() {
  const response = await apiFetch("/api/admin/law-sources/dependencies");
  const payload = await parsePayload(response);
  if (!response.ok) {
    return;
  }
  renderLawSourcesDependencies(payload);
}

function parseLawSetItemsInput(raw) {
  const rows = String(raw || "")
    .split(/\r?\n/)
    .map((line) => String(line || "").trim())
    .filter(Boolean);
  return rows.map((line, index) => {
    const [lawCode, sourceIdRaw, priorityRaw, effectiveFromRaw] = line.split("|").map((part) => String(part || "").trim());
    if (!lawCode) {
      throw new Error(`Строка ${index + 1}: law_code обязателен.`);
    }
    const sourceId = Number(sourceIdRaw || 0);
    const priority = Number(priorityRaw || 100);
    return {
      law_code: lawCode,
      source_id: Number.isFinite(sourceId) && sourceId > 0 ? sourceId : null,
      priority: Number.isFinite(priority) ? priority : 100,
      effective_from: effectiveFromRaw || "",
    };
  });
}

function renderLawSets(payload) {
  const host = document.getElementById("law-sets-host");
  if (!host) return;
  const items = Array.isArray(payload?.items) ? payload.items : [];
  host.innerHTML = `
    <table class="legal-table admin-table admin-table--compact">
      <thead><tr><th>ID</th><th>Название</th><th>Статус</th><th>Публикация</th><th>Элементов</th><th>Действия</th></tr></thead>
      <tbody>
        ${items.length ? items.map((item) => `
          <tr>
            <td>${escapeHtml(String(item.id || "—"))}</td>
            <td>${escapeHtml(String(item.name || "—"))}</td>
            <td>${item.is_active ? "active" : "disabled"}</td>
            <td>${item.is_published ? "published" : "draft"}</td>
            <td>${escapeHtml(String(item.item_count || 0))}</td>
            <td>
              <button type="button" class="ghost-button" data-law-set-edit="${escapeHtml(String(item.id || ""))}" data-law-set-name="${escapeHtml(String(item.name || ""))}" data-law-set-active="${item.is_active ? "1" : "0"}">Изменить</button>
              <button type="button" class="ghost-button" data-law-set-publish="${escapeHtml(String(item.id || ""))}">Опубликовать</button>
              <button type="button" class="ghost-button" data-law-set-rebuild="${escapeHtml(String(item.id || ""))}">Rebuild</button>
            </td>
          </tr>
        `).join("") : '<tr><td colspan="6" class="legal-section__description">Наборы законов пока не созданы.</td></tr>'}
      </tbody>
    </table>
  `;
}

async function loadLawSets() {
  const host = document.getElementById("law-sets-host");
  if (!host || !activeLawServerCode) return;
  const response = await apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(activeLawServerCode)}/law-sets`);
  const payload = await parsePayload(response);
  if (!response.ok) {
    host.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, "Не удалось загрузить наборы законов."))}</p>`;
    return;
  }
  renderLawSets(payload);
}

async function createLawSetFlow() {
  if (!activeLawServerCode) {
    setStateError(errorsHost, "Сначала выберите сервер.");
    return;
  }
  const name = String(window.prompt("Название набора законов", `${activeLawServerCode}-default`) || "").trim();
  if (!name) return;
  const rawItems = String(
    window.prompt(
      "Элементы набора (строки формата law_code|source_id|priority|effective_from)",
      "",
    ) || ""
  );
  let items = [];
  try {
    items = rawItems ? parseLawSetItemsInput(rawItems) : [];
  } catch (error) {
    setStateError(errorsHost, String(error?.message || error));
    return;
  }
  const response = await apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(activeLawServerCode)}/law-sets`, {
    method: "POST",
    body: JSON.stringify({ name, is_active: true, items }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось создать набор законов."));
    return;
  }
  showMessage(`Набор законов создан: ${name}.`);
  await loadLawSets();
}

async function editLawSetFlow(lawSetId, currentName, currentIsActive) {
  const name = String(window.prompt("Новое название набора", currentName || "") || "").trim();
  if (!name) return;
  const rawItems = String(
    window.prompt(
      "Элементы набора (строки формата law_code|source_id|priority|effective_from)",
      "",
    ) || ""
  );
  let items = [];
  try {
    items = rawItems ? parseLawSetItemsInput(rawItems) : [];
  } catch (error) {
    setStateError(errorsHost, String(error?.message || error));
    return;
  }
  const response = await apiFetch(`/api/admin/law-sets/${encodeURIComponent(String(lawSetId))}`, {
    method: "PUT",
    body: JSON.stringify({ name, is_active: currentIsActive, items }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось обновить набор законов."));
    return;
  }
  showMessage(`Набор #${lawSetId} обновлен.`);
  await loadLawSets();
}

async function publishLawSetFlow(lawSetId) {
  const response = await apiFetch(`/api/admin/law-sets/${encodeURIComponent(String(lawSetId))}/publish`, { method: "POST" });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось опубликовать набор."));
    return;
  }
  showMessage(`Набор #${lawSetId} опубликован.`);
  await loadLawSets();
}

async function rebuildLawSetFlow(lawSetId) {
  const response = await apiFetch(`/api/admin/law-sets/${encodeURIComponent(String(lawSetId))}/rebuild`, { method: "POST" });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось пересобрать набор."));
    return;
  }
  showMessage(`Набор #${lawSetId} пересобран. Версия: ${String(payload?.result?.law_version_id || "—")}.`);
  await loadLawSourcesManager();
}

function renderLawSourceRegistry(payload) {
  const host = document.getElementById("law-source-registry-host");
  if (!host) return;
  const items = Array.isArray(payload?.items) ? payload.items : [];
  host.innerHTML = `
    <table class="legal-table admin-table admin-table--compact">
      <thead><tr><th>ID</th><th>Название</th><th>Kind</th><th>URL</th><th>Статус</th><th>Действия</th></tr></thead>
      <tbody>
        ${items.length ? items.map((item) => `
          <tr>
            <td>${escapeHtml(String(item.id || "—"))}</td>
            <td>${escapeHtml(String(item.name || "—"))}</td>
            <td>${escapeHtml(String(item.kind || "url"))}</td>
            <td class="admin-user-cell__secondary">${escapeHtml(String(item.url || "—"))}</td>
            <td>${item.is_active ? "active" : "disabled"}</td>
            <td>
              <button type="button" class="ghost-button" data-law-source-edit="${escapeHtml(String(item.id || ""))}" data-law-source-name="${escapeHtml(String(item.name || ""))}" data-law-source-kind="${escapeHtml(String(item.kind || "url"))}" data-law-source-url="${escapeHtml(String(item.url || ""))}" data-law-source-active="${item.is_active ? "1" : "0"}">Изменить</button>
            </td>
          </tr>
        `).join("") : '<tr><td colspan="6" class="legal-section__description">Реестр источников пуст.</td></tr>'}
      </tbody>
    </table>
  `;
}

async function loadLawSourceRegistry() {
  const host = document.getElementById("law-source-registry-host");
  if (!host) return;
  const response = await apiFetch("/api/admin/law-source-registry");
  const payload = await parsePayload(response);
  if (!response.ok) {
    host.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, "Не удалось загрузить реестр источников."))}</p>`;
    return;
  }
  renderLawSourceRegistry(payload);
}

async function createLawSourceRegistryFlow() {
  const name = String(window.prompt("Название источника", "") || "").trim();
  if (!name) return;
  const kind = String(window.prompt("Kind (url|registry|api)", "url") || "url").trim().toLowerCase();
  const url = String(window.prompt("URL источника", "") || "").trim();
  if (!url) return;
  const response = await apiFetch("/api/admin/law-source-registry", {
    method: "POST",
    body: JSON.stringify({ name, kind, url, is_active: true }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось создать источник."));
    return;
  }
  showMessage("Источник добавлен в реестр.");
  await loadLawSourceRegistry();
}

async function editLawSourceRegistryFlow(sourceId, currentName, currentKind, currentUrl, currentActive) {
  const name = String(window.prompt("Название источника", currentName || "") || "").trim();
  if (!name) return;
  const kind = String(window.prompt("Kind (url|registry|api)", currentKind || "url") || "url").trim().toLowerCase();
  const url = String(window.prompt("URL источника", currentUrl || "") || "").trim();
  if (!url) return;
  const response = await apiFetch(`/api/admin/law-source-registry/${encodeURIComponent(String(sourceId))}`, {
    method: "PUT",
    body: JSON.stringify({ name, kind, url, is_active: currentActive }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось обновить источник."));
    return;
  }
  showMessage("Источник обновлен.");
  await loadLawSourceRegistry();
}

async function rebuildLawSources() {
  const textarea = document.getElementById("law-sources-textarea");
  const raw = String(textarea?.value || "");
  const sourceUrls = raw
    .split(/\r?\n/)
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const response = await apiFetch("/api/admin/law-sources/rebuild", {
    method: "POST",
    body: JSON.stringify({
      server_code: activeLawServerCode,
      source_urls: sourceUrls,
      persist_sources: true,
    }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось пересобрать законы."));
    return;
  }
  showMessage(`Законы обновлены: версия ${String(payload?.law_version_id || "—")}, статей ${String(payload?.article_count || 0)}.`);
  await loadCatalog("laws");
}

function stopLawRebuildPolling() {
  if (lawRebuildPollTimer) {
    window.clearTimeout(lawRebuildPollTimer);
    lawRebuildPollTimer = null;
  }
}

function setLawActionButtonsDisabled(disabled) {
  ["law-sources-sync", "law-sources-save", "law-sources-preview", "law-sources-rebuild-async", "law-sources-rebuild"].forEach((id) => {
    const button = document.getElementById(id);
    if (button instanceof HTMLButtonElement) {
      button.disabled = Boolean(disabled);
    }
  });
}

async function pollLawRebuildTask(taskId) {
  const statusHost = document.getElementById("law-sources-task-status");
  const response = await apiFetch(withLawServerQuery(`/api/admin/law-sources/tasks/${encodeURIComponent(taskId)}`));
  const payload = await parsePayload(response);
  if (!response.ok) {
    stopLawRebuildPolling();
    setLawActionButtonsDisabled(false);
    if (statusHost) {
      statusHost.textContent = "Не удалось получить статус фоновой пересборки.";
    }
    return;
  }
  const status = String(payload?.status || "queued");
  if (statusHost) {
    statusHost.textContent = `Фоновая пересборка: ${status} (task: ${taskId})`;
  }
  if (status === "finished") {
    stopLawRebuildPolling();
    setLawActionButtonsDisabled(false);
    clearStoredLawRebuildTaskId();
    showMessage(`Фоновая пересборка завершена. Версия ${String(payload?.result?.law_version_id || "—")}.`);
    await loadCatalog("laws");
    return;
  }
  if (status === "failed") {
    stopLawRebuildPolling();
    setLawActionButtonsDisabled(false);
    clearStoredLawRebuildTaskId();
    setStateError(errorsHost, String(payload?.error || "Фоновая пересборка завершилась ошибкой."));
    return;
  }
  lawRebuildPollTimer = window.setTimeout(() => {
    void pollLawRebuildTask(taskId);
  }, 2000);
}

async function rebuildLawSourcesAsync() {
  const textarea = document.getElementById("law-sources-textarea");
  const raw = String(textarea?.value || "");
  const sourceUrls = raw
    .split(/\r?\n/)
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const response = await apiFetch("/api/admin/law-sources/rebuild-async", {
    method: "POST",
    body: JSON.stringify({
      server_code: activeLawServerCode,
      source_urls: sourceUrls,
      persist_sources: true,
    }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    const details = Array.isArray(payload?.detail) ? payload.detail : [];
    const conflictDetail = details.find((item) => String(item || "").startsWith("law_rebuild_already_in_progress:"));
    if (response.status === 409 && conflictDetail) {
      const activeTaskId = String(conflictDetail).split(":")[1] || "";
      if (activeTaskId) {
        setStoredLawRebuildTaskId(activeTaskId);
        setLawActionButtonsDisabled(true);
        await pollLawRebuildTask(activeTaskId);
        return;
      }
    }
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось поставить пересборку в очередь."));
    return;
  }
  showMessage(`Пересборка поставлена в очередь (task: ${String(payload?.task_id || "—")}).`);
  setStoredLawRebuildTaskId(String(payload?.task_id || ""));
  setLawActionButtonsDisabled(true);
  stopLawRebuildPolling();
  await pollLawRebuildTask(String(payload?.task_id || ""));
}

async function saveLawSourcesManifest() {
  const textarea = document.getElementById("law-sources-textarea");
  const raw = String(textarea?.value || "");
  const sourceUrls = raw
    .split(/\r?\n/)
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const response = await apiFetch("/api/admin/law-sources/save", {
    method: "POST",
    body: JSON.stringify({
      server_code: activeLawServerCode,
      source_urls: sourceUrls,
      persist_sources: true,
    }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось сохранить источники законов."));
    return;
  }
  showMessage("Источники законов сохранены в workflow.");
  await loadCatalog("laws");
}

async function previewLawSources() {
  const textarea = document.getElementById("law-sources-textarea");
  const raw = String(textarea?.value || "");
  const sourceUrls = raw
    .split(/\r?\n/)
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const response = await apiFetch("/api/admin/law-sources/preview", {
    method: "POST",
    body: JSON.stringify({
      server_code: activeLawServerCode,
      source_urls: sourceUrls,
      persist_sources: false,
    }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось проверить ссылки законов."));
    return;
  }
  const detailsHost = document.getElementById("law-sources-validation");
  if (detailsHost) {
    const invalidUrls = Array.isArray(payload?.invalid_urls) ? payload.invalid_urls : [];
    const invalidDetails = Array.isArray(payload?.invalid_details) ? payload.invalid_details : [];
    const duplicateUrls = Array.isArray(payload?.duplicate_urls) ? payload.duplicate_urls : [];
    const invalidBlock = invalidDetails.length
      ? `<br><strong>Невалидные ссылки:</strong><br>${invalidDetails
        .map((item) => `${escapeHtml(String(item?.url || ""))} (${escapeHtml(String(item?.reason || "invalid"))})`)
        .join("<br>")}`
      : (invalidUrls.length
        ? `<br><strong>Невалидные ссылки:</strong><br>${invalidUrls.map((item) => escapeHtml(String(item))).join("<br>")}`
        : "");
    const duplicateBlock = duplicateUrls.length
      ? `<br><strong>Дубликаты (после нормализации):</strong><br>${duplicateUrls.map((item) => escapeHtml(String(item))).join("<br>")}`
      : "";
    detailsHost.innerHTML = `Принято: ${escapeHtml(String(payload?.accepted_count ?? 0))}. Дубликатов: ${escapeHtml(String(payload?.duplicate_count ?? 0))}. Невалидных: ${escapeHtml(String(payload?.invalid_count ?? 0))}.${invalidBlock}${duplicateBlock}`;
  }
  showMessage("Проверка ссылок выполнена.");
}

async function syncLawSourcesFromServerConfig() {
  const response = await apiFetch(withLawServerQuery("/api/admin/law-sources/sync"), {
    method: "POST",
    body: JSON.stringify({}),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось синхронизировать ссылки законов."));
    return;
  }
  showMessage(payload?.changed ? "Ссылки законов перенесены из server config в DB." : "DB-источники законов уже актуальны.");
  await loadCatalog("laws");
}

function renderCatalog(payload) {
  if (!catalogHost) return;
  const entityType = payload?.entity_type || activeCatalogEntity;
  activeCatalogEntity = entityType;
  const items = Array.isArray(payload?.items) ? payload.items : [];
  const audit = Array.isArray(payload?.audit) ? payload.audit : [];
  const entityLabels = {
    servers: "Серверы",
    laws: "Законы",
    templates: "Шаблоны",
    features: "Функции",
    rules: "Правила",
  };
  const entityDescriptions = {
    servers: "Серверные профили и базовые настройки окружения.",
    laws: "Правовые источники и наборы норм, на которые опирается система.",
    templates: "Шаблоны документов и заготовки для генерации.",
    features: "Переключатели функций и rollout-настройки.",
    rules: "Правила публикации, редактирования и governance-политики.",
  };
  const statusLabels = {
    draft: "черновик",
    in_review: "на ревью",
    approved: "одобрено",
    published: "опубликовано",
    rolled_back: "откат",
  };
  const workflowActionLabels = {
    submit_for_review: "Отправить на ревью",
    approve: "Одобрить",
    publish: "Опубликовать",
    request_changes: "Запросить доработки",
  };
  const allowedActionsByState = {
    draft: ["submit_for_review"],
    in_review: ["approve", "request_changes"],
    approved: ["publish"],
  };
  const auditByEntityId = new Map();
  audit.forEach((row) => {
    const entityId = String(row?.entity_id || "").trim();
    if (!entityId || auditByEntityId.has(entityId)) {
      return;
    }
    auditByEntityId.set(entityId, row);
  });
  catalogHost.innerHTML = `
    <div class="admin-section-toolbar">
      <label class="legal-field"><span class="legal-field__label">Раздел</span>
        <select id="catalog-entity">
          ${["servers", "laws", "templates", "features", "rules"]
            .map((name) => `<option value="${name}" ${name === entityType ? "selected" : ""}>${entityLabels[name]}</option>`)
            .join("")}
        </select>
      </label>
      <button type="button" id="catalog-create" class="primary-button">Создать</button>
    </div>
    <p class="legal-section__description">${escapeHtml(entityDescriptions[entityType] || "")}</p>
    ${entityType === "servers" ? `
    <div class="legal-subcard">
      <div class="admin-section-toolbar">
        <strong>Runtime серверы</strong>
        <div>
          <button type="button" id="runtime-servers-refresh" class="ghost-button">Обновить</button>
          <button type="button" id="runtime-servers-create" class="primary-button">Добавить сервер</button>
        </div>
      </div>
      <p class="legal-section__description">Управление реальными серверами из таблицы <code>servers</code>.</p>
      <div id="runtime-servers-host"></div>
    </div>
    ` : ""}
    ${entityType === "laws" ? `
    <div class="legal-subcard">
      <div class="admin-section-toolbar">
        <strong>Источники законов</strong>
        <label class="legal-field" style="min-width:260px">
          <span class="legal-field__label">Сервер (обязательно)</span>
          <select id="law-sources-server-select"></select>
        </label>
        <div>
          <button type="button" id="law-sources-sync" class="ghost-button">Синхронизировать текущие</button>
          <button type="button" id="law-sources-save" class="ghost-button">Сохранить без пересборки</button>
          <button type="button" id="law-sources-preview" class="ghost-button">Проверить ссылки</button>
          <button type="button" id="law-sources-rebuild-async" class="ghost-button">Пересобрать в фоне</button>
          <button type="button" id="law-sources-rebuild" class="primary-button">Пересобрать законы</button>
        </div>
      </div>
      <p id="law-sources-status" class="legal-section__description">Загружаем источники и активную версию...</p>
      <p id="law-sources-validation" class="legal-section__description">Перед пересборкой можно проверить ссылки на валидность и дубликаты.</p>
      <p id="law-sources-task-status" class="legal-section__description"></p>
      <label class="legal-field">
        <span class="legal-field__label">Ссылки на законы</span>
        <textarea id="law-sources-textarea" rows="8" placeholder="По одной ссылке на строку"></textarea>
        <span class="legal-field__hint">После сохранения система скачает страницы, нарежет материалы на статьи и импортирует новую DB-версию закона для текущего сервера.</span>
      </label>
      <div id="law-sources-history"></div>
      <div id="law-sources-dependencies"></div>
      <hr>
      <div class="admin-section-toolbar">
        <strong>Наборы законов сервера</strong>
        <div>
          <button type="button" id="law-sets-refresh" class="ghost-button">Обновить наборы</button>
          <button type="button" id="law-sets-create" class="primary-button">Добавить набор</button>
        </div>
      </div>
      <div id="law-sets-host"></div>
      <hr>
      <div class="admin-section-toolbar">
        <strong>Реестр источников</strong>
        <div>
          <button type="button" id="law-source-registry-refresh" class="ghost-button">Обновить реестр</button>
          <button type="button" id="law-source-registry-create" class="primary-button">Добавить источник</button>
        </div>
      </div>
      <div id="law-source-registry-host"></div>
    </div>
    ` : ""}
    <div class="legal-table-wrap">
      <table class="legal-table">
        <thead><tr><th>Название</th><th>Статус</th><th>Версия</th><th>Автор</th><th>Действия</th></tr></thead>
        <tbody>
          ${items.length
            ? items
            .map((item) => {
              const entityId = String(item.id || "");
              const auditRow = auditByEntityId.get(entityId) || {};
              const state = String(item.active_change_request_status || item.status || item.state || "draft").trim().toLowerCase();
              const stateLabel = statusLabels[state] || state;
              const changeRequestId = Number(item.active_change_request_id || item.change_request_id || 0);
              const workflowActions = changeRequestId ? (allowedActionsByState[state] || []) : [];
              const version = item.current_published_version_id ?? item.version_number ?? "—";
              const author = String(
                auditRow.author || item.updated_by || item.created_by || "system"
              );
              return `
              <tr data-machine-state="${escapeHtml(state)}" data-change-request-id="${escapeHtml(String(changeRequestId || 0))}">
                <td>${escapeHtml(String(item.title || ""))}</td>
                <td>${escapeHtml(stateLabel)}</td>
                <td>${escapeHtml(String(version))}</td>
                <td>${escapeHtml(author)}</td>
                <td>
                  <button type="button" class="ghost-button" data-catalog-view="${escapeHtml(String(item.id || ""))}">Поля</button>
                  <button type="button" class="ghost-button" data-catalog-edit="${escapeHtml(String(item.id || ""))}">Изменить</button>
                  <button type="button" class="ghost-button" data-catalog-preview="${escapeHtml(String(item.id || ""))}">Предпросмотр</button>
                  ${workflowActions
                    .map(
                      (action) => `<button type="button" class="ghost-button" data-catalog-workflow-item="${escapeHtml(String(item.id || ""))}" data-catalog-workflow-action="${escapeHtml(action)}" data-catalog-workflow-cr-id="${escapeHtml(String(changeRequestId || 0))}">${escapeHtml(workflowActionLabels[action] || action)}</button>`,
                    )
                    .join("")}
                  <button type="button" class="ghost-button" data-catalog-rollback="${escapeHtml(String(item.id || ""))}">Откат</button>
                  <button type="button" class="ghost-button" data-catalog-delete="${escapeHtml(String(item.id || ""))}">Удалить</button>
                </td>
              </tr>
            `;
            })
            .join("")
            : '<tr><td colspan="5" class="legal-section__description">Для этого раздела пока нет записей.</td></tr>'}
        </tbody>
      </table>
      <div id="catalog-preview" class="legal-subcard" hidden>
        <div id="catalog-preview-summary" class="legal-section__description"></div>
        <pre id="catalog-preview-body" class="legal-field__hint">—</pre>
      </div>
    </div>
    <section id="catalog-preview-panel" class="admin-catalog-preview" hidden>
      <div class="admin-catalog-preview__header">
        <h4 class="admin-catalog-preview__title">Предпросмотр</h4>
        <button type="button" id="catalog-preview-copy" class="ghost-button">Копировать JSON</button>
      </div>
      <div id="catalog-preview-summary" class="admin-catalog-preview__summary"></div>
      <p class="legal-section__description">Связанные версии и последний change request:</p>
      <pre id="catalog-preview-meta" class="admin-catalog-preview__meta"></pre>
      <p class="legal-section__description">Effective/current payload:</p>
      <pre id="catalog-preview-json" class="admin-catalog-preview__json"></pre>
    </section>
    <p class="legal-section__description">Журнал изменений (автор и diff):</p>
    <pre class="legal-field__hint">${escapeHtml(audit.slice(0, 8).map((row) => `${row.created_at} ${row.author} ${row.action} ${row.workflow_from || ""}->${row.workflow_to || ""}\n${row.diff || ""}`).join("\n\n"))}</pre>
  `;
}

function renderRuntimeServersPanel(payload) {
  const host = document.getElementById("runtime-servers-host");
  if (!host) return;
  const items = Array.isArray(payload?.items) ? payload.items : [];
  host.innerHTML = `
    <table class="legal-table admin-table admin-table--compact">
      <thead>
        <tr><th>Код</th><th>Название</th><th>Статус</th><th>Действия</th></tr>
      </thead>
      <tbody>
        ${items.length
          ? items.map((item) => `
            <tr>
              <td>${escapeHtml(String(item.code || "—"))}</td>
              <td>${escapeHtml(String(item.title || "—"))}</td>
              <td>${item.is_active ? "active" : "disabled"}</td>
              <td>
                <button type="button" class="ghost-button" data-runtime-server-edit="${escapeHtml(String(item.code || ""))}" data-runtime-server-title="${escapeHtml(String(item.title || ""))}">Изменить</button>
                <button type="button" class="ghost-button" data-runtime-server-toggle="${escapeHtml(String(item.code || ""))}" data-runtime-server-active="${item.is_active ? "1" : "0"}">${item.is_active ? "Деактивировать" : "Активировать"}</button>
              </td>
            </tr>
          `).join("")
          : '<tr><td colspan="4" class="legal-section__description">Серверы не найдены.</td></tr>'}
      </tbody>
    </table>
  `;
}

async function loadRuntimeServersPanel() {
  const host = document.getElementById("runtime-servers-host");
  if (!host) return;
  const response = await apiFetch("/api/admin/runtime-servers");
  const payload = await parsePayload(response);
  if (!response.ok) {
    host.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, "Не удалось загрузить runtime серверы."))}</p>`;
    return;
  }
  renderRuntimeServersPanel(payload);
}

async function createRuntimeServerFlow() {
  const code = String(window.prompt("Код сервера (латиница/цифры/_-.)", "") || "").trim().toLowerCase();
  if (!code) return;
  const title = String(window.prompt("Название сервера", code) || "").trim();
  if (!title) return;
  const response = await apiFetch("/api/admin/runtime-servers", {
    method: "POST",
    body: JSON.stringify({ code, title }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось создать сервер."));
    return;
  }
  showMessage(`Сервер ${code} создан.`);
  await loadRuntimeServersPanel();
}

async function editRuntimeServerFlow(code, currentTitle) {
  const title = String(window.prompt(`Новое название для ${code}`, currentTitle || code) || "").trim();
  if (!title) return;
  const response = await apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(code)}`, {
    method: "PUT",
    body: JSON.stringify({ code, title }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось обновить сервер."));
    return;
  }
  showMessage(`Сервер ${code} обновлен.`);
  await loadRuntimeServersPanel();
}

async function toggleRuntimeServerFlow(code, isActive) {
  const action = isActive ? "deactivate" : "activate";
  const response = await apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(code)}/${action}`, {
    method: "POST",
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось обновить статус сервера."));
    return;
  }
  showMessage(`Статус сервера ${code} обновлен.`);
  await loadRuntimeServersPanel();
}

function renderCatalogPreviewSummary(entityType, item, effectivePayload) {
  const keyOrder = ["key", "name", "title", "status", "enabled", "code", "version", "updated_at"];
  const rows = [];
  keyOrder.forEach((field) => {
    const value = field in effectivePayload ? effectivePayload[field] : item?.[field];
    if (value !== undefined && value !== null && value !== "") {
      rows.push({ field, value });
    }
  });
  if (!rows.length) {
    rows.push({ field: "entity_type", value: entityType });
    rows.push({ field: "item_id", value: item?.id ?? "—" });
  }
  return rows
    .slice(0, 10)
    .map(
      (entry) => `<div class="admin-catalog-preview__summary-row"><span>${escapeHtml(entry.field)}</span><strong>${escapeHtml(String(entry.value))}</strong></div>`
    )
    .join("");
}

function renderCatalogPreview(payload, itemId) {
  const previewPanel = document.getElementById("catalog-preview-panel");
  const summaryHost = document.getElementById("catalog-preview-summary");
  const metaHost = document.getElementById("catalog-preview-meta");
  const jsonHost = document.getElementById("catalog-preview-json");
  if (!previewPanel || !summaryHost || !metaHost || !jsonHost) return;
  const item = payload?.item || {};
  const effectivePayload = payload?.effective_payload && typeof payload.effective_payload === "object" ? payload.effective_payload : {};
  const versions = Array.isArray(payload?.versions) ? payload.versions : [];
  const latestChangeRequest = payload?.latest_change_request || (Array.isArray(payload?.change_requests) ? payload.change_requests[0] : null);
  const effectiveVersion = payload?.effective_version || null;
  summaryHost.innerHTML = renderCatalogPreviewSummary(activeCatalogEntity, item, effectivePayload);
  const metaPayload = {
    item_id: item?.id ?? itemId,
    content_key: item?.content_key || "",
    status: item?.status || "",
    effective_version: effectiveVersion
      ? {
        id: effectiveVersion.id,
        version_number: effectiveVersion.version_number,
        created_by: effectiveVersion.created_by,
        created_at: effectiveVersion.created_at,
      }
      : null,
    versions: versions.map((version) => ({
      id: version.id,
      version_number: version.version_number,
      schema_version: version.schema_version,
      created_by: version.created_by,
      created_at: version.created_at,
    })),
    latest_change_request: latestChangeRequest,
  };
  metaHost.textContent = JSON.stringify(metaPayload, null, 2);
  jsonHost.textContent = JSON.stringify(effectivePayload, null, 2);
  previewPanel.hidden = false;
}

async function loadCatalogPreview(itemId) {
  const response = await apiFetch(catalogEndpoint(activeCatalogEntity, itemId));
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось загрузить предпросмотр catalog."));
    return;
  }
  renderCatalogPreview(payload, itemId);
}
function slugifyCatalogKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_\-.а-яё]/gi, "")
    .replace(/_+/g, "_");
}

function getCatalogEntityFieldMeta(entityType) {
  const sharedHelp = "Заполните поля формы. JSON нужен только для редких/нестандартных атрибутов.";
  const byEntity = {
    servers: {
      description: "Профиль сервера: модель, URL и технические ограничения.",
      fields: [
        { name: "server_code", label: "Код сервера", placeholder: "prod-1", help: "Уникальный код окружения." },
        { name: "base_url", label: "Base URL", placeholder: "https://api.example.com", help: "Базовый URL сервера/интеграции." },
        { name: "timeout_sec", label: "Timeout (сек)", type: "number", min: 1, placeholder: "30", help: "Таймаут запросов в секундах." },
      ],
    },
    laws: {
      description: "Нормативный источник и его реквизиты.",
      fields: [
        { name: "law_code", label: "Код закона", placeholder: "uk_rf_2026", help: "Внутренний код закона/сборника." },
        { name: "source", label: "Источник", placeholder: "consultant", help: "Откуда взят текст (сервис/реестр)." },
        { name: "effective_from", label: "Действует с", placeholder: "2026-01-01", help: "Дата в формате YYYY-MM-DD." },
      ],
    },
    templates: {
      description: "Шаблон документа: формат, цель и обязательные блоки.",
      fields: [
        { name: "template_type", label: "Тип шаблона", placeholder: "complaint", help: "Например: complaint, appeal, rehab." },
        { name: "document_kind", label: "Вид документа", placeholder: "Жалоба", help: "Человекочитаемый вид документа." },
        { name: "output_format", label: "Формат вывода", placeholder: "bbcode", help: "Например: bbcode, markdown, html." },
      ],
    },
    features: {
      description: "Фича-флаг: rollout и условия включения.",
      fields: [
        { name: "feature_flag", label: "Feature flag", placeholder: "new_law_qa", help: "Уникальный код флага." },
        { name: "rollout_percent", label: "Rollout (%)", type: "number", min: 0, max: 100, placeholder: "25", help: "Доля пользователей в процентах." },
        { name: "audience", label: "Аудитория", placeholder: "testers", help: "Кому включено: all/testers/staff/..." },
      ],
    },
    rules: {
      description: "Правило применения: приоритет, область и действие.",
      fields: [
        { name: "rule_type", label: "Тип правила", placeholder: "moderation", help: "Категория правила." },
        { name: "priority", label: "Приоритет", type: "number", min: 0, placeholder: "100", help: "Чем больше число, тем выше приоритет." },
        { name: "applies_to", label: "Область", placeholder: "complaint_generation", help: "Где применяется правило." },
      ],
    },
  };
  return byEntity[entityType] || { description: sharedHelp, fields: [] };
}

function buildCatalogFormValues(entityType, seed = {}) {
  const config = seed.config && typeof seed.config === "object" ? seed.config : {};
  const key = String(seed.key || config.key || slugifyCatalogKey(seed.title || "") || "");
  const description = String(seed.description || config.description || "");
  const status = String(seed.status || config.status || "draft");
  const values = {
    title: String(seed.title || ""),
    key,
    description,
    status,
    config,
  };
  const meta = getCatalogEntityFieldMeta(entityType);
  meta.fields.forEach((field) => {
    values[field.name] = seed[field.name] ?? config[field.name] ?? "";
  });
  return values;
}

function parseCatalogAdvancedJson(rawJson) {
  const raw = String(rawJson || "").trim();
  if (!raw) {
    return {};
  }
  const parsed = JSON.parse(raw);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Advanced JSON должен быть объектом.");
  }
  return parsed;
}

async function openCatalogFormDialog(entityType, seed = {}) {
  const meta = getCatalogEntityFieldMeta(entityType);
  const values = buildCatalogFormValues(entityType, seed);
  const dialog = document.createElement("dialog");
  const dynamicFields = meta.fields
    .map((field) => {
      const type = field.type || "text";
      const value = String(values[field.name] ?? "");
      const min = field.min !== undefined ? `min="${field.min}"` : "";
      const max = field.max !== undefined ? `max="${field.max}"` : "";
      return `
        <label class="legal-field">
          <span class="legal-field__label">${escapeHtml(field.label)}</span>
          <input type="${escapeHtml(type)}" name="${escapeHtml(field.name)}" value="${escapeHtml(value)}" placeholder="${escapeHtml(field.placeholder || "")}" ${min} ${max}>
          <span class="legal-field__hint">${escapeHtml(field.help || "")}</span>
        </label>
      `;
    })
    .join("");
  dialog.innerHTML = `
    <form method="dialog" class="legal-section">
      <h3>${seed.id ? "Редактирование" : "Создание"}: ${escapeHtml(entityType)}</h3>
      <p class="legal-field__hint">${escapeHtml(meta.description || "")}</p>
      <label class="legal-field">
        <span class="legal-field__label">Название</span>
        <input type="text" name="title" value="${escapeHtml(values.title)}" placeholder="Понятное имя записи" required>
      </label>
      <label class="legal-field">
        <span class="legal-field__label">Ключ</span>
        <input type="text" name="key" value="${escapeHtml(values.key)}" placeholder="server_main" required>
        <span class="legal-field__hint">Уникальный ключ (латиница/цифры/подчеркивание). Пример: <code>main_ruleset</code></span>
      </label>
      <label class="legal-field">
        <span class="legal-field__label">Описание</span>
        <textarea name="description" rows="2" placeholder="Кратко: зачем нужна запись">${escapeHtml(values.description)}</textarea>
      </label>
      <label class="legal-field">
        <span class="legal-field__label">Статус</span>
        <select name="status">
          ${["draft", "review", "published", "active", "disabled", "archived"]
            .map((statusName) => `<option value="${statusName}" ${values.status === statusName ? "selected" : ""}>${statusName}</option>`)
            .join("")}
        </select>
        <span class="legal-field__hint">Обычно для новых записей используется <code>draft</code>.</span>
      </label>
      ${dynamicFields}
      <details>
        <summary>Дополнительно (JSON)</summary>
        <p class="legal-field__hint">Опционально. Добавьте редкие поля в JSON-объекте, например: {\"tags\":[\"beta\"],\"owner\":\"team-legal\"}</p>
        <label class="legal-field">
          <textarea name="advanced_config" rows="7" placeholder='{\"tags\":[\"beta\"],\"owner\":\"team-legal\"}'>${escapeHtml(JSON.stringify(values.config || {}, null, 2))}</textarea>
        </label>
      </details>
      <menu style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px;">
        <button type="button" class="ghost-button" data-action="cancel">Отмена</button>
        <button type="submit" class="primary-button" data-action="submit">Сохранить</button>
      </menu>
    </form>
  `;
  document.body.appendChild(dialog);

  return await new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      if (dialog.open) {
        dialog.close();
      }
      dialog.remove();
      resolve(value);
    };
    dialog.querySelector('[data-action="cancel"]')?.addEventListener("click", () => {
      finish(null);
    });
    dialog.addEventListener("cancel", () => finish(null));
    dialog.addEventListener("close", () => finish(null));
    dialog.querySelector("form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      if (!(form instanceof HTMLFormElement)) return;
      const formData = new FormData(form);
      try {
        const title = String(formData.get("title") || "").trim();
        const key = slugifyCatalogKey(String(formData.get("key") || ""));
        const description = String(formData.get("description") || "").trim();
        const status = String(formData.get("status") || "draft").trim().toLowerCase();
        if (!title) {
          throw new Error("Поле «Название» обязательно.");
        }
        if (!key) {
          throw new Error("Поле «Ключ» обязательно.");
        }
        const advanced = parseCatalogAdvancedJson(formData.get("advanced_config"));
        const payload = { title, key, description, status, config: advanced };
        meta.fields.forEach((field) => {
          const raw = formData.get(field.name);
          if (raw === null) return;
          const value = String(raw).trim();
          if (!value) return;
          payload[field.name] = field.type === "number" ? Number(value) : value;
        });
        finish(payload);
      } catch (error) {
        window.alert(String(error?.message || error));
      }
    });
    dialog.showModal();
  });
}

function extractCatalogEditableData(itemPayload) {
  const item = itemPayload?.item || {};
  const versions = Array.isArray(itemPayload?.versions) ? itemPayload.versions : [];
  const topVersion = versions[0]?.payload_json;
  const metadataConfig = item?.metadata_json?.config;
  const config = (topVersion && typeof topVersion === "object" && !Array.isArray(topVersion) && Object.keys(topVersion).length)
    ? topVersion
    : (metadataConfig && typeof metadataConfig === "object" ? metadataConfig : {});
  return {
    id: item.id,
    title: String(item.title || ""),
    status: String(item.status || config.status || "draft"),
    key: String(item.content_key || config.key || ""),
    description: String(config.description || ""),
    config,
  };
}

async function loadCatalog(entityType = activeCatalogEntity) {
  if (!catalogHost) return;
  const response = await apiFetch(catalogEndpoint(entityType));
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось загрузить catalog."));
    return;
  }
  renderCatalog(payload);
  if (entityType === "servers") {
    await loadRuntimeServersPanel();
  }
  if (entityType === "laws") {
    await loadLawServerOptions();
    await loadLawSourcesManager();
    await loadLawSets();
    await loadLawSourceRegistry();
  }
}

const userModal = createModalController({
  modal: document.getElementById("admin-user-modal"),
});
const actionModal = createModalController({
  modal: document.getElementById("admin-action-modal"),
});
const catalogModal = createModalController({
  modal: document.getElementById("admin-catalog-modal"),
});

function formatJsonForDisplay(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "string") {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

function extractVersionPayload(version) {
  if (!version || typeof version !== "object") return null;
  if (version.payload_json !== undefined) return version.payload_json;
  if (version.payload !== undefined) return version.payload;
  if (version.config !== undefined) return version.config;
  return null;
}

function pickCatalogVersion(versions, expectedStates = []) {
  const normalizedStates = expectedStates.map((state) => String(state || "").toLowerCase());
  return versions.find((version) => {
    const markers = [
      version?.status,
      version?.state,
      version?.workflow_state,
      version?.kind,
      version?.channel,
    ]
      .map((value) => String(value || "").toLowerCase())
      .filter(Boolean);
    return normalizedStates.some((state) => markers.includes(state));
  }) || null;
}

function parseJsonConfig(rawText) {
  try {
    return { ok: true, value: JSON.parse(rawText) };
  } catch (error) {
    const source = String(rawText || "");
    const match = /position\s+(\d+)/i.exec(String(error?.message || ""));
    if (!match) {
      return { ok: false, message: "Не удалось разобрать JSON. Проверьте синтаксис." };
    }
    const index = Number(match[1]);
    const boundedIndex = Number.isFinite(index) ? Math.max(0, Math.min(index, source.length)) : 0;
    const before = source.slice(0, boundedIndex);
    const line = before.split("\n").length;
    const column = boundedIndex - (before.lastIndexOf("\n") + 1) + 1;
    return {
      ok: false,
      message: `Некорректный JSON: ошибка на строке ${line}, позиция ${column}.`,
    };
  }
}

function resetCatalogModalState() {
  pendingCatalogContext = null;
  if (catalogModalTitle) catalogModalTitle.textContent = "Редактирование каталога";
  if (catalogTitleInput) {
    catalogTitleInput.value = "";
    catalogTitleInput.disabled = false;
  }
  if (catalogJsonInput) {
    catalogJsonInput.value = "{}";
    catalogJsonInput.disabled = false;
  }
  if (catalogJsonError) {
    catalogJsonError.textContent = "";
    catalogJsonError.hidden = true;
  }
  if (catalogPublishedHost) catalogPublishedHost.textContent = "—";
  if (catalogDraftHost) catalogDraftHost.textContent = "—";
  if (catalogSaveButton) {
    catalogSaveButton.hidden = false;
    catalogSaveButton.disabled = false;
    catalogSaveButton.textContent = "Сохранить";
  }
  if (catalogCancelButton) catalogCancelButton.textContent = "Закрыть";
  setStateIdle(catalogModalErrors);
}

function closeCatalogModal() {
  catalogModal.close();
  resetCatalogModalState();
}

function openCatalogModal(config) {
  resetCatalogModalState();
  pendingCatalogContext = config;
  const mode = config?.mode === "view" ? "view" : "edit";
  const item = config?.item || {};
  const versions = Array.isArray(config?.versions) ? config.versions : [];
  const publishedVersion = pickCatalogVersion(versions, ["published", "publish"]);
  const draftVersion = pickCatalogVersion(versions, ["candidate", "draft", "review"]);
  const activeVersion =
    pickCatalogVersion(versions, ["candidate", "draft", "review", "published", "publish"]) ||
    versions[0] ||
    null;
  const activePayload =
    extractVersionPayload(activeVersion) ??
    item.payload_json ??
    item.config ??
    {};

  if (catalogModalTitle) {
    const baseTitle = mode === "view" ? "Просмотр элемента" : (config?.isCreate ? "Создание элемента" : "Редактирование элемента");
    catalogModalTitle.textContent = `${baseTitle}: ${String(item.title || "").trim() || "без названия"}`;
  }
  if (catalogTitleInput) {
    catalogTitleInput.value = String(item.title || "");
    catalogTitleInput.disabled = mode === "view";
  }
  if (catalogJsonInput) {
    catalogJsonInput.value = formatJsonForDisplay(activePayload);
    catalogJsonInput.disabled = mode === "view";
  }
  if (catalogPublishedHost) {
    catalogPublishedHost.textContent = formatJsonForDisplay(
      extractVersionPayload(publishedVersion) ?? "Опубликованная версия отсутствует."
    );
  }
  if (catalogDraftHost) {
    catalogDraftHost.textContent = formatJsonForDisplay(
      extractVersionPayload(draftVersion) ?? "Черновик отсутствует."
    );
  }
  if (catalogSaveButton) {
    catalogSaveButton.hidden = mode === "view";
    catalogSaveButton.disabled = false;
  }
  if (catalogCancelButton) {
    catalogCancelButton.textContent = mode === "view" ? "Закрыть" : "Отмена";
  }
  catalogModal.open();
}

async function submitCatalogModal() {
  if (!pendingCatalogContext || pendingCatalogContext.mode === "view") {
    closeCatalogModal();
    return;
  }
  const title = String(catalogTitleInput?.value || "").trim();
  const rawJson = String(catalogJsonInput?.value || "").trim();
  if (!title) {
    setStateError(catalogModalErrors, "Укажите название элемента.");
    return;
  }
  const parsed = parseJsonConfig(rawJson || "{}");
  if (!parsed.ok) {
    if (catalogJsonError) {
      catalogJsonError.textContent = parsed.message;
      catalogJsonError.hidden = false;
    }
    setStateError(catalogModalErrors, parsed.message);
    return;
  }
  if (catalogJsonError) {
    catalogJsonError.textContent = "";
    catalogJsonError.hidden = true;
  }
  setStateIdle(catalogModalErrors);
  if (catalogSaveButton) catalogSaveButton.disabled = true;
  clearMessage();
  setStateIdle(errorsHost);

  const body = JSON.stringify({ title, config: parsed.value });
  const isCreate = Boolean(pendingCatalogContext.isCreate);
  const itemId = pendingCatalogContext.itemId;
  const url = isCreate ? catalogEndpoint(activeCatalogEntity) : catalogEndpoint(activeCatalogEntity, itemId);
  const method = isCreate ? "POST" : "PUT";
  try {
    const response = await apiFetch(url, { method, body });
    const payload = await parsePayload(response);
    if (!response.ok) {
      setStateError(catalogModalErrors, formatHttpError(response, payload, "Не удалось сохранить элемент."));
      if (catalogSaveButton) catalogSaveButton.disabled = false;
      return;
    }
    showMessage(isCreate ? "Элемент создан." : "Элемент обновлен.");
    closeCatalogModal();
    await loadCatalog(activeCatalogEntity);
  } catch (error) {
    setStateError(catalogModalErrors, error?.message || "Не удалось сохранить элемент.");
    if (catalogSaveButton) catalogSaveButton.disabled = false;
  }
}

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
  button.textContent = expanded ? "Скрыть" : "Показать";
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
    return "Системный запрос без указанного пути.";
  }

  const patterns = [
    [/^\/api\/admin\/overview$/, "Загрузка всей админ-панели: сводка, пользователи, события и статистика."],
    [/^\/api\/admin\/users\.csv$/, "Выгрузка CSV со списком пользователей по текущим фильтрам."],
    [/^\/api\/admin\/events\.csv$/, "Выгрузка CSV со списком событий по текущим фильтрам."],
    [/^\/api\/admin\/users\/[^/]+\/verify-email$/, "Администратор вручную подтверждает email выбранного пользователя."],
    [/^\/api\/admin\/users\/[^/]+\/block$/, "Администратор блокирует доступ пользователя к аккаунту."],
    [/^\/api\/admin\/users\/[^/]+\/unblock$/, "Администратор снимает блокировку и возвращает доступ к аккаунту."],
    [/^\/api\/admin\/users\/[^/]+\/grant-tester$/, "Администратор выдает пользователю статус тестера."],
    [/^\/api\/admin\/users\/[^/]+\/revoke-tester$/, "Администратор снимает у пользователя статус тестера."],
    [/^\/api\/admin\/users\/[^/]+\/grant-gka$/, "Администратор присваивает пользователю тип ГКА-ЗГКА."],
    [/^\/api\/admin\/users\/[^/]+\/revoke-gka$/, "Администратор снимает у пользователя тип ГКА-ЗГКА."],
    [/^\/api\/admin\/users\/[^/]+\/email$/, "Администратор вручную меняет email пользователя."],
    [/^\/api\/admin\/users\/[^/]+\/reset-password$/, "Администратор вручную задает новый пароль пользователю."],
    [/^\/api\/admin\/users\/[^/]+\/deactivate$/, "Администратор мягко деактивирует аккаунт пользователя."],
    [/^\/api\/admin\/users\/[^/]+\/reactivate$/, "Администратор снимает деактивацию аккаунта."],
    [/^\/api\/admin\/users\/[^/]+\/daily-quota$/, "Администратор задает суточный лимит API для пользователя."],
    [/^\/api\/admin\/users\/bulk-actions$/, "Администратор запускает массовую операцию по выбранным пользователям."],
    [/^\/api\/admin\/tasks\/[^/]+$/, "Проверка статуса фоновой задачи админ-операций."],
    [/^\/api\/complaint-draft$/, "Сохранение, загрузка или очистка черновика жалобы пользователя."],
    [/^\/api\/generate$/, "Генерация итоговой жалобы по заполненной форме."],
    [/^\/api\/generate-rehab$/, "Генерация заявления на реабилитацию."],
    [/^\/api\/ai\/suggest$/, "AI улучшает и переписывает описание жалобы."],
    [/^\/api\/ai\/extract-principal$/, "AI распознает данные доверителя с изображения документа."],
    [/^\/api\/auth\/login$/, "Вход пользователя в аккаунт."],
    [/^\/api\/auth\/register$/, "Регистрация нового аккаунта."],
    [/^\/api\/auth\/logout$/, "Выход пользователя из аккаунта."],
    [/^\/api\/auth\/forgot-password$/, "Запуск восстановления пароля."],
    [/^\/api\/auth\/reset-password$/, "Сброс пароля по токену восстановления."],
    [/^\/api\/profile$/, "Загрузка или сохранение данных профиля пользователя."],
    [/^\/api\/exam-import\/sync$/, "Импорт новых ответов на экзамены из Google Sheets."],
    [/^\/api\/exam-import\/score$/, "Массовая проверка импортированных экзаменационных ответов."],
    [/^\/api\/exam-import\/rows\/\d+$/, "Просмотр деталей по одной импортированной строке экзамена."],
    [/^\/api\/exam-import\/rows\/\d+\/score$/, "Проверка и оценка одной конкретной строки экзамена."],
  ];

  for (const [pattern, description] of patterns) {
    if (pattern.test(normalized)) {
      return description;
    }
  }

  return "Технический API-запрос. Для этого пути еще не добавлено человекочитаемое описание.";
}

function describeEventType(eventType) {
  const normalized = String(eventType || "").trim().toLowerCase();
  const descriptions = {
    api_request: "Обычный запрос к API приложения.",
    complaint_generated: "Пользователь сгенерировал жалобу.",
    rehab_generated: "Пользователь сгенерировал заявление на реабилитацию.",
    complaint_draft_saved: "Пользователь сохранил черновик жалобы.",
    complaint_draft_cleared: "Пользователь очистил черновик жалобы.",
    ai_suggest: "AI обработал и улучшил текст жалобы.",
    ai_extract_principal: "AI распознал данные с документа.",
    ai_exam_scoring: "AI проверил экзаменационные ответы и вернул статистику по cache, эвристикам и LLM.",
    exam_import_sync_error: "Импорт из Google Sheets завершился ошибкой.",
    exam_import_score_failures: "Во время массовой проверки экзаменов часть строк не обработалась.",
    exam_import_row_score_error: "Проверка одной строки экзамена завершилась ошибкой.",
    admin_verify_email: "Администратор подтвердил email пользователя.",
    admin_block_user: "Администратор заблокировал пользователя.",
    admin_unblock_user: "Администратор разблокировал пользователя.",
    admin_grant_tester: "Администратор выдал статус тестера.",
    admin_revoke_tester: "Администратор снял статус тестера.",
    admin_grant_gka: "Администратор присвоил тип ГКА-ЗГКА.",
    admin_revoke_gka: "Администратор снял тип ГКА-ЗГКА.",
    admin_update_email: "Администратор изменил email пользователя.",
    admin_reset_password: "Администратор задал новый пароль пользователю.",
    admin_deactivate_user: "Администратор деактивировал аккаунт пользователя.",
    admin_reactivate_user: "Администратор снял деактивацию аккаунта.",
    admin_set_daily_quota: "Администратор обновил суточную квоту API пользователя.",
  };
  return descriptions[normalized] || "Системное событие без дополнительного описания.";
}

function showMessage(text) {
  setStateSuccess(messageHost, text);
}

function clearMessage() {
  setStateIdle(messageHost);
}

function resetActionModalFields() {
  pendingAction = null;
  if (actionReasonInput) actionReasonInput.value = "";
  if (actionEmailInput) actionEmailInput.value = "";
  if (actionPasswordInput) actionPasswordInput.value = "";
  if (actionQuotaInput) actionQuotaInput.value = "";
  if (actionReasonField) actionReasonField.hidden = true;
  if (actionEmailField) actionEmailField.hidden = true;
  if (actionPasswordField) actionPasswordField.hidden = true;
  if (actionQuotaField) actionQuotaField.hidden = true;
  if (actionConfirmButton) actionConfirmButton.textContent = "Подтвердить";
  setStateIdle(actionModalErrors);
}

function openActionModal(config) {
  pendingAction = config;
  if (actionModalTitle) {
    actionModalTitle.textContent = config.title || "Подтверждение действия";
  }
  if (actionModalDescription) {
    actionModalDescription.textContent = config.description || "";
  }
  if (actionConfirmButton) {
    actionConfirmButton.textContent = config.confirmLabel || "Подтвердить";
  }
  if (actionReasonField) {
    actionReasonField.hidden = !config.askReason;
  }
  if (actionEmailField) {
    actionEmailField.hidden = !config.askEmail;
  }
  if (actionPasswordField) {
    actionPasswordField.hidden = !config.askPassword;
  }
  if (actionQuotaField) {
    actionQuotaField.hidden = !config.askQuota;
  }
  if (actionEmailInput && config.defaultEmail) {
    actionEmailInput.value = String(config.defaultEmail);
  }
  if (actionReasonInput && config.defaultReason) {
    actionReasonInput.value = String(config.defaultReason);
  }
  if (actionQuotaInput && config.defaultQuota !== undefined) {
    actionQuotaInput.value = String(config.defaultQuota);
  }
  setStateIdle(actionModalErrors);
  actionModal.open();
}

function closeActionModal() {
  actionModal.close();
  resetActionModalFields();
}

function formatNumber(value) {
  return new Intl.NumberFormat("ru-RU").format(Number(value || 0));
}

function formatUsd(value) {
  const amount = Number(value || 0);
  return amount.toLocaleString("en-US", {
    minimumFractionDigits: 4,
    maximumFractionDigits: 6,
  });
}

function renderBadge(text, tone = "neutral") {
  return `<span class="admin-badge admin-badge--${tone}">${escapeHtml(text)}</span>`;
}

function renderBandBadge(band) {
  const normalized = String(band || "unknown").trim().toLowerCase();
  if (normalized === "green" || normalized === "success" || normalized === "success-soft") {
    return renderBadge("Green", "success-soft");
  }
  if (normalized === "yellow" || normalized === "warn" || normalized === "warning" || normalized === "info") {
    return renderBadge("Yellow", "info");
  }
  if (normalized === "red" || normalized === "danger" || normalized === "error") {
    return renderBadge("Red", "danger");
  }
  return renderBadge("Unknown", "muted");
}

function riskLabel(user) {
  const riskScore = Number(user.risk_score || 0);
  if (riskScore >= 4) return renderBadge("Риск: высокий", "danger");
  if (riskScore >= 2) return renderBadge("Риск: средний", "info");
  return renderBadge("Риск: низкий", "success-soft");
}

function renderFilterChip(label, key) {
  return `
    <button type="button" class="admin-filter-chip" data-clear-filter="${escapeHtml(key)}">
      <span>${escapeHtml(label)}</span>
      <span class="admin-filter-chip__close" aria-hidden="true">×</span>
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
      <p class="legal-section__description">Загружаем данные...</p>
      ${lines}
    </div>
  `;
}

function showOverviewLoading() {
  renderLoadingState(totalsHost, { count: 6 });
  renderLoadingState(performanceHost, { count: 4, compact: true });
  renderLoadingState(examImportHost, { count: 3 });
  renderLoadingState(endpointsHost, { count: 3, compact: true });
  renderLoadingState(syntheticHost, { count: 3, compact: true });
  renderLoadingState(usersHost, { count: 4, compact: true });
  renderLoadingState(errorExplorerHost, { count: 3, compact: true });
  renderLoadingState(adminEventsHost, { count: 3, compact: true });
  renderLoadingState(eventsHost, { count: 3, compact: true });
  renderLoadingState(costSummaryHost, { count: 2, compact: true });
  renderLoadingState(aiPipelineHost, { count: 3, compact: true });
  renderLoadingState(roleHistoryHost, { count: 3, compact: true });
}

function setLiveStatus(text, tone = "muted") {
  if (!liveStatusHost) {
    return;
  }
  liveStatusHost.className = `admin-badge admin-badge--${tone}`;
  liveStatusHost.textContent = text;
}

function renderTotals(totals) {
  if (!totalsHost) {
    return;
  }
  const items = [
    ["Пользователи", totals.users_total, "Всего аккаунтов в системе"],
    ["API-запросы", totals.api_requests_total, "Накопленная активность API"],
    ["Жалобы", totals.complaints_total, "Сгенерированные жалобы"],
    ["Реабилитации", totals.rehabs_total, "Сгенерированные реабилитации"],
    ["AI suggest", totals.ai_suggest_total, "Текстовые AI-операции"],
    ["AI OCR", totals.ai_ocr_total, "Распознавание документов"],
    ["AI-проверки экзаменов", totals.ai_exam_scoring_total || 0, "Сколько раз запускалась AI-проверка экзаменов"],
    ["Строки экзамена", totals.ai_exam_scoring_rows || 0, "Сколько строк экзамена реально проверено"],
    ["Ответы экзамена", totals.ai_exam_scoring_answers || 0, "Сколько ответов прошло через оценивание"],
    ["Без LLM", totals.ai_exam_heuristic_total || 0, "Ответы, закрытые без обращения к модели"],
    ["Попадания в кэш", totals.ai_exam_cache_total || 0, "Ответы, взятые из кэша"],
    ["Ответы через LLM", totals.ai_exam_llm_total || 0, "Ответы, реально ушедшие в модель"],
    ["Вызовы LLM", totals.ai_exam_llm_calls_total || 0, "Сколько batch-вызовов сделали к модели"],
    ["Ошибки экзамена", totals.ai_exam_failure_total || 0, "Ошибки оценивания экзаменов и импорта"],
    ["Входящий трафик", `${formatNumber(totals.request_bytes_total)} B`, "Суммарный размер запросов"],
    ["Исходящий трафик", `${formatNumber(totals.response_bytes_total)} B`, "Суммарный размер ответов"],
    ["Ресурсные единицы", formatNumber(totals.resource_units_total), "Условная нагрузка"],
    ["AI cost (USD)", `$${formatUsd(totals.ai_estimated_cost_total_usd || 0)}`, `Оценка по ${formatNumber(totals.ai_estimated_cost_samples || 0)} вызовам`],
    ["AI токены (in/out/total)", `${formatNumber(totals.ai_input_tokens_total || 0)} / ${formatNumber(totals.ai_output_tokens_total || 0)} / ${formatNumber(totals.ai_total_tokens_total || 0)}`, `Сумма по ${formatNumber(totals.ai_generation_total || 0)} генерациям`],
    ["Средний API ответ", `${formatNumber(totals.avg_api_duration_ms)} ms`, "Средняя длительность API"],
    ["События за 24 часа", totals.events_last_24h, "Последняя суточная активность"],
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
  const totals = {
    ...(payload?.totals || {}),
    total_requests: (payload?.totals || {}).total_requests ?? payload?.total_api_requests ?? 0,
    failed_requests: (payload?.totals || {}).failed_requests ?? payload?.error_count ?? 0,
  };
  const latency = {
    ...(payload?.latency || {}),
    p95_ms: (payload?.latency || {}).p95_ms ?? payload?.p95_ms ?? "-",
    p50_ms: (payload?.latency || {}).p50_ms ?? payload?.p50_ms ?? "-",
  };
  const rates = {
    ...(payload?.rates || {}),
    requests_per_second: (payload?.rates || {}).requests_per_second ?? payload?.throughput_rps ?? "-",
  };
  const top = Array.isArray(payload?.top_endpoints)
    ? payload.top_endpoints
    : Array.isArray(payload?.endpoint_overview)
      ? payload.endpoint_overview
      : [];
  const snapshotAt = String(payload?.snapshot_at || payload?.generated_at || "-");

  performanceHost.innerHTML = `
    <article class="legal-status-card">
      <span class="legal-status-card__label">Снимок</span>
      <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(snapshotAt)}</strong>
      <span class="admin-user-cell__secondary">${renderBadge(isCached ? "cache" : "live", isCached ? "muted" : "success-soft")}</span>
    </article>
    <article class="legal-status-card">
      <span class="legal-status-card__label">p95 / p50 (ms)</span>
      <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(latency.p95_ms ?? "—"))} / ${escapeHtml(String(latency.p50_ms ?? "—"))}</strong>
      <span class="admin-user-cell__secondary">Ошибок: ${escapeHtml(String(totals.failed_requests ?? 0))} из ${escapeHtml(String(totals.total_requests ?? 0))}</span>
    </article>
    <article class="legal-status-card">
      <span class="legal-status-card__label">RPS</span>
      <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(rates.requests_per_second ?? "—"))}</strong>
      <span class="admin-user-cell__secondary">Окно: ${escapeHtml(String(payload?.window_minutes ?? "—"))} мин</span>
    </article>
    <article class="legal-status-card">
      <span class="legal-status-card__label">Топ endpoint</span>
      <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(top[0]?.path || "—"))}</strong>
      <span class="admin-user-cell__secondary">Запросов: ${escapeHtml(String(top[0]?.count || 0))}</span>
    </article>
  `;
}

function renderSynthetic(summary) {
  if (!syntheticHost) {
    return;
  }
  const bySuite = summary?.by_suite || {};
  const suites = ["smoke", "nightly", "load", "fault"];
  const suiteDescriptions = {
    smoke: "Быстрая проверка основных сценариев генерации, снапшотов, цитат и публикации.",
    nightly: "Расширенный регрессионный прогон полного workflow, вложений, артефактов и rollback.",
    load: "Нагрузочная проверка burst/sustained сценариев генерации, экспорта и content workflow.",
    fault: "Проверка отказоустойчивости: retry, DLQ, idempotency, isolation и policy gates.",
  };
  const cards = suites.map((suite) => {
    const row = bySuite[suite] || {};
    const latest = String(row.latest_status || "unknown");
    const tone = latest === "pass" ? "success-soft" : latest === "fail" ? "danger-soft" : "muted";
    const isRunning = activeSyntheticSuite === suite;
    return `
      <article class="legal-status-card admin-synthetic-card">
        <span class="legal-status-card__label">${escapeHtml(suite)}</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${renderBadge(latest, tone)}</strong>
        <span class="admin-user-cell__secondary">runs: ${escapeHtml(String(row.runs_total || 0))}, failed: ${escapeHtml(String(row.failed_total || 0))}</span>
        <span class="admin-user-cell__secondary admin-synthetic-card__description">${escapeHtml(suiteDescriptions[suite] || "")}</span>
        <button type="button" class="ghost-button" data-synthetic-run="${suite}" ${isRunning ? "disabled" : ""}>${isRunning ? "Запуск..." : "Запустить"}</button>
      </article>
    `;
  });
  const failedRuns = Array.isArray(summary?.runs)
    ? summary.runs.filter((item) => String(item?.status || "") !== "pass").slice(0, 5)
    : [];
  const failedHtml = failedRuns.length
    ? `<div class="legal-table-wrap"><table class="legal-table"><thead><tr><th>Suite</th><th>Run</th><th>Status</th><th>When</th></tr></thead><tbody>
      ${failedRuns
        .map(
          (item) => `<tr><td>${escapeHtml(String(item.suite || "-"))}</td><td>${escapeHtml(String(item.run_id || "-"))}</td><td>${escapeHtml(String(item.status || "-"))}</td><td>${escapeHtml(String(item.created_at || "-"))}</td></tr>`,
        )
        .join("")}
    </tbody></table></div>`
    : '<p class="legal-section__description">Падений synthetic suite не обнаружено.</p>';
  syntheticHost.innerHTML = `
    <div class="admin-performance-grid admin-synthetic-grid">${cards.join("")}</div>
    ${failedHtml}
  `;
}

async function runSyntheticSuite(suite) {
  const normalizedSuite = String(suite || "").trim().toLowerCase();
  if (!normalizedSuite || activeSyntheticSuite) {
    return;
  }
  activeSyntheticSuite = normalizedSuite;
  clearMessage();
  renderSynthetic({ by_suite: {} });
  try {
    const response = await apiFetch("/api/admin/synthetic/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        suite: normalizedSuite,
        trigger: "admin_ui",
      }),
    });
    const payload = await parsePayload(response);
    if (!response.ok) {
      setStateError(errorsHost, formatHttpError(response, payload, `Не удалось запустить synthetic suite ${normalizedSuite}.`));
      return;
    }
    showMessage(`Synthetic suite ${normalizedSuite} завершен: ${String(payload?.status || "unknown")}.`);
    await loadAdminOverview({ silent: true });
  } catch (error) {
    setStateError(errorsHost, error?.message || `Не удалось запустить synthetic suite ${normalizedSuite}.`);
  } finally {
    activeSyntheticSuite = "";
    await loadAdminOverview({ silent: true });
  }
}

function renderCostSummary(totals) {
  if (!costSummaryHost) {
    return;
  }
  const samples = Number(totals?.ai_estimated_cost_samples || 0);
  costSummaryHost.innerHTML = `
    <article class="legal-status-card">
      <span class="legal-status-card__label">AI cost (USD)</span>
      <strong class="legal-status-card__value legal-status-card__value--small">$${escapeHtml(formatUsd(totals?.ai_estimated_cost_total_usd || 0))}</strong>
      <span class="admin-user-cell__secondary">Сэмплов: ${escapeHtml(String(samples))}</span>
    </article>
    <article class="legal-status-card">
      <span class="legal-status-card__label">AI токены (in/out/total)</span>
      <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatNumber(totals?.ai_input_tokens_total || 0))} / ${escapeHtml(formatNumber(totals?.ai_output_tokens_total || 0))} / ${escapeHtml(formatNumber(totals?.ai_total_tokens_total || 0))}</strong>
      <span class="admin-user-cell__secondary">Генераций: ${escapeHtml(String(totals?.ai_generation_total || 0))}</span>
    </article>
  `;
}

function renderModelPolicy(policy) {
  if (!modelPolicyHost) {
    return;
  }

  const thresholds = Object.entries(policy?.kpi_thresholds || {});
  const autoActions = Array.isArray(policy?.auto_actions) ? policy.auto_actions : [];
  const rolloutConfig = policy?.cheap_model_rollout || {};
  const rolloutStages = Object.entries(rolloutConfig).filter(([key]) => key !== "immediate_rollback");
  const rollbackItems = Array.isArray(rolloutConfig.immediate_rollback) ? rolloutConfig.immediate_rollback : [];
  const defaults = policy?.recommended_defaults || {};
  const cadence = defaults?.review_cadence || {};
  const routing = policy?.model_routing || {};
  const checklist = policy?.daily_admin_checklist || {};

  if (!thresholds.length && !autoActions.length) {
    modelPolicyHost.innerHTML = '<p class="legal-section__description">Policy config is not loaded yet.</p>';
    return;
  }

  modelPolicyHost.innerHTML = `
    <div class="admin-performance-grid">
      <article class="legal-status-card">
        <span class="legal-status-card__label">Default tier</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(defaults.default_tier || "gpt-5.4-mini"))}</strong>
        <span class="admin-user-cell__secondary">Nano share: ${escapeHtml(String(defaults.nano_share_simple_cases || "n/a"))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Auto escalation</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(defaults.auto_escalation ?? false))}</strong>
        <span class="admin-user-cell__secondary">Manual model UI: ${escapeHtml(String(defaults.manual_model_selection_ui ?? false))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Review cadence</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(cadence.operational || "daily"))}</strong>
        <span class="admin-user-cell__secondary">Policy review: ${escapeHtml(String(cadence.policy || "weekly"))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Law QA routing</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(routing?.law_qa?.default_model || "gpt-5.4-mini"))}</strong>
        <span class="admin-user-cell__secondary">Low confidence: ${escapeHtml(String(routing?.law_qa?.low_confidence_model || "gpt-5.4"))}</span>
      </article>
    </div>
    <div class="legal-table-shell">
      <table class="legal-table admin-table admin-table--compact">
        <thead><tr><th>KPI</th><th>Green</th><th>Yellow</th><th>Red</th></tr></thead>
        <tbody>
          ${thresholds
            .map(
              ([metric, bands]) => `
                <tr>
                  <td>${escapeHtml(String(metric))}</td>
                  <td>${escapeHtml(String((bands || {}).green || "-"))}</td>
                  <td>${escapeHtml(String((bands || {}).yellow || "-"))}</td>
                  <td>${escapeHtml(String((bands || {}).red || "-"))}</td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
    <div class="legal-field-grid legal-field-grid--two">
      <article class="legal-subcard">
        <div class="legal-field__label">Auto actions</div>
        <ul class="legal-list">
          ${autoActions
            .map(
              (item) => `<li><strong>${escapeHtml(String(item.when || "-"))}</strong>: ${escapeHtml(String(item.action || "-"))} (${escapeHtml(String(item.duration || "-"))})</li>`,
            )
            .join("")}
        </ul>
      </article>
      <article class="legal-subcard">
        <div class="legal-field__label">Daily admin checklist</div>
        <ul class="legal-list">
          ${["quality", "cost", "stability", "drill_down"]
            .map((key) => {
              const values = Array.isArray(checklist?.[key]) ? checklist[key] : [];
              return values.map((item) => `<li>${escapeHtml(`${key}: ${String(item)}`)}</li>`).join("");
            })
            .join("")}
        </ul>
      </article>
      <article class="legal-subcard">
        <div class="legal-field__label">Cheap-tier rollout</div>
        <ul class="legal-list">
          ${rolloutStages
            .map(
              ([stage, meta]) => `<li><strong>${escapeHtml(String(stage))}</strong>: ${escapeHtml(String((meta || {}).traffic_share || "-"))}, ${escapeHtml(String((meta || {}).promote_when || "-"))}</li>`,
            )
            .join("")}
        </ul>
      </article>
      <article class="legal-subcard">
        <div class="legal-field__label">Immediate rollback</div>
        <ul class="legal-list">
          ${rollbackItems.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}
        </ul>
      </article>
    </div>
  `;
}

function renderAiPipeline(payload) {
  if (!aiPipelineHost) {
    return;
  }
  const summary = payload?.summary || {};
  const models = Object.entries(summary?.models || {});
  const feedback = Array.isArray(payload?.feedback) ? payload.feedback.slice(0, 8) : [];
  aiPipelineHost.innerHTML = `
    <div class="admin-performance-grid">
      <article class="legal-status-card">
        <span class="legal-status-card__label">Генерации</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(summary?.total_generations || 0))}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Оценка стоимости</span>
        <strong class="legal-status-card__value legal-status-card__value--small">$${escapeHtml(formatUsd(summary?.estimated_cost_total_usd || 0))}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">p95 latency</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(summary?.latency_ms_p95 ?? "—"))} ms</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Budget warnings</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(summary?.budget_warning_count || 0))}</strong>
      </article>
    </div>
    <div class="admin-section-toolbar">
      <span class="admin-user-cell__secondary">Модели: ${escapeHtml(models.map(([name, count]) => `${name} (${count})`).join(", ") || "нет данных")}</span>
    </div>
    ${
      feedback.length
        ? `
      <div class="legal-table-shell">
        <table class="legal-table admin-table admin-table--compact">
          <thead><tr><th>Когда</th><th>Flow</th><th>Issue</th><th>Комментарий</th></tr></thead>
          <tbody>
            ${feedback
              .map(
                (row) => `
                <tr>
                  <td>${escapeHtml(String(row.created_at || "—"))}</td>
                  <td>${escapeHtml(String((row.meta || {}).flow || "—"))}</td>
                  <td>${escapeHtml(String((row.meta || {}).issue_type || "—"))}</td>
                  <td>${escapeHtml(String((row.meta || {}).comment || "—"))}</td>
                </tr>
              `,
              )
              .join("")}
          </tbody>
        </table>
      </div>`
        : '<p class="legal-section__description">Нет обратной связи по AI-пайплайну.</p>'
    }
  `;
}

function renderAiPipeline(payload) {
  if (!aiPipelineHost) {
    return;
  }
  const summary = payload?.summary || {};
  const models = Object.entries(summary?.models || {});
  const feedback = Array.isArray(payload?.feedback) ? payload.feedback.slice(0, 8) : [];
  const quality = payload?.quality_summary || {};
  const flowSummaries = payload?.flow_summaries || {};
  const costTables = payload?.cost_tables || {};
  const topInaccurate = Array.isArray(payload?.top_inaccurate_generations) ? payload.top_inaccurate_generations : [];
  const policyActions = Array.isArray(payload?.policy_actions) ? payload.policy_actions : [];
  const modelCostRows = Array.isArray(costTables?.by_model) ? costTables.by_model : [];
  const flowCostRows = Array.isArray(costTables?.by_flow) ? costTables.by_flow : [];
  const issueCounts = quality?.issue_counts || {};
  const lawQaP95 = flowSummaries?.law_qa?.latency_ms_p95;
  const suggestP95 = flowSummaries?.suggest?.latency_ms_p95;
  const partialErrors = Array.isArray(payload?.partial_errors) ? payload.partial_errors : [];
  const partialErrorsSummary = partialErrors
    .slice(0, 3)
    .map((item) => {
      const source = String(item?.source || "unknown").trim();
      const message = String(item?.message || "Неизвестная ошибка").trim();
      return `${source}: ${message}`;
    })
    .join("; ");
  const formatQualityRate = (value, sampleLabel) => {
    if (value === null || value === undefined) {
      return `n/a (no ${sampleLabel} samples)%`;
    }
    return `${String(value)}%`;
  };

  aiPipelineHost.innerHTML = `
    ${
      partialErrors.length
        ? `<div class="legal-alert legal-alert--warning">AI Pipeline загружен частично (${escapeHtml(String(partialErrors.length))}). ${escapeHtml(partialErrorsSummary || "Подробности доступны в server logs.")}</div>`
        : ""
    }
    <div class="admin-performance-grid">
      <article class="legal-status-card">
        <span class="legal-status-card__label">Recent generations</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(summary?.total_generations || 0))}</strong>
        <span class="admin-user-cell__secondary">24h sample: ${escapeHtml(String(quality?.generation_samples || 0))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Estimated cost</span>
        <strong class="legal-status-card__value legal-status-card__value--small">$${escapeHtml(formatUsd(summary?.estimated_cost_total_usd || 0))}</strong>
        <span class="admin-user-cell__secondary">Samples: ${escapeHtml(String(summary?.estimated_cost_samples || 0))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">p95 latency</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(summary?.latency_ms_p95 ?? "-"))} ms</strong>
        <span class="admin-user-cell__secondary">law_qa: ${escapeHtml(String(lawQaP95 ?? "-"))} / suggest: ${escapeHtml(String(suggestP95 ?? "-"))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Fallback rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.fallback_rate, "generation"))}</strong>
        <span class="admin-user-cell__secondary">Budget warnings: ${escapeHtml(String(summary?.budget_warning_count || 0))}</span>
      </article>
    </div>
    <div class="admin-performance-grid">
      <article class="legal-status-card">
        <span class="legal-status-card__label">guard_fail_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.guard_fail_rate, "generation"))}</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.guard_fail_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">guard_warn_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.guard_warn_rate, "generation"))}</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.guard_warn_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">wrong_law_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.wrong_law_rate, "feedback"))}</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.wrong_law_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">hallucination_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.hallucination_rate, "feedback"))}</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.hallucination_rate)}</span>
      </article>
    </div>
    <div class="admin-performance-grid">
      <article class="legal-status-card">
        <span class="legal-status-card__label">wrong_fact_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.wrong_fact_rate, "feedback"))}</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.wrong_fact_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">unclear_answer_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.unclear_answer_rate, "feedback"))}</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.unclear_answer_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">validation_retry_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.validation_retry_rate, "generation"))}</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.validation_retry_rate)}</span>
      </article>
    </div>
    <div class="admin-performance-grid">
      <article class="legal-status-card">
        <span class="legal-status-card__label">new_fact_validation_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.new_fact_validation_rate, "generation"))}</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.new_fact_validation_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">unsupported_article_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.unsupported_article_rate, "generation"))}</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.unsupported_article_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">format_violation_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.format_violation_rate, "generation"))}</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.format_violation_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">safe_fallback_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.safe_fallback_rate, "generation"))}</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.safe_fallback_rate)}</span>
      </article>
    </div>
    <div class="admin-section-toolbar">
      <span class="admin-user-cell__secondary">Models: ${escapeHtml(models.map(([name, count]) => `${name} (${count})`).join(", ") || "no data")}</span>
    </div>
    <div class="legal-field-grid legal-field-grid--two">
      <article class="legal-subcard">
        <div class="legal-field__label">Accuracy taxonomy</div>
        <ul class="legal-list">
          <li>wrong_law: ${escapeHtml(String(issueCounts.wrong_law || 0))}</li>
          <li>wrong_fact: ${escapeHtml(String(issueCounts.wrong_fact || 0))}</li>
          <li>hallucination: ${escapeHtml(String(issueCounts.hallucination || 0))}</li>
          <li>unclear_answer: ${escapeHtml(String(issueCounts.unclear_answer || 0))}</li>
          <li>new_fact_detected: ${escapeHtml(String(issueCounts.new_fact_detected || 0))}</li>
          <li>unsupported_article_reference: ${escapeHtml(String(issueCounts.unsupported_article_reference || 0))}</li>
          <li>format_violation: ${escapeHtml(String(issueCounts.format_violation || 0))}</li>
        </ul>
      </article>
      <article class="legal-subcard">
        <div class="legal-field__label">Policy actions</div>
        <ul class="legal-list">
          ${policyActions.map((item) => `<li>${renderBandBadge(item.severity)} <strong>${escapeHtml(String(item.title || "-"))}</strong>: ${escapeHtml(String(item.reason || "-"))}</li>`).join("")}
        </ul>
      </article>
    </div>
    ${
      modelCostRows.length
        ? `
      <div class="legal-table-shell">
        <table class="legal-table admin-table admin-table--compact">
          <thead><tr><th>Model</th><th>Requests</th><th>Total cost</th><th>Avg cost</th><th>Total tokens</th></tr></thead>
          <tbody>
            ${modelCostRows.map((row) => `
                <tr>
                  <td>${escapeHtml(String(row.model || "-"))}</td>
                  <td>${escapeHtml(String(row.requests || 0))}</td>
                  <td>$${escapeHtml(formatUsd(row.estimated_cost_total_usd || 0))}</td>
                  <td>$${escapeHtml(formatUsd(row.avg_cost_per_request_usd || 0))}</td>
                  <td>${escapeHtml(formatNumber(row.total_tokens || 0))}</td>
                </tr>
              `).join("")}
          </tbody>
        </table>
      </div>`
        : ""
    }
    ${
      flowCostRows.length
        ? `
      <div class="legal-table-shell">
        <table class="legal-table admin-table admin-table--compact">
          <thead><tr><th>Flow</th><th>Requests</th><th>Total cost</th><th>Avg cost</th><th>Total tokens</th></tr></thead>
          <tbody>
            ${flowCostRows.map((row) => `
                <tr>
                  <td>${escapeHtml(String(row.flow || "-"))}</td>
                  <td>${escapeHtml(String(row.requests || 0))}</td>
                  <td>$${escapeHtml(formatUsd(row.estimated_cost_total_usd || 0))}</td>
                  <td>$${escapeHtml(formatUsd(row.avg_cost_per_request_usd || 0))}</td>
                  <td>${escapeHtml(formatNumber(row.total_tokens || 0))}</td>
                </tr>
              `).join("")}
          </tbody>
        </table>
      </div>`
        : ""
    }
    ${
      topInaccurate.length
        ? `
      <div class="legal-table-shell">
        <table class="legal-table admin-table admin-table--compact">
          <thead><tr><th>generation_id</th><th>Flow</th><th>Issues</th><th>Preview</th><th>Guard</th><th>Note</th></tr></thead>
          <tbody>
            ${topInaccurate.map((row) => `
                <tr>
                  <td>${escapeHtml(String(row.generation_id || "-"))}</td>
                  <td>${escapeHtml(String(row.flow || "-"))}</td>
                  <td>${escapeHtml(String((row.issues || []).join(", ") || "-"))}</td>
                  <td>${escapeHtml(String(row.output_preview || "-"))}</td>
                  <td>${escapeHtml(String(row.guard_status || "-"))}</td>
                  <td>${escapeHtml(String(row.note || "-"))}</td>
                </tr>
              `).join("")}
          </tbody>
        </table>
      </div>`
        : '<p class="legal-section__description">No inaccurate generations in the recent sample.</p>'
    }
    ${
      feedback.length
        ? `
      <div class="legal-table-shell">
        <table class="legal-table admin-table admin-table--compact">
          <thead><tr><th>When</th><th>Flow</th><th>Issues</th><th>Comment</th></tr></thead>
          <tbody>
            ${feedback.map((row) => `
                <tr>
                  <td>${escapeHtml(String(row.created_at || "-"))}</td>
                  <td>${escapeHtml(String((row.meta || {}).flow || "-"))}</td>
                  <td>${escapeHtml(String(((row.meta || {}).issues || []).join(", ") || "-"))}</td>
                  <td>${escapeHtml(String((row.meta || {}).note || "-"))}</td>
                </tr>
              `).join("")}
          </tbody>
        </table>
      </div>`
        : '<p class="legal-section__description">No feedback items in the recent sample.</p>'
    }
  `;
}

function renderRoleHistory(payload) {
  if (!roleHistoryHost) {
    return;
  }
  const items = Array.isArray(payload?.items) ? payload.items : [];
  if (!items.length) {
    roleHistoryHost.innerHTML = '<p class="legal-section__description">Изменений ролей пока нет.</p>';
    return;
  }
  roleHistoryHost.innerHTML = `
    <div class="legal-table-shell">
      <table class="legal-table admin-table admin-table--compact">
        <thead><tr><th>Когда</th><th>Админ</th><th>Действие</th><th>Пользователь</th></tr></thead>
        <tbody>
          ${items
            .slice(0, 20)
            .map(
              (item) => `
              <tr>
                <td>${escapeHtml(String(item.created_at || "—"))}</td>
                <td>${escapeHtml(String(item.username || "—"))}</td>
                <td>${escapeHtml(String(item.event_type || "—"))}</td>
                <td>${escapeHtml(String((item.meta || {}).target_username || "—"))}</td>
              </tr>
            `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function extractErrorMessage(payload, fallback) {
  const detail = payload?.detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item) => String(item || "").trim()).filter(Boolean).join(" ");
  }
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }
  if (typeof payload?.message === "string" && payload.message.trim()) {
    return payload.message.trim();
  }
  return fallback;
}

function formatHttpError(response, payload, fallback) {
  const status = Number(response?.status || 0);
  if (redirectIfUnauthorized?.(status)) {
    return "Требуется повторный вход в систему.";
  }

  const details = extractErrorMessage(payload, fallback);
  const requestId = String(response?.headers?.get?.("x-request-id") || "").trim();

  let prefix = "";
  if (status === 403) {
    prefix = "Доступ запрещен.";
  } else if (status === 429) {
    prefix = "Превышен лимит запросов.";
  } else if (status >= 500) {
    prefix = "Ошибка сервера.";
  } else if (status >= 400) {
    prefix = "Ошибка запроса.";
  }

  const parts = [];
  if (prefix) {
    parts.push(prefix);
  }
  parts.push(details);
  if (status > 0) {
    parts.push(`(HTTP ${status})`);
  }
  if (requestId) {
    parts.push(`[request_id: ${requestId}]`);
  }
  return parts.join(" ").trim();
}

function renderTopEndpoints(items) {
  if (!endpointsHost) {
    return;
  }
  if (!items.length) {
    endpointsHost.innerHTML = '<p class="legal-section__description">Пока нет данных по API-запросам.</p>';
    return;
  }

  endpointsHost.innerHTML = `
    <div class="legal-table-shell">
      <table class="legal-table admin-table admin-table--compact">
        <thead><tr><th>Эндпоинт</th><th>Что делает</th><th>Запросов</th></tr></thead>
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
    examImportHost.innerHTML = '<p class="legal-section__description">Пока нет данных по импорту экзаменов.</p>';
    return;
  }

  const lastSync = summary.last_sync || {};
  const lastScore = summary.last_score || {};
  const recentFailures = [...(summary.recent_failures || []), ...(summary.recent_row_failures || [])];
  const recentEntries = Array.isArray(summary.recent_entries) ? summary.recent_entries : [];
  const failedEntries = Array.isArray(summary.failed_entries) ? summary.failed_entries : [];

  examImportHost.innerHTML = `
    <div class="admin-exam-grid">
      <article class="legal-status-card">
        <span class="legal-status-card__label">Ожидают оценивания</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(summary.pending_scores || 0))}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Последняя синхронизация</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(lastSync.created_at || "—")}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Последнее оценивание</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(lastScore.created_at || "—")}</strong>
      </article>
    </div>
    <div class="admin-exam-meta">
      <div class="admin-user-cell">
        <strong>${escapeHtml(lastSync.path || "/api/exam-import/sync")}</strong>
        <span class="admin-user-cell__secondary">${escapeHtml(lastSync.status_code ? `Статус ${lastSync.status_code}` : "Запусков пока не было")}</span>
      </div>
      <div class="admin-user-cell">
        <strong>${escapeHtml(lastScore.path || "/api/exam-import/score")}</strong>
        <span class="admin-user-cell__secondary">${escapeHtml(lastScore.status_code ? `Статус ${lastScore.status_code}` : "Проверок пока не было")}</span>
      </div>
    </div>
    ${renderAdminExamEntriesSection({
      title: "Последние ответы и оценки",
      description: "Последние импортированные строки с текущим баллом, статусом и быстрым переходом к детальному разбору.",
      entries: recentEntries,
      emptyText: "Пока нет строк, которые можно показать в админке.",
    })}
    ${renderAdminExamEntriesSection({
      title: "Нуждаются в перепроверке",
      description: "Строки, где у ответов остались некорректные или неполные результаты проверки.",
      entries: failedEntries,
      emptyText: "Строк, требующих перепроверки, сейчас нет.",
      emphasizeFailed: true,
    })}
    ${
      recentFailures.length
        ? `
          <div class="legal-table-shell">
            <table class="legal-table admin-table admin-table--compact">
              <thead>
                <tr><th>Время</th><th>Тип</th><th>Путь</th><th>Что случилось</th></tr>
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
        : '<p class="legal-section__description">Последних ошибок импорта экзаменов и AI-оценивания не найдено.</p>'
    }
  `;
}

function getExamEntryStatus(entry) {
  if (ExamView?.getEntryStatus) {
    return ExamView.getEntryStatus(entry);
  }
  const average = Number(entry?.average_score);
  if (entry?.average_score == null || Number.isNaN(average)) {
    return { key: "pending", label: "Ожидает оценки", tone: "pending" };
  }
  if (average >= 73) {
    return { key: "good", label: "Сдан хорошо", tone: "ok" };
  }
  if (average > 55) {
    return { key: "medium", label: "Сдан на среднем уровне", tone: "warn" };
  }
  return { key: "poor", label: "Сдан слабо", tone: "problem" };
}

function formatExamAverage(entry) {
  if (ExamView?.formatAverage) {
    return ExamView.formatAverage(entry);
  }
  return entry?.average_score != null ? `${entry.average_score} / 100` : "—";
}

function renderAdminExamEntriesSection({ title, description, entries, emptyText, emphasizeFailed = false }) {
  if (!Array.isArray(entries) || !entries.length) {
    return `
      <div class="legal-subcard admin-user-detail-card">
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">${escapeHtml(title)}</span>
            <p class="legal-section__description">${escapeHtml(description)}</p>
          </div>
        </div>
        <p class="legal-section__description">${escapeHtml(emptyText)}</p>
      </div>
    `;
  }

  return `
    <section class="legal-subcard admin-user-detail-card">
      <div class="legal-subcard__header">
        <div>
          <span class="legal-field__label">${escapeHtml(title)}</span>
          <p class="legal-section__description">${escapeHtml(description)}</p>
        </div>
      </div>
      <div class="legal-table-shell">
        <table class="legal-table admin-table admin-table--compact">
          <thead>
            <tr>
              <th>Строка</th>
              <th>Кандидат</th>
              <th>Формат</th>
              <th>Балл</th>
              <th>Статус</th>
              <th>Ответов</th>
              <th>Импорт</th>
              <th>Действие</th>
            </tr>
          </thead>
          <tbody>
            ${entries
              .map((entry) => {
                const status = getExamEntryStatus(entry);
                const reviewBadge = emphasizeFailed || entry?.needs_rescore
                  ? renderBadge("Нужна перепроверка", "danger")
                  : "";
                return `
                  <tr>
                    <td>${escapeHtml(entry.source_row ?? "—")}</td>
                    <td>
                      <div class="admin-user-cell">
                        <strong class="admin-user-cell__name">${escapeHtml(entry.full_name || "—")}</strong>
                        <span class="admin-user-cell__secondary">${escapeHtml(entry.discord_tag || "—")}</span>
                      </div>
                    </td>
                    <td>${escapeHtml(entry.exam_format || "—")}</td>
                    <td>${escapeHtml(formatExamAverage(entry))}</td>
                    <td>
                      <div class="admin-badge-row">
                        <span class="exam-status-badge exam-status-badge--${escapeHtml(status.tone)}">${escapeHtml(status.label)}</span>
                        ${reviewBadge}
                      </div>
                    </td>
                    <td>${escapeHtml(String(entry.answer_count ?? 0))}</td>
                    <td>${escapeHtml(entry.imported_at || "—")}</td>
                    <td>
                      <button
                        type="button"
                        class="ghost-button admin-exam-detail-btn"
                        data-exam-source-row="${escapeHtml(entry.source_row ?? "")}"
                      >
                        Разбор
                      </button>
                    </td>
                  </tr>
                `;
              })
              .join("")}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function renderActiveFilters(filters) {
  if (!activeFiltersHost) {
    return;
  }

  const chips = [];
  if (filters.search) chips.push(renderFilterChip(`Пользователь: ${filters.search}`, "search"));
  if (filters.user_sort && filters.user_sort !== "complaints") {
    const sortLabels = {
      api_requests: "Сортировка: API-активность",
      last_seen: "Сортировка: последняя активность",
      created_at: "Сортировка: дата регистрации",
      username: "Сортировка: username",
    };
    chips.push(renderFilterChip(sortLabels[filters.user_sort] || `Сортировка: ${filters.user_sort}`, "user_sort"));
  }
  if (filters.blocked_only) chips.push(renderFilterChip("Только заблокированные", "blocked_only"));
  if (filters.tester_only) chips.push(renderFilterChip("Только тестеры", "tester_only"));
  if (filters.gka_only) chips.push(renderFilterChip("Только ГКА-ЗГКА", "gka_only"));
  if (filters.unverified_only) chips.push(renderFilterChip("Только без подтверждения email", "unverified_only"));
  if (filters.event_search) chips.push(renderFilterChip(`События: ${filters.event_search}`, "event_search"));
  if (filters.event_type) chips.push(renderFilterChip(`Тип: ${filters.event_type}`, "event_type"));
  if (filters.failed_events_only) chips.push(renderFilterChip("Только ошибки", "failed_events_only"));

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
    user.email_verified ? renderBadge("Email OK", "success") : renderBadge("Email не подтвержден", "muted"),
    user.access_blocked ? renderBadge("Заблокирован", "danger") : renderBadge("Активен", "success-soft"),
    user.deactivated_at ? renderBadge("Деактивирован", "danger") : null,
    user.is_tester ? renderBadge("Тестер", "info") : renderBadge("Обычный", "neutral"),
    user.is_gka ? renderBadge("ГКА-ЗГКА", "info") : null,
    Number(user.api_quota_daily || 0) > 0 ? renderBadge(`Квота/день: ${Number(user.api_quota_daily || 0)}`, "info") : renderBadge("Квота: без лимита", "muted"),
    riskLabel(user),
  ];
  return `<div class="admin-badge-row">${badges.filter(Boolean).join("")}</div>`;
}

function renderUserActivity(user) {
  return `
    <div class="admin-activity">
      <div class="admin-activity__main">
        <strong>${escapeHtml(String(user.complaints || 0))}</strong><span>жалоб</span>
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
  if (!usersHost) {
    return;
  }
  userIndex.clear();
  users.forEach((user) => {
    userIndex.set(String(user.username || "").toLowerCase(), user);
  });

  if (!users.length) {
    usersHost.innerHTML = '<p class="legal-section__description">По текущему фильтру пользователи не найдены.</p>';
    return;
  }

  usersHost.innerHTML = `
    <div class="admin-section-toolbar">
      <p class="legal-section__description">Показано пользователей: ${escapeHtml(String(users.length))}. Сортировка: ${escapeHtml(String(userSort))}</p>
    </div>
    <div class="admin-section-toolbar">
      <label class="legal-field">
        <span class="legal-field__label">Массовое действие</span>
        <select id="admin-bulk-action">
          <option value="">Выберите действие</option>
          <option value="verify_email">Подтвердить email</option>
          <option value="block">Заблокировать</option>
          <option value="unblock">Разблокировать</option>
          <option value="grant_tester">Выдать тестера</option>
          <option value="revoke_tester">Снять тестера</option>
          <option value="grant_gka">Выдать ГКА-ЗГКА</option>
          <option value="revoke_gka">Снять ГКА-ЗГКА</option>
          <option value="deactivate">Деактивировать</option>
          <option value="reactivate">Реактивировать</option>
          <option value="set_daily_quota">Установить квоту/день</option>
        </select>
      </label>
      <input id="admin-bulk-reason" type="text" placeholder="Причина (для block/deactivate)">
      <input id="admin-bulk-quota" type="number" min="0" step="1" placeholder="Квота/день (для quota)">
      <button type="button" id="admin-bulk-run" class="ghost-button">Запустить в очереди</button>
      <span id="admin-bulk-status" class="admin-badge admin-badge--muted">Выбрано: ${selectedBulkUsers.size}</span>
    </div>
    <div class="legal-table-shell">
      <table class="legal-table admin-table">
        <thead>
          <tr>
            <th><input type="checkbox" id="admin-users-select-all"></th>
            <th>Пользователь</th>
            <th>Статусы</th>
            <th>Активность</th>
            <th>Последняя активность</th>
            <th>Управление</th>
          </tr>
        </thead>
        <tbody>
          ${users
            .map(
              (user) => `
                <tr class="admin-user-row">
                  <td><input type="checkbox" data-bulk-user="${escapeHtml(user.username || "")}" ${selectedBulkUsers.has(String(user.username || "").toLowerCase()) ? "checked" : ""}></td>
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
                      <strong>${escapeHtml(user.last_seen_at || "—")}</strong>
                      <span class="admin-user-cell__secondary">${escapeHtml(user.access_blocked_reason || "Без причины блокировки")}</span>
                    </div>
                  </td>
                  <td>
                    <button type="button" class="secondary-button admin-user-open-btn" data-open-user="${escapeHtml(user.username || "")}">Управление</button>
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
  if (!eventsHost) {
    return;
  }
  if (!events.length) {
    eventsHost.innerHTML = '<p class="legal-section__description">Событий по текущему фильтру нет.</p>';
    return;
  }

  eventsHost.innerHTML = `
    <div class="admin-section-toolbar">
      <p class="legal-section__description">Показано событий: ${escapeHtml(String(events.length))}</p>
    </div>
    <div class="legal-table-shell">
      <table class="legal-table admin-table admin-table--compact">
        <thead>
          <tr>
            <th>Время</th>
            <th>Пользователь</th>
            <th>Тип</th>
            <th>Путь</th>
            <th>Статус</th>
            <th>ms</th>
            <th>Ресурсы</th>
          </tr>
        </thead>
        <tbody>
          ${events
            .map((event) => {
              const statusValue = event.status_code ?? "—";
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

function renderErrorExplorer(payload) {
  if (!errorExplorerHost) {
    return;
  }
  const items = Array.isArray(payload?.items) ? payload.items : [];
  const byType = Array.isArray(payload?.by_event_type) ? payload.by_event_type : [];
  const byPath = Array.isArray(payload?.by_path) ? payload.by_path : [];

  if (!items.length) {
    errorExplorerHost.innerHTML = '<p class="legal-section__description">Ошибок по текущему фильтру не найдено.</p>';
    return;
  }

  const topTypeText = byType.slice(0, 3).map((item) => `${item.event_type}: ${item.count}`).join(" · ");
  const topPathText = byPath.slice(0, 3).map((item) => `${item.path}: ${item.count}`).join(" · ");

  errorExplorerHost.innerHTML = `
    <div class="admin-section-toolbar">
      <p class="legal-section__description">
        Ошибок: ${escapeHtml(String(payload?.total || items.length))}
      </p>
      <p class="legal-section__description">
        Топ типов: ${escapeHtml(topTypeText || "—")}
      </p>
      <p class="legal-section__description">
        Топ endpoint: ${escapeHtml(topPathText || "—")}
      </p>
    </div>
    <div class="legal-table-shell">
      <table class="legal-table admin-table admin-table--compact">
        <thead>
          <tr>
            <th>Время</th>
            <th>Тип</th>
            <th>Endpoint</th>
            <th>HTTP</th>
            <th>Ошибка</th>
            <th>request_id</th>
          </tr>
        </thead>
        <tbody>
          ${items
            .map((event) => {
              const meta = event.meta || {};
              const errorText = String(meta.error_message || meta.error_type || "-");
              const requestId = String(meta.request_id || "-");
              return `
                <tr>
                  <td>${escapeHtml(event.created_at || "-")}</td>
                  <td>${renderBadge(event.event_type || "-", "danger")}</td>
                  <td class="admin-table__path" title="${escapeHtml(event.path || "-")}">${escapeHtml(event.path || "-")}</td>
                  <td>${renderBadge(String(event.status_code ?? "-"), "danger")}</td>
                  <td title="${escapeHtml(errorText)}">${escapeHtml(errorText)}</td>
                  <td title="${escapeHtml(requestId)}">${escapeHtml(requestId)}</td>
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
    adminEventsHost.innerHTML = '<p class="legal-section__description">Админ-действий по текущему фильтру пока не видно.</p>';
    return;
  }

  adminEventsHost.innerHTML = `
    <div class="admin-section-toolbar">
      <p class="legal-section__description">Показано админ-действий: ${escapeHtml(String(adminEvents.length))}</p>
    </div>
    <div class="legal-table-shell">
      <table class="legal-table admin-table admin-table--compact">
        <thead>
          <tr>
            <th>Время</th>
            <th>Администратор</th>
            <th>Действие</th>
            <th>Запрос</th>
            <th>Статус</th>
          </tr>
        </thead>
        <tbody>
          ${adminEvents
            .map((event) => {
              const statusValue = event.status_code ?? "—";
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
  if (userModalTitle) {
    userModalTitle.textContent = DEFAULT_USER_MODAL_TITLE;
  }

  userModalBody.innerHTML = `
    <div class="legal-status-row legal-status-row--three">
      <article class="legal-status-card">
        <span class="legal-status-card__label">Пользователь</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(user.username || "-")}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Email</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(user.email || "-")}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Последняя активность</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(user.last_seen_at || "—")}</strong>
      </article>
    </div>

    <div class="legal-subcard admin-user-detail-card">
      <div class="legal-subcard__header">
        <div>
          <span class="legal-field__label">Статусы</span>
          <p class="legal-section__description">Ключевые флаги и причина блокировки.</p>
        </div>
      </div>
      ${renderUserStatuses(user)}
      <div class="admin-user-detail-grid">
        <div><span class="legal-field__label">Причина блокировки</span><div class="admin-user-detail-text">${escapeHtml(user.access_blocked_reason || "Не указана")}</div></div>
        <div><span class="legal-field__label">Создан</span><div class="admin-user-detail-text">${escapeHtml(user.created_at || "—")}</div></div>
      </div>
    </div>

    <div class="legal-subcard admin-user-detail-card">
      <div class="legal-subcard__header">
        <div>
          <span class="legal-field__label">Активность</span>
          <p class="legal-section__description">Краткая сводка по действиям пользователя.</p>
        </div>
      </div>
      <div class="admin-user-summary-grid">
        <article class="legal-status-card"><span class="legal-status-card__label">Жалобы</span><strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(user.complaints || 0))}</strong></article>
        <article class="legal-status-card"><span class="legal-status-card__label">Rehab</span><strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(user.rehabs || 0))}</strong></article>
        <article class="legal-status-card"><span class="legal-status-card__label">AI</span><strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String((user.ai_suggestions || 0) + (user.ai_ocr_requests || 0)))}</strong></article>
        <article class="legal-status-card"><span class="legal-status-card__label">API</span><strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(user.api_requests || 0))}</strong></article>
        <article class="legal-status-card"><span class="legal-status-card__label">Ресурсы</span><strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(user.resource_units || 0))}</strong></article>
      </div>
    </div>

    <div class="legal-subcard admin-user-detail-card">
      <div class="legal-subcard__header">
        <div>
          <span class="legal-field__label">Быстрые действия</span>
          <p class="legal-section__description">Управление доступом и учетной записью пользователя.</p>
        </div>
      </div>
      <div class="admin-user-actions">
        <button type="button" class="ghost-button" data-verify-email="${escapeHtml(user.username || "")}">Подтвердить email</button>
        <button type="button" class="ghost-button" data-change-email="${escapeHtml(user.username || "")}" data-current-email="${escapeHtml(user.email || "")}">Сменить email</button>
        <button type="button" class="ghost-button" data-reset-password="${escapeHtml(user.username || "")}">Сбросить пароль</button>
        <button type="button" class="ghost-button" data-set-quota="${escapeHtml(user.username || "")}" data-current-quota="${escapeHtml(String(user.api_quota_daily || 0))}">Квота API/день</button>
        ${
          user.is_tester
            ? `<button type="button" class="ghost-button" data-revoke-tester="${escapeHtml(user.username || "")}">Снять тестера</button>`
            : `<button type="button" class="ghost-button" data-grant-tester="${escapeHtml(user.username || "")}">Выдать тестера</button>`
        }
        ${
          user.is_gka
            ? `<button type="button" class="ghost-button" data-revoke-gka="${escapeHtml(user.username || "")}">Снять ГКА-ЗГКА</button>`
            : `<button type="button" class="ghost-button" data-grant-gka="${escapeHtml(user.username || "")}">Выдать ГКА-ЗГКА</button>`
        }
        ${
          user.deactivated_at
            ? `<button type="button" class="ghost-button" data-reactivate-user="${escapeHtml(user.username || "")}">Реактивировать</button>`
            : `<button type="button" class="ghost-button" data-deactivate-user="${escapeHtml(user.username || "")}">Деактивировать</button>`
        }
        ${
          user.access_blocked
            ? `<button type="button" class="ghost-button" data-unblock-user="${escapeHtml(user.username || "")}">Разблокировать</button>`
            : `<button type="button" class="ghost-button" data-block-user="${escapeHtml(user.username || "")}">Заблокировать</button>`
        }
      </div>
    </div>
  `;
}

function renderExamEntryDetailModal(entry) {
  if (!userModalBody || !entry) {
    return;
  }
  if (userModalTitle) {
    userModalTitle.textContent = `Разбор ответа · строка ${entry.source_row || "—"}`;
  }

  userModalBody.innerHTML = `
    <div class="legal-status-row legal-status-row--three">
      <article class="legal-status-card">
        <span class="legal-status-card__label">Строка</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(entry.source_row || "—"))}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Кандидат</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(entry.full_name || "—")}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Средний балл</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatExamAverage(entry))}</strong>
      </article>
    </div>

    <div class="legal-status-row legal-status-row--three">
      <article class="legal-status-card">
        <span class="legal-status-card__label">Формат</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(entry.exam_format || "—")}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Ответов</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(entry.answer_count || 0))}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Обновлено</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(entry.updated_at || entry.imported_at || "—")}</strong>
      </article>
    </div>

    <div id="admin-exam-detail-score" class="legal-subcard" hidden></div>

    <section class="legal-subcard admin-user-detail-card">
      <div class="legal-subcard__header">
        <div>
          <span class="legal-field__label">Исходные поля строки</span>
          <p class="legal-section__description">Ниже видно, какие данные пришли из таблицы и с чем сравнивалась проверка.</p>
        </div>
      </div>
      <div class="legal-table-shell exam-detail-shell exam-detail-shell--payload">
        <table class="legal-table admin-table admin-table--compact exam-detail-table exam-detail-table--payload">
          <thead>
            <tr>
              <th>Столбец / Поле</th>
              <th>Значение</th>
            </tr>
          </thead>
          <tbody id="admin-exam-detail-body">
            <tr>
              <td colspan="2" class="legal-table__empty">Данные строки загружены.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  `;

  const scoreHost = document.getElementById("admin-exam-detail-score");
  const payloadHost = document.getElementById("admin-exam-detail-body");
  if (ExamView?.renderScoreTable) {
    ExamView.renderScoreTable(scoreHost, entry.exam_scores || [], formatExamAverage(entry), escapeHtml);
  }
  if (ExamView?.renderPayloadTable) {
    ExamView.renderPayloadTable(payloadHost, entry.payload || {}, escapeHtml);
  }
}

async function openExamEntryDetail(sourceRow) {
  const normalizedSourceRow = Number(sourceRow);
  if (!Number.isFinite(normalizedSourceRow) || normalizedSourceRow <= 0) {
    setStateError(errorsHost, "Не удалось определить строку экзамена для разбора.");
    return;
  }

  try {
    const response = await apiFetch(`/api/exam-import/rows/${encodeURIComponent(normalizedSourceRow)}`);
    const payload = await parsePayload(response);
    if (!response.ok) {
      setStateError(errorsHost, formatHttpError(response, payload, "Не удалось загрузить разбор ответа."));
      return;
    }
    selectedUser = null;
    renderExamEntryDetailModal(payload);
    userModal.open();
  } catch (error) {
    setStateError(errorsHost, error?.message || "Не удалось загрузить разбор ответа.");
  }
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

async function loadAiPipeline({ silent = false } = {}) {
  if (!aiPipelineHost) {
    return;
  }
  if (!silent) {
    renderLoadingState(aiPipelineHost, { count: 3, compact: true });
  }
  try {
    const response = await apiFetch("/api/admin/ai-pipeline?limit=50");
    const payload = await parsePayload(response);
    if (!response.ok) {
      if (!silent) {
        setStateError(errorsHost, formatHttpError(response, payload, "Не удалось загрузить AI Pipeline."));
      }
      return;
    }
    renderAiPipeline(payload);
    const partialErrors = Array.isArray(payload?.partial_errors) ? payload.partial_errors : [];
    if (partialErrors.length && !silent) {
      const first = partialErrors[0] || {};
      const source = first.source ? `[${String(first.source)}] ` : "";
      const message = String(first.message || "").trim();
      setStateError(errorsHost, `AI Pipeline загружен частично (${partialErrors.length}). ${source}${message}`.trim());
    }
  } catch (error) {
    if (!silent) {
      setStateError(errorsHost, error?.message || "Не удалось загрузить AI Pipeline.");
    }
  }
}

async function loadRoleHistory({ silent = false } = {}) {
  if (!roleHistoryHost) {
    return;
  }
  if (!silent) {
    renderLoadingState(roleHistoryHost, { count: 3, compact: true });
  }
  try {
    const response = await apiFetch("/api/admin/role-history?limit=100");
    const payload = await parsePayload(response);
    if (!response.ok) {
      if (!silent) {
        setStateError(errorsHost, formatHttpError(response, payload, "Не удалось загрузить историю ролей."));
      }
      return;
    }
    renderRoleHistory(payload);
  } catch (error) {
    if (!silent) {
      setStateError(errorsHost, error?.message || "Не удалось загрузить историю ролей.");
    }
  }
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
        setStateError(errorsHost, formatHttpError(response, payload, "Не удалось загрузить метрики производительности."));
      }
      return;
    }
    const payload = await parsePayload(response);
    renderPerformance(payload);
  } catch (error) {
    if (!silent) {
      setStateError(errorsHost, error?.message || "Не удалось загрузить метрики производительности.");
    }
  }
}

async function loadAdminOverview({ silent = false } = {}) {
  if (!silent) {
    setStateIdle(errorsHost);
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
        setStateError(errorsHost, formatHttpError(response, payload, "Не удалось загрузить данные админ-панели."));
      } else {
        setLiveStatus("Live: ошибка обновления", "danger");
      }
      return;
    }

    const payload = await parsePayload(response);
    renderActiveFilters(currentFilters());
    renderTotals(payload.totals || {});
    renderModelPolicy(payload.model_policy || {});
    renderCostSummary(payload.totals || {});
    renderExamImport(payload.exam_import || null);
    renderTopEndpoints(payload.top_endpoints || []);
    renderSynthetic(payload.synthetic || {});
    renderUsers(payload.users || [], payload.filters?.user_sort || "complaints");
    renderErrorExplorer(payload.error_explorer || null);
    renderAdminAudit(payload.recent_events || []);
    renderEvents(payload.recent_events || []);
    const partialErrors = Array.isArray(payload.partial_errors) ? payload.partial_errors : [];
    if (partialErrors.length && !silent) {
      const first = partialErrors[0] || {};
      const source = first.source ? `[${String(first.source)}] ` : "";
      const message = String(first.message || "").trim();
      setStateError(errorsHost, `Панель загружена частично (${partialErrors.length}). ${source}${message}`.trim());
    }

    if (selectedUser && userIndex.has(String(selectedUser).toLowerCase())) {
      renderUserModal(userIndex.get(String(selectedUser).toLowerCase()));
    }
    if (silent) {
      setLiveStatus(`Live: синхронно ${new Date().toLocaleTimeString("ru-RU")}`, "success-soft");
    }
  } catch (error) {
    if (!silent) {
      setStateError(errorsHost, error?.message || "Не удалось загрузить данные админ-панели.");
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
      loadAiPipeline({ silent: true }),
      loadRoleHistory({ silent: true }),
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
  setStateIdle(errorsHost);
  clearMessage();
  try {
    const response = await apiFetch(url, {
      method: "POST",
      body: body ? JSON.stringify(body) : null,
    });
    if (!response.ok) {
      const payload = await parsePayload(response);
      setStateError(errorsHost, formatHttpError(response, payload, "Не удалось выполнить действие администратора."));
      return;
    }
    showMessage(successText);
    await loadAdminOverview();
  } catch (error) {
    setStateError(errorsHost, error?.message || "Не удалось выполнить действие администратора.");
  }
}

async function pollBulkTask(taskId) {
  const statusHost = document.getElementById("admin-bulk-status");
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const response = await apiFetch(`/api/admin/tasks/${encodeURIComponent(taskId)}`);
    const payload = await parsePayload(response);
    if (!response.ok) {
      setStateError(errorsHost, formatHttpError(response, payload, "Не удалось получить статус bulk-задачи."));
      return;
    }
    const progress = payload.progress || {};
    if (statusHost) {
      statusHost.textContent = `Bulk: ${payload.status} (${progress.done || 0}/${progress.total || 0})`;
    }
    if (payload.status === "finished") {
      showMessage(`Bulk завершен: ok ${payload.result?.success_count || 0}, ошибок ${payload.result?.failed_count || 0}.`);
      selectedBulkUsers = new Set();
      await loadAdminOverview();
      return;
    }
    if (payload.status === "failed") {
      setStateError(errorsHost, payload.error || "Bulk-задача завершилась ошибкой.");
      return;
    }
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  setStateError(errorsHost, "Таймаут ожидания bulk-задачи.");
}

async function runBulkAction() {
  const usernames = Array.from(selectedBulkUsers);
  if (!usernames.length) {
    setStateError(errorsHost, "Выберите хотя бы одного пользователя для массовой операции.");
    return;
  }
  const action = String(document.getElementById("admin-bulk-action")?.value || "").trim();
  if (!action) {
    setStateError(errorsHost, "Выберите массовое действие.");
    return;
  }
  const reason = String(document.getElementById("admin-bulk-reason")?.value || "").trim();
  const quotaRaw = String(document.getElementById("admin-bulk-quota")?.value || "").trim();
  const daily_limit = quotaRaw ? Number(quotaRaw) : null;

  const response = await apiFetch("/api/admin/users/bulk-actions", {
    method: "POST",
    body: JSON.stringify({ usernames, action, reason, daily_limit, run_async: true }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось запустить bulk-операцию."));
    return;
  }
  showMessage("Bulk-задача добавлена в очередь.");
  await pollBulkTask(payload.task_id);
}

async function handleAdminAction(target) {
  const verifyUsername = target.getAttribute("data-verify-email");
  if (verifyUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(verifyUsername)}/verify-email`, "Email пользователя подтвержден администратором.");
    return true;
  }

  const unblockUsername = target.getAttribute("data-unblock-user");
  if (unblockUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(unblockUsername)}/unblock`, "Доступ пользователя восстановлен.");
    return true;
  }

  const blockUsername = target.getAttribute("data-block-user");
  if (blockUsername) {
    openActionModal({
      action: "block-user",
      username: blockUsername,
      askReason: true,
      title: "Блокировка пользователя",
      description: `Вы блокируете пользователя ${blockUsername}. При необходимости укажите причину.`,
      confirmLabel: "Заблокировать",
    });
    return true;
  }

  const grantTesterUsername = target.getAttribute("data-grant-tester");
  if (grantTesterUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(grantTesterUsername)}/grant-tester`, "Статус тестера выдан.");
    return true;
  }

  const revokeTesterUsername = target.getAttribute("data-revoke-tester");
  if (revokeTesterUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(revokeTesterUsername)}/revoke-tester`, "Статус тестера снят.");
    return true;
  }

  const grantGkaUsername = target.getAttribute("data-grant-gka");
  if (grantGkaUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(grantGkaUsername)}/grant-gka`, "Тип ГКА-ЗГКА присвоен.");
    return true;
  }

  const revokeGkaUsername = target.getAttribute("data-revoke-gka");
  if (revokeGkaUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(revokeGkaUsername)}/revoke-gka`, "Тип ГКА-ЗГКА снят.");
    return true;
  }

  const changeEmailUsername = target.getAttribute("data-change-email");
  if (changeEmailUsername) {
    openActionModal({
      action: "change-email",
      username: changeEmailUsername,
      askEmail: true,
      defaultEmail: target.getAttribute("data-current-email") || "",
      title: "Смена email",
      description: `Укажите новый email для пользователя ${changeEmailUsername}.`,
      confirmLabel: "Сохранить email",
    });
    return true;
  }

  const resetPasswordUsername = target.getAttribute("data-reset-password");
  if (resetPasswordUsername) {
    openActionModal({
      action: "reset-password",
      username: resetPasswordUsername,
      askPassword: true,
      title: "Сброс пароля",
      description: `Введите новый пароль для пользователя ${resetPasswordUsername}.`,
      confirmLabel: "Сменить пароль",
    });
    return true;
  }

  const deactivateUsername = target.getAttribute("data-deactivate-user");
  if (deactivateUsername) {
    openActionModal({
      action: "deactivate-user",
      username: deactivateUsername,
      askReason: true,
      title: "Деактивация аккаунта",
      description: `Пользователь ${deactivateUsername} будет деактивирован (soft-delete).`,
      confirmLabel: "Деактивировать",
    });
    return true;
  }

  const reactivateUsername = target.getAttribute("data-reactivate-user");
  if (reactivateUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(reactivateUsername)}/reactivate`, "Аккаунт реактивирован.");
    return true;
  }

  const setQuotaUsername = target.getAttribute("data-set-quota");
  if (setQuotaUsername) {
    openActionModal({
      action: "set-daily-quota",
      username: setQuotaUsername,
      askQuota: true,
      defaultQuota: target.getAttribute("data-current-quota") || "0",
      title: "Суточная квота API",
      description: `Установите лимит API запросов в сутки для ${setQuotaUsername} (0 = без лимита).`,
      confirmLabel: "Сохранить квоту",
    });
    return true;
  }

  return false;
}

async function submitPendingAction() {
  if (!pendingAction) {
    return;
  }
  setStateIdle(actionModalErrors);
  const action = pendingAction.action;
  const username = String(pendingAction.username || "");

  if (action === "block-user") {
    const reason = String(actionReasonInput?.value || "").trim();
    await performAdminAction(`/api/admin/users/${encodeURIComponent(username)}/block`, "Доступ пользователя заблокирован.", {
      reason,
    });
    closeActionModal();
    return;
  }

  if (action === "change-email") {
    const email = String(actionEmailInput?.value || "").trim();
    if (!email) {
      setStateError(actionModalErrors, "Укажите новый email.");
      return;
    }
    await performAdminAction(`/api/admin/users/${encodeURIComponent(username)}/email`, "Email пользователя обновлен.", {
      email,
    });
    closeActionModal();
    return;
  }

  if (action === "reset-password") {
    const password = String(actionPasswordInput?.value || "").trim();
    if (!password) {
      setStateError(actionModalErrors, "Введите новый пароль.");
      return;
    }
    if (password.length < 10) {
      setStateError(actionModalErrors, "Пароль должен быть не короче 10 символов.");
      return;
    }
    await performAdminAction(
      `/api/admin/users/${encodeURIComponent(username)}/reset-password`,
      "Пароль пользователя обновлен.",
      { password },
    );
    closeActionModal();
    return;
  }

  if (action === "deactivate-user") {
    const reason = String(actionReasonInput?.value || "").trim();
    await performAdminAction(`/api/admin/users/${encodeURIComponent(username)}/deactivate`, "Аккаунт пользователя деактивирован.", {
      reason,
    });
    closeActionModal();
    return;
  }

  if (action === "set-daily-quota") {
    const quota = Number(actionQuotaInput?.value || 0);
    if (!Number.isFinite(quota) || quota < 0) {
      setStateError(actionModalErrors, "Квота должна быть неотрицательным числом.");
      return;
    }
    await performAdminAction(`/api/admin/users/${encodeURIComponent(username)}/daily-quota`, "Квота обновлена.", {
      daily_limit: quota,
    });
    closeActionModal();
  }
}

usersHost?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }

  const openUser = target.getAttribute("data-open-user");
  if (openUser) {
    openUserModal(openUser);
    return;
  }
  if (target.id === "admin-bulk-run") {
    await runBulkAction();
    return;
  }
  if (target.id === "admin-users-select-all") {
    const checked = Boolean(target.checked);
    const checkboxes = Array.from(usersHost.querySelectorAll("input[data-bulk-user]"));
    checkboxes.forEach((checkbox) => {
      checkbox.checked = checked;
      const username = String(checkbox.getAttribute("data-bulk-user") || "").toLowerCase();
      if (!username) return;
      if (checked) {
        selectedBulkUsers.add(username);
      } else {
        selectedBulkUsers.delete(username);
      }
    });
    const statusHost = document.getElementById("admin-bulk-status");
    if (statusHost) statusHost.textContent = `Выбрано: ${selectedBulkUsers.size}`;
  }
});

examImportHost?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const detailButton = target.closest("[data-exam-source-row]");
  if (!(detailButton instanceof HTMLElement)) {
    return;
  }
  await openExamEntryDetail(detailButton.getAttribute("data-exam-source-row") || "");
});

syntheticHost?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const button = target.closest("[data-synthetic-run]");
  if (!(button instanceof HTMLElement)) {
    return;
  }
  await runSyntheticSuite(button.getAttribute("data-synthetic-run") || "");
});

usersHost?.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const username = target.getAttribute("data-bulk-user");
  if (username) {
    if (target.checked) {
      selectedBulkUsers.add(String(username).toLowerCase());
    } else {
      selectedBulkUsers.delete(String(username).toLowerCase());
    }
    const statusHost = document.getElementById("admin-bulk-status");
    if (statusHost) statusHost.textContent = `Выбрано: ${selectedBulkUsers.size}`;
  }
});

catalogHost?.addEventListener("change", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (target.id === "catalog-entity") {
    await loadCatalog(String(target.value || "servers"));
    return;
  }
  if (target.id === "law-sources-server-select") {
    activeLawServerCode = String(target.value || "").trim().toLowerCase();
    await loadLawSourcesManager();
    await loadLawSets();
  }
});

catalogHost?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (target.id === "runtime-servers-refresh") {
    await loadRuntimeServersPanel();
    return;
  }
  if (target.id === "runtime-servers-create") {
    await createRuntimeServerFlow();
    return;
  }
  const runtimeEditCode = target.getAttribute("data-runtime-server-edit");
  if (runtimeEditCode) {
    const currentTitle = String(target.getAttribute("data-runtime-server-title") || runtimeEditCode);
    await editRuntimeServerFlow(runtimeEditCode, currentTitle);
    return;
  }
  const runtimeToggleCode = target.getAttribute("data-runtime-server-toggle");
  if (runtimeToggleCode) {
    const activeRaw = String(target.getAttribute("data-runtime-server-active") || "0");
    await toggleRuntimeServerFlow(runtimeToggleCode, activeRaw === "1");
    return;
  }
  if (target.id === "law-sources-sync") {
    await syncLawSourcesFromServerConfig();
    return;
  }
  if (target.id === "law-sources-rebuild") {
    await rebuildLawSources();
    return;
  }
  if (target.id === "law-sources-rebuild-async") {
    await rebuildLawSourcesAsync();
    return;
  }
  if (target.id === "law-sources-save") {
    await saveLawSourcesManifest();
    return;
  }
  if (target.id === "law-sources-preview") {
    await previewLawSources();
    return;
  }
  if (target.id === "law-sets-refresh") {
    await loadLawSets();
    return;
  }
  if (target.id === "law-sets-create") {
    await createLawSetFlow();
    return;
  }
  if (target.id === "law-source-registry-refresh") {
    await loadLawSourceRegistry();
    return;
  }
  if (target.id === "law-source-registry-create") {
    await createLawSourceRegistryFlow();
    return;
  }
  const lawSetEditId = target.getAttribute("data-law-set-edit");
  if (lawSetEditId) {
    const currentName = String(target.getAttribute("data-law-set-name") || "");
    const currentIsActive = String(target.getAttribute("data-law-set-active") || "1") === "1";
    await editLawSetFlow(lawSetEditId, currentName, currentIsActive);
    return;
  }
  const lawSetPublishId = target.getAttribute("data-law-set-publish");
  if (lawSetPublishId) {
    await publishLawSetFlow(lawSetPublishId);
    return;
  }
  const lawSetRebuildId = target.getAttribute("data-law-set-rebuild");
  if (lawSetRebuildId) {
    await rebuildLawSetFlow(lawSetRebuildId);
    return;
  }
  const lawSourceEditId = target.getAttribute("data-law-source-edit");
  if (lawSourceEditId) {
    const currentName = String(target.getAttribute("data-law-source-name") || "");
    const currentKind = String(target.getAttribute("data-law-source-kind") || "url");
    const currentUrl = String(target.getAttribute("data-law-source-url") || "");
    const currentActive = String(target.getAttribute("data-law-source-active") || "1") === "1";
    await editLawSourceRegistryFlow(lawSourceEditId, currentName, currentKind, currentUrl, currentActive);
    return;
  }
  if (target.id === "catalog-create") {
    const payload = await openCatalogFormDialog(activeCatalogEntity);
    if (!payload) return;
    await performAdminAction(catalogEndpoint(activeCatalogEntity), "Элемент создан.", payload);
    await loadCatalog(activeCatalogEntity);
    return;
  }
  const viewId = target.getAttribute("data-catalog-view");
  if (viewId) {
    const response = await apiFetch(catalogEndpoint(activeCatalogEntity, viewId));
    const payload = await parsePayload(response);
    if (!response.ok) {
      setStateError(errorsHost, formatHttpError(response, payload, "Не удалось загрузить элемент catalog."));
      return;
    }
    openCatalogModal({
      mode: "view",
      itemId: viewId,
      item: payload?.item || {},
      versions: Array.isArray(payload?.versions) ? payload.versions : [],
    });
    return;
  }
  const editId = target.getAttribute("data-catalog-edit");
  if (editId) {
    const itemResponse = await apiFetch(catalogEndpoint(activeCatalogEntity, editId));
    const itemPayload = await parsePayload(itemResponse);
    if (!itemResponse.ok) {
      setStateError(errorsHost, formatHttpError(itemResponse, itemPayload, "Не удалось загрузить элемент catalog."));
      return;
    }
    const payload = await openCatalogFormDialog(activeCatalogEntity, extractCatalogEditableData(itemPayload));
    if (!payload) return;
    const response = await apiFetch(catalogEndpoint(activeCatalogEntity, editId), {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    if (response.ok) showMessage("Элемент обновлен.");
    await loadCatalog(activeCatalogEntity);
    return;
  }
  const workflowItemId = target.getAttribute("data-catalog-workflow-item");
  if (workflowItemId) {
    const action = String(target.getAttribute("data-catalog-workflow-action") || "").trim().toLowerCase();
    const changeRequestId = Number(target.getAttribute("data-catalog-workflow-cr-id") || "0");
    if (!action || !changeRequestId) {
      setStateError(errorsHost, "Не удалось определить действие workflow: отсутствует change request.");
      return;
    }
    await performAdminAction(`${catalogEndpoint(activeCatalogEntity, workflowItemId)}/workflow`, "Workflow обновлен.", {
      action,
      change_request_id: changeRequestId,
    });
    await loadCatalog(activeCatalogEntity);
    return;
  }
  const previewId = target.getAttribute("data-catalog-preview");
  if (previewId) {
    await loadCatalogPreview(previewId);
    return;
  }
  if (target.id === "catalog-preview-copy") {
    const jsonHost = document.getElementById("catalog-preview-json");
    const text = String(jsonHost?.textContent || "").trim();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      showMessage("JSON скопирован.");
    } catch {
      showMessage("Не удалось скопировать JSON.");
    }
    return;
  }
  const rollbackId = target.getAttribute("data-catalog-rollback");
  if (rollbackId) {
    const version = Number(window.prompt("Rollback to version", "1") || "1");
    await performAdminAction(`${catalogEndpoint(activeCatalogEntity, rollbackId)}/rollback`, "Rollback выполнен.", { version });
    await loadCatalog(activeCatalogEntity);
    return;
  }
  const deleteId = target.getAttribute("data-catalog-delete");
  if (deleteId) {
    const response = await apiFetch(catalogEndpoint(activeCatalogEntity, deleteId), { method: "DELETE" });
    if (response.ok) showMessage("Элемент удален.");
    await loadCatalog(activeCatalogEntity);
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
    loadAiPipeline(),
    loadRoleHistory(),
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
actionModal.bind(
  document.getElementById("admin-action-modal-close"),
  document.getElementById("admin-action-cancel"),
);
catalogModal.bind(
  document.getElementById("admin-catalog-modal-close"),
  document.getElementById("admin-catalog-cancel"),
);

actionConfirmButton?.addEventListener("click", submitPendingAction);
actionCancelButton?.addEventListener("click", closeActionModal);
document.getElementById("admin-action-modal-close")?.addEventListener("click", resetActionModalFields);
catalogSaveButton?.addEventListener("click", submitCatalogModal);
catalogForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  submitCatalogModal();
});
catalogCancelButton?.addEventListener("click", closeCatalogModal);
document.getElementById("admin-catalog-modal-close")?.addEventListener("click", closeCatalogModal);
catalogJsonInput?.addEventListener("input", () => {
  if (catalogJsonError) {
    catalogJsonError.hidden = true;
    catalogJsonError.textContent = "";
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    userModal.close();
    closeActionModal();
    closeCatalogModal();
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
      loadAiPipeline({ silent: true }),
      loadRoleHistory({ silent: true }),
    ]);
  }
});

resetActionModalFields();
resetCatalogModalState();
initCollapsibles();
Promise.all([
  loadAdminOverview(),
  loadAdminPerformance(),
  loadAiPipeline(),
  loadRoleHistory(),
  loadCatalog(),
]).then(() => {
  scheduleLiveRefresh();
});
