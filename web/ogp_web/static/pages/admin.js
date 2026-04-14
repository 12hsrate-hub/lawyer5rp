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
const {
  buildScopedStorageKey,
  catalogEndpoint,
  formatHttpError,
  withQuery,
} = window.OGPAdmin;
const {
  formatExamAverage: formatExamAverageMarkup,
  getExamEntryStatus: getExamEntryStatusMarkup,
  renderAdminAuditMarkup,
  renderAdminExamEntriesSectionMarkup,
  renderErrorExplorerMarkup,
  renderEventsMarkup,
  renderExamImportMarkup,
  renderUserActivityMarkup,
  renderUserStatusesMarkup,
  renderUsersMarkup,
} = window.OGPAdminActivity;
const {
  buildCatalogPreviewMetaText,
  formatCatalogPreviewValue,
  renderCatalogAuditTrailMarkup,
  renderCatalogMarkup,
  renderCatalogPreviewSummaryMarkup,
} = window.OGPAdminCatalog;
const {
  renderAiPipelineMarkup,
  renderCostSummaryMarkup,
  renderPerformanceMarkup,
  renderRoleHistoryMarkup,
  renderSyntheticMarkup,
  renderTopEndpointsMarkup,
  renderTotalsMarkup,
} = window.OGPAdminOverview;
const {
  renderLawSetsTable,
  renderRuntimeServersTable,
  renderServerLawBindingsTable,
  renderServerSetupWorkflow: renderServerSetupWorkflowMarkup,
} = window.OGPAdminRuntimeLaws;
const {
  renderUserModalMarkup,
} = window.OGPAdminUserDetails;
const {
  createAdminOverviewLoader,
} = window.OGPAdminOverviewLoader;
const {
  createAdminActionsController,
} = window.OGPAdminActions;
const {
  createAdminLawRuntimeController,
} = window.OGPAdminLawRuntimeController;
const ExamView = window.OGPExamImportView;
const ADMIN_COLLAPSE_STORAGE_KEY = "ogp_admin_collapsible_sections";
const LAW_REBUILD_TASK_STORAGE_KEY = "ogp_admin_law_rebuild_task_id";
const DEFAULT_USER_MODAL_TITLE = userModalTitle?.textContent || "Карточка пользователя";

let adminSearchTimer = null;
let adminLiveTimer = null;
let lawRebuildPollTimer = null;
let selectedUser = null;
let selectedBulkUsers = new Set();
const userIndex = new Map();
let activeCatalogEntity = String(catalogHost?.dataset.catalogEntity || "servers");
let activeSyntheticSuite = "";
let pendingCatalogContext = null;
let activeLawServerCode = "";
let lawServerOptions = [];
let lawSetOptions = [];
let lawSourceRegistryItems = [];
let serverLawBindingItems = [];
let runtimeServerItems = [];
let runtimeServerHealth = null;
let lawCatalogOptions = [];
let activeCatalogAuditEntityType = "";
let activeCatalogAuditEntityId = "";

function withLawServerQuery(path) {
  return withQuery(path, "server_code", activeLawServerCode);
}

function getLawServerSelect() {
  return document.getElementById("law-sources-server-select");
}

function getLawRebuildTaskStorageKey(serverCode = activeLawServerCode) {
  return buildScopedStorageKey(LAW_REBUILD_TASK_STORAGE_KEY, serverCode);
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

async function fetchRuntimeServersPayload() {
  return adminLawRuntimeController.fetchRuntimeServersPayload();
}

function syncLawServerOptionsFromRuntimeServers() {
  adminLawRuntimeController.syncLawServerOptionsFromRuntimeServers();
}

async function loadLawServerOptions() {
  return adminLawRuntimeController.loadLawServerOptions();
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
  renderServerSetupWorkflow();
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
  renderServerSetupWorkflow();
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

function renderPlatformBlueprintStage(payload) {
  const host = document.getElementById("platform-blueprint-stage");
  if (!host) {
    return;
  }
  const stage = payload?.stage || {};
  const stageCode = String(stage?.stage_code || "phase_a_foundation").trim();
  const stageLabel = String(stage?.stage_label || "Phase A - Stabilize foundation").trim();
  host.innerHTML = `
    <div class="legal-section__description"><strong>Этап платформы:</strong> ${escapeHtml(stageLabel)}</div>
    <div class="legal-field__hint">code: <code>${escapeHtml(stageCode)}</code></div>
  `;
}

async function loadPlatformBlueprintStage() {
  const host = document.getElementById("platform-blueprint-stage");
  if (!host) {
    return;
  }
  const response = await apiFetch("/api/admin/platform-blueprint/status");
  const payload = await parsePayload(response);
  if (!response.ok) {
    host.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, "Не удалось загрузить текущий этап платформы."))}</p>`;
    return;
  }
  renderPlatformBlueprintStage(payload);
}

function parseLawSetItemsInput(raw) {
  return adminLawRuntimeController.parseLawSetItemsInput(raw);
}

function getActiveRuntimeServer() {
  return adminLawRuntimeController.getActiveRuntimeServer();
}

function renderServerSetupWorkflow() {
  adminLawRuntimeController.renderServerSetupWorkflow();
}

async function loadRuntimeServerHealth({ silent = true } = {}) {
  return adminLawRuntimeController.loadRuntimeServerHealth({ silent });
}

function renderLawSets(payload) {
  adminLawRuntimeController.renderLawSets(payload);
}

async function loadLawSets() {
  return adminLawRuntimeController.loadLawSets();
}

async function createLawSetFlow() {
  return adminLawRuntimeController.createLawSetFlow();
}

async function editLawSetFlow(lawSetId, currentName, currentIsActive) {
  return adminLawRuntimeController.editLawSetFlow(lawSetId, currentName, currentIsActive);
}

async function publishLawSetFlow(lawSetId) {
  return adminLawRuntimeController.publishLawSetFlow(lawSetId);
}

async function rebuildLawSetFlow(lawSetId) {
  return adminLawRuntimeController.rebuildLawSetFlow(lawSetId);
}

async function rollbackLawSetFlow(lawSetId) {
  return adminLawRuntimeController.rollbackLawSetFlow(lawSetId);
}

function renderLawSourceRegistry(payload) {
  const host = document.getElementById("law-source-registry-host");
  if (!host) return;
  const items = Array.isArray(payload?.items) ? payload.items : [];
  lawSourceRegistryItems = items;
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

function renderServerLawBindings(payload) {
  adminLawRuntimeController.renderServerLawBindings(payload);
}

async function loadServerLawBindings() {
  return adminLawRuntimeController.loadServerLawBindings();
}

async function loadLawCatalogOptions() {
  const response = await apiFetch(catalogEndpoint("laws"));
  const payload = await parsePayload(response);
  if (!response.ok) {
    return [];
  }
  const items = Array.isArray(payload?.items) ? payload.items : [];
  lawCatalogOptions = items;
  return items;
}

function normalizeLawCodeOptions(items) {
  const seen = new Set();
  const normalized = [];
  items.forEach((item) => {
    const rawCode = String(item?.code || item?.key || item?.law_code || "").trim();
    if (!rawCode) return;
    const code = rawCode.toLowerCase();
    if (seen.has(code)) return;
    seen.add(code);
    normalized.push({
      code,
      label: String(item?.title || item?.name || item?.law_set_name || rawCode).trim() || rawCode,
    });
  });
  return normalized.sort((a, b) => a.code.localeCompare(b.code));
}

async function openServerLawBindingDialog() {
  if (!lawSetOptions.length) {
    await loadLawSets();
  }
  if (!lawSourceRegistryItems.length) {
    await loadLawSourceRegistry();
  }
  const catalogItems = await loadLawCatalogOptions();
  const lawCodeOptions = normalizeLawCodeOptions([...catalogItems, ...serverLawBindingItems, ...lawSetOptions]);
  const sourceOptions = lawSourceRegistryItems.filter((item) => Number(item?.id) > 0);
  if (!sourceOptions.length) {
    throw new Error("Сначала добавьте источник в «Реестр источников».");
  }
  if (!lawCodeOptions.length) {
    throw new Error("Не удалось собрать список кодов законов для выбора.");
  }
  const dialog = document.createElement("dialog");
  dialog.innerHTML = `
    <form method="dialog" class="legal-section">
      <h3>Привязать закон к серверу</h3>
      <p class="legal-field__hint">Сервер: <strong>${escapeHtml(activeLawServerCode)}</strong></p>
      <label class="legal-field"><span class="legal-field__label">Код закона</span>
        <select name="law_code" required>
          ${lawCodeOptions.map((item) => `<option value="${escapeHtml(item.code)}">${escapeHtml(item.code)} — ${escapeHtml(item.label)}</option>`).join("")}
        </select>
      </label>
      <label class="legal-field"><span class="legal-field__label">Источник</span>
        <select name="source_id" required>
          ${sourceOptions.map((item) => `<option value="${escapeHtml(String(item.id))}">${escapeHtml(String(item.name || "Источник"))} — ${escapeHtml(String(item.url || ""))}</option>`).join("")}
        </select>
      </label>
      <label class="legal-field"><span class="legal-field__label">Набор законов</span>
        <select name="law_set_id">
          <option value="">Автовыбор (публикуемый/последний)</option>
          ${lawSetOptions.map((item) => `<option value="${escapeHtml(String(item.id || ""))}">${escapeHtml(String(item.name || item.id || ""))}</option>`).join("")}
        </select>
      </label>
      <label class="legal-field"><span class="legal-field__label">Priority</span><input type="number" name="priority" value="100" min="1" max="10000"></label>
      <label class="legal-field"><span class="legal-field__label">Effective from</span><input type="date" name="effective_from" value=""></label>
      <menu style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px;">
        <button type="button" class="ghost-button" data-action="cancel">Отмена</button>
        <button type="submit" class="primary-button" data-action="submit">Привязать</button>
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
    dialog.querySelector('[data-action="cancel"]')?.addEventListener("click", () => finish(null));
    dialog.addEventListener("cancel", () => finish(null));
    dialog.addEventListener("close", () => finish(null));
    dialog.querySelector("form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      if (!(form instanceof HTMLFormElement)) return;
      const formData = new FormData(form);
      const lawCode = String(formData.get("law_code") || "").trim().toLowerCase();
      const sourceId = Number(formData.get("source_id") || 0);
      const priority = Number(formData.get("priority") || 100);
      const effectiveFrom = String(formData.get("effective_from") || "").trim();
      const lawSetIdRaw = String(formData.get("law_set_id") || "").trim();
      if (!lawCode) {
        setStateError(errorsHost, "Выберите код закона.");
        return;
      }
      if (!Number.isFinite(sourceId) || sourceId <= 0) {
        setStateError(errorsHost, "Выберите источник.");
        return;
      }
      finish({
        law_code: lawCode,
        source_id: sourceId,
        priority: Number.isFinite(priority) ? priority : 100,
        effective_from: effectiveFrom,
        law_set_id: lawSetIdRaw ? Number(lawSetIdRaw) : null,
      });
    });
    dialog.showModal();
  });
}

async function addServerLawBindingFlow() {
  let formPayload = null;
  if (!activeLawServerCode) {
    setStateError(errorsHost, "Сначала выберите сервер.");
    return;
  }
  try {
    formPayload = await openServerLawBindingDialog();
  } catch (error) {
    setStateError(errorsHost, String(error?.message || error));
    return;
  }
  if (!formPayload) return;
  const response = await apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(activeLawServerCode)}/law-bindings`, {
    method: "POST",
    body: JSON.stringify(formPayload),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "Не удалось привязать закон к серверу."));
    return;
  }
  showMessage(`Закон ${String(formPayload.law_code || "")} привязан к серверу ${activeLawServerCode}.`);
  await loadServerLawBindings();
}

async function loadLawJobsOverview() {
  const host = document.getElementById("law-jobs-host");
  if (!host) return;
  const response = await apiFetch("/api/admin/law-jobs/overview");
  const payload = await parsePayload(response);
  if (!response.ok) {
    host.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, "Не удалось загрузить jobs/alerts."))}</p>`;
    return;
  }
  const summary = payload?.summary || {};
  const alerts = Array.isArray(payload?.alerts) ? payload.alerts : [];
  const running = Array.isArray(payload?.running) ? payload.running : [];
  host.innerHTML = `
    <div class="legal-section__description">
      jobs: total=${escapeHtml(String(summary.total_tasks || 0))}, running=${escapeHtml(String(summary.running_tasks || 0))}, failed=${escapeHtml(String(summary.failed_tasks || 0))}, alerts=${escapeHtml(String(summary.alerts_count || 0))}
    </div>
    <details ${alerts.length ? "open" : ""}>
      <summary>Алерты</summary>
      <pre class="legal-field__hint">${escapeHtml(JSON.stringify(alerts, null, 2) || "[]")}</pre>
    </details>
    <details>
      <summary>Running jobs</summary>
      <pre class="legal-field__hint">${escapeHtml(JSON.stringify(running, null, 2) || "[]")}</pre>
    </details>
  `;
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
  catalogHost.innerHTML = renderCatalogMarkup({
    entityType,
    items,
    audit,
    activeCatalogAuditEntityType,
    activeCatalogAuditEntityId,
  });
}

function renderCatalogAuditTrail(payload) {
  const host = document.getElementById("catalog-audit-results");
  if (!host) {
    return;
  }
  const items = Array.isArray(payload?.items) ? payload.items : [];
  host.innerHTML = renderCatalogAuditTrailMarkup(items);
}

async function loadCatalogAuditTrail() {
  const params = new URLSearchParams();
  const inputEntityType = String(document.getElementById("catalog-audit-entity-type")?.value || activeCatalogAuditEntityType || "").trim().toLowerCase();
  const inputEntityId = String(document.getElementById("catalog-audit-entity-id")?.value || activeCatalogAuditEntityId || "").trim();
  const limitRaw = String(document.getElementById("catalog-audit-limit")?.value || "12").trim();
  const safeLimit = Math.max(1, Math.min(500, Number(limitRaw || 12) || 12));
  activeCatalogAuditEntityType = inputEntityType;
  activeCatalogAuditEntityId = inputEntityId;
  if (inputEntityType) params.set("entity_type", inputEntityType);
  if (inputEntityId) params.set("entity_id", inputEntityId);
  params.set("limit", String(safeLimit));
  const response = await apiFetch(`/api/admin/catalog/audit?${params.toString()}`);
  const payload = await parsePayload(response);
  const host = document.getElementById("catalog-audit-results");
  if (!response.ok) {
    if (host) {
      host.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, "Не удалось загрузить журнал изменений."))}</p>`;
    }
    return;
  }
  renderCatalogAuditTrail(payload);
}

function renderRuntimeServersPanel(payload) {
  adminLawRuntimeController.renderRuntimeServersPanel(payload);
}

async function loadRuntimeServersPanel() {
  return adminLawRuntimeController.loadRuntimeServersPanel();
}

async function createRuntimeServerFlow() {
  return adminLawRuntimeController.createRuntimeServerFlow();
}

async function editRuntimeServerFlow(code, currentTitle) {
  return adminLawRuntimeController.editRuntimeServerFlow(code, currentTitle);
}

async function toggleRuntimeServerFlow(code, isActive) {
  return adminLawRuntimeController.toggleRuntimeServerFlow(code, isActive);
}

function renderCatalogPreview(payload, itemId) {
  const previewPanel = document.getElementById("catalog-preview-panel");
  const summaryHost = document.getElementById("catalog-preview-summary");
  const metaHost = document.getElementById("catalog-preview-meta");
  const jsonHost = document.getElementById("catalog-preview-json");
  if (!previewPanel || !summaryHost || !metaHost || !jsonHost) return;
  const item = payload?.item || {};
  const effectivePayload = payload?.effective_payload && typeof payload.effective_payload === "object" ? payload.effective_payload : {};
  summaryHost.innerHTML = renderCatalogPreviewSummaryMarkup(activeCatalogEntity, item, effectivePayload);
  metaHost.textContent = buildCatalogPreviewMetaText(payload, itemId);
  jsonHost.textContent = formatCatalogPreviewValue(effectivePayload);
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
    .replace(/[^a-z0-9_\-.Р°-СЏС']/gi, "")
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
  activeCatalogAuditEntityType = "";
  activeCatalogAuditEntityId = "";
  renderCatalog(payload);
  await loadCatalogAuditTrail();
  if (entityType === "servers") {
    await loadRuntimeServersPanel();
  }
  if (entityType === "laws") {
    await adminLawRuntimeController.loadCatalogContext();
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

const adminActions = createAdminActionsController({
  actionConfirmButton,
  actionEmailField,
  actionEmailInput,
  actionModal,
  actionModalDescription,
  actionModalErrors,
  actionModalTitle,
  actionPasswordField,
  actionPasswordInput,
  actionQuotaField,
  actionQuotaInput,
  actionReasonField,
  actionReasonInput,
  apiFetch,
  clearMessage,
  errorsHost,
  formatHttpError,
  loadAdminOverview: (...args) => loadAdminOverview(...args),
  parsePayload,
  setStateError,
  setStateIdle,
  showMessage,
});

function resetActionModalFields() {
  adminActions.reset();
}

function openActionModal(config) {
  adminActions.open(config);
}

function closeActionModal() {
  adminActions.close();
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
  return renderBadge("Р РёСЃРє: РЅРёР·РєРёР№", "success-soft");
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
  totalsHost.innerHTML = renderTotalsMarkup(totals, {
    escapeHtml,
    formatNumber,
    formatUsd,
  });
}

function renderPerformance(payload) {
  if (!performanceHost) {
    return;
  }
  performanceHost.innerHTML = renderPerformanceMarkup(payload, {
    escapeHtml,
    renderBadge,
  });
}

function renderSynthetic(summary) {
  if (!syntheticHost) {
    return;
  }
  syntheticHost.innerHTML = renderSyntheticMarkup(summary, {
    activeSyntheticSuite,
    escapeHtml,
    renderBadge,
  });
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
  costSummaryHost.innerHTML = renderCostSummaryMarkup(totals, {
    escapeHtml,
    formatNumber,
    formatUsd,
  });
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
  aiPipelineHost.innerHTML = renderAiPipelineMarkup(payload, {
    escapeHtml,
    formatNumber,
    formatUsd,
    renderBandBadge,
  });
}
function renderRoleHistory(payload) {
  if (!roleHistoryHost) {
    return;
  }
  roleHistoryHost.innerHTML = renderRoleHistoryMarkup(payload, { escapeHtml });
}

function renderTopEndpoints(items) {
  if (!endpointsHost) {
    return;
  }
  endpointsHost.innerHTML = renderTopEndpointsMarkup(items, {
    describeApiPath,
    escapeHtml,
  });
}

function renderExamImport(summary) {
  if (!examImportHost) {
    return;
  }
  examImportHost.innerHTML = renderExamImportMarkup(summary, {
    describeEventType,
    escapeHtml,
    renderBadge,
    renderAdminExamEntriesSectionMarkup: (config) =>
      renderAdminExamEntriesSectionMarkup(config, {
        ExamView,
        escapeHtml,
        renderBadge,
      }),
  });
}
function getExamEntryStatus(entry) {
  return getExamEntryStatusMarkup(entry, { ExamView });
}
function formatExamAverage(entry) {
  return formatExamAverageMarkup(entry, { ExamView });
}
function renderAdminExamEntriesSection({ title, description, entries, emptyText, emphasizeFailed = false }) {
  return renderAdminExamEntriesSectionMarkup(
    { title, description, entries, emptyText, emphasizeFailed },
    {
      ExamView,
      escapeHtml,
      renderBadge,
      getExamEntryStatus: (entry) => getExamEntryStatus(entry),
      formatExamAverage: (entry) => formatExamAverage(entry),
    },
  );
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
  if (filters.event_type) chips.push(renderFilterChip(`РўРёРї: ${filters.event_type}`, "event_type"));
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
  usersHost.innerHTML = renderUsersMarkup(
    users,
    {
      selectedBulkUsers,
      userSort,
    },
    {
      escapeHtml,
      renderUserActivityMarkup: (user) => renderUserActivityMarkup(user, { escapeHtml }),
      renderUserStatusesMarkup: (user) => renderUserStatusesMarkup(user, { renderBadge, riskLabel }),
    },
  );
}
function renderEvents(events) {
  if (!eventsHost) {
    return;
  }
  eventsHost.innerHTML = renderEventsMarkup(events, {
    describeApiPath,
    describeEventType,
    escapeHtml,
    renderBadge,
  });
}
function renderErrorExplorer(payload) {
  if (!errorExplorerHost) {
    return;
  }
  errorExplorerHost.innerHTML = renderErrorExplorerMarkup(payload, {
    escapeHtml,
    renderBadge,
  });
}
function renderAdminAudit(events) {
  if (!adminEventsHost) {
    return;
  }
  adminEventsHost.innerHTML = renderAdminAuditMarkup(events, {
    describeApiPath,
    describeEventType,
    escapeHtml,
    renderBadge,
  });
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
  userModalBody.innerHTML = renderUserModalMarkup(user, {
    escapeHtml,
    renderUserStatuses: (targetUser) => renderUserStatuses(targetUser),
  });
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

const adminOverviewLoader = createAdminOverviewLoader({
  apiFetch,
  buildOverviewUrl,
  clearMessage,
  currentFilters,
  errorsHost,
  formatHttpError,
  getSelectedUser: () => selectedUser,
  parsePayload,
  renderActiveFilters,
  renderAdminAudit,
  renderCostSummary,
  renderErrorExplorer,
  renderEvents,
  renderExamImport,
  renderModelPolicy,
  renderSynthetic,
  renderTopEndpoints,
  renderTotals,
  renderUserModal,
  renderUsers,
  setLiveStatus,
  setStateError,
  setStateIdle,
  showOverviewLoading,
  userIndex,
});

const adminLawRuntimeController = createAdminLawRuntimeController({
  apiFetch,
  addServerLawBindingFlow,
  errorsHost,
  escapeHtml,
  formatHttpError,
  getActiveCatalogEntity() {
    return activeCatalogEntity;
  },
  getActiveLawServerCode() {
    return activeLawServerCode;
  },
  getCatalogHost() {
    return catalogHost;
  },
  getLawSetOptions() {
    return lawSetOptions;
  },
  getRuntimeServerHealth() {
    return runtimeServerHealth;
  },
  getRuntimeServerItems() {
    return runtimeServerItems;
  },
  getServerLawBindingItems() {
    return serverLawBindingItems;
  },
  createLawSourceRegistryFlow,
  editLawSourceRegistryFlow,
  loadCatalog,
  loadLawJobsOverview,
  loadLawSourceRegistry,
  loadLawSourcesManager,
  parsePayload,
  previewLawSources,
  rebuildLawSources,
  rebuildLawSourcesAsync,
  renderRuntimeServersTable,
  renderLawSetsTable,
  renderServerLawBindingsTable,
  renderLawServerSelector,
  renderServerSetupWorkflowMarkup,
  saveLawSourcesManifest,
  setActiveLawServerCode(value) {
    activeLawServerCode = value;
  },
  setLawServerOptions(value) {
    lawServerOptions = Array.isArray(value) ? value : [];
  },
  setLawSetOptions(value) {
    lawSetOptions = Array.isArray(value) ? value : [];
  },
  setServerLawBindingItems(value) {
    serverLawBindingItems = Array.isArray(value) ? value : [];
  },
  setRuntimeServerHealth(value) {
    runtimeServerHealth = value;
  },
  setRuntimeServerItems(value) {
    runtimeServerItems = Array.isArray(value) ? value : [];
  },
  setStateError,
  showMessage,
  syncLawSourcesFromServerConfig,
});

async function loadAdminOverview({ silent = false } = {}) {
  return adminOverviewLoader.load({ silent });
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
  return adminActions.performAction(url, successText, body);
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
  return adminActions.handleTarget(target);
}

async function submitPendingAction() {
  return adminActions.submitPendingAction();
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
  if (await adminLawRuntimeController.handleCatalogChange(target)) {
    return;
  }
});

catalogHost?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (await adminLawRuntimeController.handleCatalogClick(target)) {
    return;
  }
  if (target.id === "catalog-create") {
    const payload = await openCatalogFormDialog(activeCatalogEntity);
    if (!payload) return;
    await performAdminAction(catalogEndpoint(activeCatalogEntity), "Элемент создан.", payload);
    await loadCatalog(activeCatalogEntity);
    return;
  }
  if (target.id === "catalog-audit-refresh") {
    await loadCatalogAuditTrail();
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
