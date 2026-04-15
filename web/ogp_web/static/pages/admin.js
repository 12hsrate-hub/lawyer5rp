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
const asyncJobsHost = document.getElementById("admin-async-jobs");
const lawJobsHost = document.getElementById("admin-law-jobs");
const examImportOpsHost = document.getElementById("admin-exam-import-ops");
const pilotRolloutHost = document.getElementById("admin-pilot-rollout");
const provenanceTraceHost = document.getElementById("admin-provenance-trace");
const provenanceTraceForm = document.getElementById("admin-provenance-form");
const provenanceTraceVersionField = document.getElementById("admin-provenance-version-id");
const provenanceTraceDocumentField = document.getElementById("admin-provenance-document-id");
const provenanceTraceLoadButton = document.getElementById("admin-provenance-load");
const generatedDocumentsReviewHost = document.getElementById("admin-generated-documents-review");
const generatedDocumentContextHost = document.getElementById("admin-generated-document-context");
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
  renderExamImportOpsMarkup,
  renderLawJobsMarkup,
  renderPerformanceMarkup,
  renderRoleHistoryMarkup,
  renderAsyncJobsMarkup,
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
const DEFAULT_USER_MODAL_TITLE = userModalTitle?.textContent || "РљР°СЂС‚РѕС‡РєР° РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ";

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
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РёСЃС‚РѕС‡РЅРёРєРё Р·Р°РєРѕРЅРѕРІ."));
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
    const activeVersionId = payload?.active_law_version?.id ?? "вЂ”";
    const chunkCount = payload?.bundle_meta?.chunk_count ?? payload?.active_law_version?.chunk_count ?? "вЂ”";
    const origin = String(payload?.source_origin || "unknown");
    statusHost.textContent = `РСЃС‚РѕС‡РЅРёРє СЃСЃС‹Р»РѕРє: ${origin}. РђРєС‚РёРІРЅР°СЏ РІРµСЂСЃРёСЏ Р·Р°РєРѕРЅР°: ${activeVersionId}. РЎС‚Р°С‚РµР№ РІ РёРЅРґРµРєСЃРµ: ${chunkCount}.`;
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
    host.innerHTML = '<p class="legal-section__description">РСЃС‚РѕСЂРёСЏ РїРµСЂРµСЃР±РѕСЂРѕРє РїРѕРєР° РїСѓСЃС‚Р°.</p>';
    return;
  }
  host.innerHTML = `
    <ul class="legal-section__description">
      ${items
        .map((item) => `<li>Р’РµСЂСЃРёСЏ #${escapeHtml(String(item.id || "вЂ”"))} вЂў articles: ${escapeHtml(String(item.chunk_count || 0))} вЂў generated: ${escapeHtml(String(item.generated_at_utc || "вЂ”"))}</li>`)
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
    host.innerHTML = '<p class="legal-section__description">РќРµС‚ РґР°РЅРЅС‹С… РїРѕ Р·Р°РІРёСЃРёРјРѕСЃС‚СЏРј РёСЃС‚РѕС‡РЅРёРєРѕРІ.</p>';
    return;
  }
  host.innerHTML = `
    <div class="legal-section__description"><strong>РЎРІСЏР·СЊ СЃРµСЂРІРµСЂРѕРІ Рё РёСЃС‚РѕС‡РЅРёРєРѕРІ Р·Р°РєРѕРЅРѕРІ</strong></div>
    <table class="legal-table">
      <thead><tr><th>РЎРµСЂРІРµСЂ</th><th>РСЃС‚РѕС‡РЅРёРєРѕРІ</th><th>РћР±С‰РёС… РёСЃС‚РѕС‡РЅРёРєРѕРІ</th><th>РЎРІСЏР·Р°РЅ СЃ СЃРµСЂРІРµСЂР°РјРё</th></tr></thead>
      <tbody>
        ${rows
          .map((row) => `<tr>
            <td>${escapeHtml(String(row?.server_name || row?.server_code || "вЂ”"))}</td>
            <td>${escapeHtml(String(row?.source_count || 0))}</td>
            <td>${escapeHtml(String(row?.shared_source_count || 0))}</td>
            <td>${escapeHtml(String((row?.shared_with_servers || []).join(", ") || "вЂ”"))}</td>
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
    <div class="legal-section__description"><strong>Р­С‚Р°Рї РїР»Р°С‚С„РѕСЂРјС‹:</strong> ${escapeHtml(stageLabel)}</div>
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
    host.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ С‚РµРєСѓС‰РёР№ СЌС‚Р°Рї РїР»Р°С‚С„РѕСЂРјС‹."))}</p>`;
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
      <thead><tr><th>ID</th><th>РќР°Р·РІР°РЅРёРµ</th><th>Kind</th><th>URL</th><th>РЎС‚Р°С‚СѓСЃ</th><th>Р”РµР№СЃС‚РІРёСЏ</th></tr></thead>
      <tbody>
        ${items.length ? items.map((item) => `
          <tr>
            <td>${escapeHtml(String(item.id || "вЂ”"))}</td>
            <td>${escapeHtml(String(item.name || "вЂ”"))}</td>
            <td>${escapeHtml(String(item.kind || "url"))}</td>
            <td class="admin-user-cell__secondary">${escapeHtml(String(item.url || "вЂ”"))}</td>
            <td>${item.is_active ? "active" : "disabled"}</td>
            <td>
              <button type="button" class="ghost-button" data-law-source-edit="${escapeHtml(String(item.id || ""))}" data-law-source-name="${escapeHtml(String(item.name || ""))}" data-law-source-kind="${escapeHtml(String(item.kind || "url"))}" data-law-source-url="${escapeHtml(String(item.url || ""))}" data-law-source-active="${item.is_active ? "1" : "0"}">РР·РјРµРЅРёС‚СЊ</button>
            </td>
          </tr>
        `).join("") : '<tr><td colspan="6" class="legal-section__description">Р РµРµСЃС‚СЂ РёСЃС‚РѕС‡РЅРёРєРѕРІ РїСѓСЃС‚.</td></tr>'}
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
    host.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЂРµРµСЃС‚СЂ РёСЃС‚РѕС‡РЅРёРєРѕРІ."))}</p>`;
    return;
  }
  renderLawSourceRegistry(payload);
}

async function createLawSourceRegistryFlow() {
  const name = String(window.prompt("РќР°Р·РІР°РЅРёРµ РёСЃС‚РѕС‡РЅРёРєР°", "") || "").trim();
  if (!name) return;
  const kind = String(window.prompt("Kind (url|registry|api)", "url") || "url").trim().toLowerCase();
  const url = String(window.prompt("URL РёСЃС‚РѕС‡РЅРёРєР°", "") || "").trim();
  if (!url) return;
  const response = await apiFetch("/api/admin/law-source-registry", {
    method: "POST",
    body: JSON.stringify({ name, kind, url, is_active: true }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕР·РґР°С‚СЊ РёСЃС‚РѕС‡РЅРёРє."));
    return;
  }
  showMessage("РСЃС‚РѕС‡РЅРёРє РґРѕР±Р°РІР»РµРЅ РІ СЂРµРµСЃС‚СЂ.");
  await loadLawSourceRegistry();
}

async function editLawSourceRegistryFlow(sourceId, currentName, currentKind, currentUrl, currentActive) {
  const name = String(window.prompt("РќР°Р·РІР°РЅРёРµ РёСЃС‚РѕС‡РЅРёРєР°", currentName || "") || "").trim();
  if (!name) return;
  const kind = String(window.prompt("Kind (url|registry|api)", currentKind || "url") || "url").trim().toLowerCase();
  const url = String(window.prompt("URL РёСЃС‚РѕС‡РЅРёРєР°", currentUrl || "") || "").trim();
  if (!url) return;
  const response = await apiFetch(`/api/admin/law-source-registry/${encodeURIComponent(String(sourceId))}`, {
    method: "PUT",
    body: JSON.stringify({ name, kind, url, is_active: currentActive }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ РѕР±РЅРѕРІРёС‚СЊ РёСЃС‚РѕС‡РЅРёРє."));
    return;
  }
  showMessage("РСЃС‚РѕС‡РЅРёРє РѕР±РЅРѕРІР»РµРЅ.");
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
    throw new Error("РЎРЅР°С‡Р°Р»Р° РґРѕР±Р°РІСЊС‚Рµ РёСЃС‚РѕС‡РЅРёРє РІ В«Р РµРµСЃС‚СЂ РёСЃС‚РѕС‡РЅРёРєРѕРІВ».");
  }
  if (!lawCodeOptions.length) {
    throw new Error("РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕР±СЂР°С‚СЊ СЃРїРёСЃРѕРє РєРѕРґРѕРІ Р·Р°РєРѕРЅРѕРІ РґР»СЏ РІС‹Р±РѕСЂР°.");
  }
  const dialog = document.createElement("dialog");
  dialog.innerHTML = `
    <form method="dialog" class="legal-section">
      <h3>РџСЂРёРІСЏР·Р°С‚СЊ Р·Р°РєРѕРЅ Рє СЃРµСЂРІРµСЂСѓ</h3>
      <p class="legal-field__hint">РЎРµСЂРІРµСЂ: <strong>${escapeHtml(activeLawServerCode)}</strong></p>
      <label class="legal-field"><span class="legal-field__label">РљРѕРґ Р·Р°РєРѕРЅР°</span>
        <select name="law_code" required>
          ${lawCodeOptions.map((item) => `<option value="${escapeHtml(item.code)}">${escapeHtml(item.code)} вЂ” ${escapeHtml(item.label)}</option>`).join("")}
        </select>
      </label>
      <label class="legal-field"><span class="legal-field__label">РСЃС‚РѕС‡РЅРёРє</span>
        <select name="source_id" required>
          ${sourceOptions.map((item) => `<option value="${escapeHtml(String(item.id))}">${escapeHtml(String(item.name || "РСЃС‚РѕС‡РЅРёРє"))} вЂ” ${escapeHtml(String(item.url || ""))}</option>`).join("")}
        </select>
      </label>
      <label class="legal-field"><span class="legal-field__label">РќР°Р±РѕСЂ Р·Р°РєРѕРЅРѕРІ</span>
        <select name="law_set_id">
          <option value="">РђРІС‚РѕРІС‹Р±РѕСЂ (РїСѓР±Р»РёРєСѓРµРјС‹Р№/РїРѕСЃР»РµРґРЅРёР№)</option>
          ${lawSetOptions.map((item) => `<option value="${escapeHtml(String(item.id || ""))}">${escapeHtml(String(item.name || item.id || ""))}</option>`).join("")}
        </select>
      </label>
      <label class="legal-field"><span class="legal-field__label">Priority</span><input type="number" name="priority" value="100" min="1" max="10000"></label>
      <label class="legal-field"><span class="legal-field__label">Effective from</span><input type="date" name="effective_from" value=""></label>
      <menu style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px;">
        <button type="button" class="ghost-button" data-action="cancel">РћС‚РјРµРЅР°</button>
        <button type="submit" class="primary-button" data-action="submit">РџСЂРёРІСЏР·Р°С‚СЊ</button>
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
        setStateError(errorsHost, "Р’С‹Р±РµСЂРёС‚Рµ РєРѕРґ Р·Р°РєРѕРЅР°.");
        return;
      }
      if (!Number.isFinite(sourceId) || sourceId <= 0) {
        setStateError(errorsHost, "Р’С‹Р±РµСЂРёС‚Рµ РёСЃС‚РѕС‡РЅРёРє.");
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
    setStateError(errorsHost, "РЎРЅР°С‡Р°Р»Р° РІС‹Р±РµСЂРёС‚Рµ СЃРµСЂРІРµСЂ.");
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
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРёРІСЏР·Р°С‚СЊ Р·Р°РєРѕРЅ Рє СЃРµСЂРІРµСЂСѓ."));
    return;
  }
  showMessage(`Р—Р°РєРѕРЅ ${String(formPayload.law_code || "")} РїСЂРёРІСЏР·Р°РЅ Рє СЃРµСЂРІРµСЂСѓ ${activeLawServerCode}.`);
  await loadServerLawBindings();
}

async function legacyLoadLawJobsOverview() {
  const host = lawJobsHost || document.getElementById("law-jobs-host");
  if (!host) return;
  const response = await apiFetch("/api/admin/law-jobs/overview");
  const payload = await parsePayload(response);
  if (!response.ok) {
    host.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ jobs/alerts."))}</p>`;
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
      <summary>РђР»РµСЂС‚С‹</summary>
      <pre class="legal-field__hint">${escapeHtml(JSON.stringify(alerts, null, 2) || "[]")}</pre>
    </details>
    <details>
      <summary>Running jobs</summary>
      <pre class="legal-field__hint">${escapeHtml(JSON.stringify(running, null, 2) || "[]")}</pre>
    </details>
  `;
}

async function loadLawJobsOverview() {
  const host = lawJobsHost || document.getElementById("law-jobs-host");
  if (!host) return;
  const response = await apiFetch("/api/admin/law-jobs/overview");
  const payload = await parsePayload(response);
  if (!response.ok) {
    host.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, "Р СњР Вµ РЎС“Р Т‘Р В°Р В»Р С•РЎРѓРЎРЉ Р В·Р В°Р С–РЎР‚РЎС“Р В·Р С‘РЎвЂљРЎРЉ jobs/alerts."))}</p>`;
    return;
  }
  host.innerHTML = renderLawJobsMarkup(payload, { escapeHtml });
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
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ РїРµСЂРµСЃРѕР±СЂР°С‚СЊ Р·Р°РєРѕРЅС‹."));
    return;
  }
  showMessage(`Р—Р°РєРѕРЅС‹ РѕР±РЅРѕРІР»РµРЅС‹: РІРµСЂСЃРёСЏ ${String(payload?.law_version_id || "вЂ”")}, СЃС‚Р°С‚РµР№ ${String(payload?.article_count || 0)}.`);
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
      statusHost.textContent = "РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕР»СѓС‡РёС‚СЊ СЃС‚Р°С‚СѓСЃ С„РѕРЅРѕРІРѕР№ РїРµСЂРµСЃР±РѕСЂРєРё.";
    }
    return;
  }
  const status = String(payload?.status || "queued");
  if (statusHost) {
    statusHost.textContent = `Р¤РѕРЅРѕРІР°СЏ РїРµСЂРµСЃР±РѕСЂРєР°: ${status} (task: ${taskId})`;
  }
  if (status === "finished") {
    stopLawRebuildPolling();
    setLawActionButtonsDisabled(false);
    clearStoredLawRebuildTaskId();
    showMessage(`Р¤РѕРЅРѕРІР°СЏ РїРµСЂРµСЃР±РѕСЂРєР° Р·Р°РІРµСЂС€РµРЅР°. Р’РµСЂСЃРёСЏ ${String(payload?.result?.law_version_id || "вЂ”")}.`);
    await loadCatalog("laws");
    return;
  }
  if (status === "failed") {
    stopLawRebuildPolling();
    setLawActionButtonsDisabled(false);
    clearStoredLawRebuildTaskId();
    setStateError(errorsHost, String(payload?.error || "Р¤РѕРЅРѕРІР°СЏ РїРµСЂРµСЃР±РѕСЂРєР° Р·Р°РІРµСЂС€РёР»Р°СЃСЊ РѕС€РёР±РєРѕР№."));
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
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕСЃС‚Р°РІРёС‚СЊ РїРµСЂРµСЃР±РѕСЂРєСѓ РІ РѕС‡РµСЂРµРґСЊ."));
    return;
  }
  showMessage(`РџРµСЂРµСЃР±РѕСЂРєР° РїРѕСЃС‚Р°РІР»РµРЅР° РІ РѕС‡РµСЂРµРґСЊ (task: ${String(payload?.task_id || "вЂ”")}).`);
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
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ РёСЃС‚РѕС‡РЅРёРєРё Р·Р°РєРѕРЅРѕРІ."));
    return;
  }
  showMessage("РСЃС‚РѕС‡РЅРёРєРё Р·Р°РєРѕРЅРѕРІ СЃРѕС…СЂР°РЅРµРЅС‹ РІ workflow.");
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
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРѕРІРµСЂРёС‚СЊ СЃСЃС‹Р»РєРё Р·Р°РєРѕРЅРѕРІ."));
    return;
  }
  const detailsHost = document.getElementById("law-sources-validation");
  if (detailsHost) {
    const invalidUrls = Array.isArray(payload?.invalid_urls) ? payload.invalid_urls : [];
    const invalidDetails = Array.isArray(payload?.invalid_details) ? payload.invalid_details : [];
    const duplicateUrls = Array.isArray(payload?.duplicate_urls) ? payload.duplicate_urls : [];
    const invalidBlock = invalidDetails.length
      ? `<br><strong>РќРµРІР°Р»РёРґРЅС‹Рµ СЃСЃС‹Р»РєРё:</strong><br>${invalidDetails
        .map((item) => `${escapeHtml(String(item?.url || ""))} (${escapeHtml(String(item?.reason || "invalid"))})`)
        .join("<br>")}`
      : (invalidUrls.length
        ? `<br><strong>РќРµРІР°Р»РёРґРЅС‹Рµ СЃСЃС‹Р»РєРё:</strong><br>${invalidUrls.map((item) => escapeHtml(String(item))).join("<br>")}`
        : "");
    const duplicateBlock = duplicateUrls.length
      ? `<br><strong>Р”СѓР±Р»РёРєР°С‚С‹ (РїРѕСЃР»Рµ РЅРѕСЂРјР°Р»РёР·Р°С†РёРё):</strong><br>${duplicateUrls.map((item) => escapeHtml(String(item))).join("<br>")}`
      : "";
    detailsHost.innerHTML = `РџСЂРёРЅСЏС‚Рѕ: ${escapeHtml(String(payload?.accepted_count ?? 0))}. Р”СѓР±Р»РёРєР°С‚РѕРІ: ${escapeHtml(String(payload?.duplicate_count ?? 0))}. РќРµРІР°Р»РёРґРЅС‹С…: ${escapeHtml(String(payload?.invalid_count ?? 0))}.${invalidBlock}${duplicateBlock}`;
  }
  showMessage("РџСЂРѕРІРµСЂРєР° СЃСЃС‹Р»РѕРє РІС‹РїРѕР»РЅРµРЅР°.");
}

async function syncLawSourcesFromServerConfig() {
  const response = await apiFetch(withLawServerQuery("/api/admin/law-sources/sync"), {
    method: "POST",
    body: JSON.stringify({}),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРёРЅС…СЂРѕРЅРёР·РёСЂРѕРІР°С‚СЊ СЃСЃС‹Р»РєРё Р·Р°РєРѕРЅРѕРІ."));
    return;
  }
  showMessage(payload?.changed ? "РЎСЃС‹Р»РєРё Р·Р°РєРѕРЅРѕРІ РїРµСЂРµРЅРµСЃРµРЅС‹ РёР· server config РІ DB." : "DB-РёСЃС‚РѕС‡РЅРёРєРё Р·Р°РєРѕРЅРѕРІ СѓР¶Рµ Р°РєС‚СѓР°Р»СЊРЅС‹.");
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
      host.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ Р¶СѓСЂРЅР°Р» РёР·РјРµРЅРµРЅРёР№."))}</p>`;
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
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РїСЂРµРґРїСЂРѕСЃРјРѕС‚СЂ catalog."));
    return;
  }
  renderCatalogPreview(payload, itemId);
}
function slugifyCatalogKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_\-.Р В°-РЎРЏРЎ']/gi, "")
    .replace(/_+/g, "_");
}

function getCatalogEntityFieldMeta(entityType) {
  const sharedHelp = "Р—Р°РїРѕР»РЅРёС‚Рµ РїРѕР»СЏ С„РѕСЂРјС‹. JSON РЅСѓР¶РµРЅ С‚РѕР»СЊРєРѕ РґР»СЏ СЂРµРґРєРёС…/РЅРµСЃС‚Р°РЅРґР°СЂС‚РЅС‹С… Р°С‚СЂРёР±СѓС‚РѕРІ.";
  const byEntity = {
    servers: {
      description: "РџСЂРѕС„РёР»СЊ СЃРµСЂРІРµСЂР°: РјРѕРґРµР»СЊ, URL Рё С‚РµС…РЅРёС‡РµСЃРєРёРµ РѕРіСЂР°РЅРёС‡РµРЅРёСЏ.",
      fields: [
        { name: "server_code", label: "РљРѕРґ СЃРµСЂРІРµСЂР°", placeholder: "prod-1", help: "РЈРЅРёРєР°Р»СЊРЅС‹Р№ РєРѕРґ РѕРєСЂСѓР¶РµРЅРёСЏ." },
        { name: "base_url", label: "Base URL", placeholder: "https://api.example.com", help: "Р‘Р°Р·РѕРІС‹Р№ URL СЃРµСЂРІРµСЂР°/РёРЅС‚РµРіСЂР°С†РёРё." },
        { name: "timeout_sec", label: "Timeout (СЃРµРє)", type: "number", min: 1, placeholder: "30", help: "РўР°Р№РјР°СѓС‚ Р·Р°РїСЂРѕСЃРѕРІ РІ СЃРµРєСѓРЅРґР°С…." },
      ],
    },
    laws: {
      description: "РќРѕСЂРјР°С‚РёРІРЅС‹Р№ РёСЃС‚РѕС‡РЅРёРє Рё РµРіРѕ СЂРµРєРІРёР·РёС‚С‹.",
      fields: [
        { name: "law_code", label: "РљРѕРґ Р·Р°РєРѕРЅР°", placeholder: "uk_rf_2026", help: "Р’РЅСѓС‚СЂРµРЅРЅРёР№ РєРѕРґ Р·Р°РєРѕРЅР°/СЃР±РѕСЂРЅРёРєР°." },
        { name: "source", label: "РСЃС‚РѕС‡РЅРёРє", placeholder: "consultant", help: "РћС‚РєСѓРґР° РІР·СЏС‚ С‚РµРєСЃС‚ (СЃРµСЂРІРёСЃ/СЂРµРµСЃС‚СЂ)." },
        { name: "effective_from", label: "Р”РµР№СЃС‚РІСѓРµС‚ СЃ", placeholder: "2026-01-01", help: "Р”Р°С‚Р° РІ С„РѕСЂРјР°С‚Рµ YYYY-MM-DD." },
      ],
    },
    templates: {
      description: "РЁР°Р±Р»РѕРЅ РґРѕРєСѓРјРµРЅС‚Р°: С„РѕСЂРјР°С‚, С†РµР»СЊ Рё РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Рµ Р±Р»РѕРєРё.",
      fields: [
        { name: "template_type", label: "РўРёРї С€Р°Р±Р»РѕРЅР°", placeholder: "complaint", help: "РќР°РїСЂРёРјРµСЂ: complaint, appeal, rehab." },
        { name: "document_kind", label: "Р’РёРґ РґРѕРєСѓРјРµРЅС‚Р°", placeholder: "Р–Р°Р»РѕР±Р°", help: "Р§РµР»РѕРІРµРєРѕС‡РёС‚Р°РµРјС‹Р№ РІРёРґ РґРѕРєСѓРјРµРЅС‚Р°." },
        { name: "output_format", label: "Р¤РѕСЂРјР°С‚ РІС‹РІРѕРґР°", placeholder: "bbcode", help: "РќР°РїСЂРёРјРµСЂ: bbcode, markdown, html." },
      ],
    },
    features: {
      description: "Р¤РёС‡Р°-С„Р»Р°Рі: rollout Рё СѓСЃР»РѕРІРёСЏ РІРєР»СЋС‡РµРЅРёСЏ.",
      fields: [
        { name: "feature_flag", label: "Feature flag", placeholder: "new_law_qa", help: "РЈРЅРёРєР°Р»СЊРЅС‹Р№ РєРѕРґ С„Р»Р°РіР°." },
        { name: "rollout_percent", label: "Rollout (%)", type: "number", min: 0, max: 100, placeholder: "25", help: "Р”РѕР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№ РІ РїСЂРѕС†РµРЅС‚Р°С…." },
        { name: "audience", label: "РђСѓРґРёС‚РѕСЂРёСЏ", placeholder: "testers", help: "РљРѕРјСѓ РІРєР»СЋС‡РµРЅРѕ: all/testers/staff/..." },
      ],
    },
    rules: {
      description: "РџСЂР°РІРёР»Рѕ РїСЂРёРјРµРЅРµРЅРёСЏ: РїСЂРёРѕСЂРёС‚РµС‚, РѕР±Р»Р°СЃС‚СЊ Рё РґРµР№СЃС‚РІРёРµ.",
      fields: [
        { name: "rule_type", label: "РўРёРї РїСЂР°РІРёР»Р°", placeholder: "moderation", help: "РљР°С‚РµРіРѕСЂРёСЏ РїСЂР°РІРёР»Р°." },
        { name: "priority", label: "РџСЂРёРѕСЂРёС‚РµС‚", type: "number", min: 0, placeholder: "100", help: "Р§РµРј Р±РѕР»СЊС€Рµ С‡РёСЃР»Рѕ, С‚РµРј РІС‹С€Рµ РїСЂРёРѕСЂРёС‚РµС‚." },
        { name: "applies_to", label: "РћР±Р»Р°СЃС‚СЊ", placeholder: "complaint_generation", help: "Р“РґРµ РїСЂРёРјРµРЅСЏРµС‚СЃСЏ РїСЂР°РІРёР»Рѕ." },
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
    throw new Error("Advanced JSON РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РѕР±СЉРµРєС‚РѕРј.");
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
      <h3>${seed.id ? "Р РµРґР°РєС‚РёСЂРѕРІР°РЅРёРµ" : "РЎРѕР·РґР°РЅРёРµ"}: ${escapeHtml(entityType)}</h3>
      <p class="legal-field__hint">${escapeHtml(meta.description || "")}</p>
      <label class="legal-field">
        <span class="legal-field__label">РќР°Р·РІР°РЅРёРµ</span>
        <input type="text" name="title" value="${escapeHtml(values.title)}" placeholder="РџРѕРЅСЏС‚РЅРѕРµ РёРјСЏ Р·Р°РїРёСЃРё" required>
      </label>
      <label class="legal-field">
        <span class="legal-field__label">РљР»СЋС‡</span>
        <input type="text" name="key" value="${escapeHtml(values.key)}" placeholder="server_main" required>
        <span class="legal-field__hint">РЈРЅРёРєР°Р»СЊРЅС‹Р№ РєР»СЋС‡ (Р»Р°С‚РёРЅРёС†Р°/С†РёС„СЂС‹/РїРѕРґС‡РµСЂРєРёРІР°РЅРёРµ). РџСЂРёРјРµСЂ: <code>main_ruleset</code></span>
      </label>
      <label class="legal-field">
        <span class="legal-field__label">РћРїРёСЃР°РЅРёРµ</span>
        <textarea name="description" rows="2" placeholder="РљСЂР°С‚РєРѕ: Р·Р°С‡РµРј РЅСѓР¶РЅР° Р·Р°РїРёСЃСЊ">${escapeHtml(values.description)}</textarea>
      </label>
      <label class="legal-field">
        <span class="legal-field__label">РЎС‚Р°С‚СѓСЃ</span>
        <select name="status">
          ${["draft", "review", "published", "active", "disabled", "archived"]
            .map((statusName) => `<option value="${statusName}" ${values.status === statusName ? "selected" : ""}>${statusName}</option>`)
            .join("")}
        </select>
        <span class="legal-field__hint">РћР±С‹С‡РЅРѕ РґР»СЏ РЅРѕРІС‹С… Р·Р°РїРёСЃРµР№ РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ <code>draft</code>.</span>
      </label>
      ${dynamicFields}
      <details>
        <summary>Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ (JSON)</summary>
        <p class="legal-field__hint">РћРїС†РёРѕРЅР°Р»СЊРЅРѕ. Р”РѕР±Р°РІСЊС‚Рµ СЂРµРґРєРёРµ РїРѕР»СЏ РІ JSON-РѕР±СЉРµРєС‚Рµ, РЅР°РїСЂРёРјРµСЂ: {\"tags\":[\"beta\"],\"owner\":\"team-legal\"}</p>
        <label class="legal-field">
          <textarea name="advanced_config" rows="7" placeholder='{\"tags\":[\"beta\"],\"owner\":\"team-legal\"}'>${escapeHtml(JSON.stringify(values.config || {}, null, 2))}</textarea>
        </label>
      </details>
      <menu style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px;">
        <button type="button" class="ghost-button" data-action="cancel">РћС‚РјРµРЅР°</button>
        <button type="submit" class="primary-button" data-action="submit">РЎРѕС…СЂР°РЅРёС‚СЊ</button>
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
          throw new Error("РџРѕР»Рµ В«РќР°Р·РІР°РЅРёРµВ» РѕР±СЏР·Р°С‚РµР»СЊРЅРѕ.");
        }
        if (!key) {
          throw new Error("РџРѕР»Рµ В«РљР»СЋС‡В» РѕР±СЏР·Р°С‚РµР»СЊРЅРѕ.");
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
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ catalog."));
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
    return "-";
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
      return { ok: false, message: "РќРµ СѓРґР°Р»РѕСЃСЊ СЂР°Р·РѕР±СЂР°С‚СЊ JSON. РџСЂРѕРІРµСЂСЊС‚Рµ СЃРёРЅС‚Р°РєСЃРёСЃ." };
    }
    const index = Number(match[1]);
    const boundedIndex = Number.isFinite(index) ? Math.max(0, Math.min(index, source.length)) : 0;
    const before = source.slice(0, boundedIndex);
    const line = before.split("\n").length;
    const column = boundedIndex - (before.lastIndexOf("\n") + 1) + 1;
    return {
      ok: false,
      message: `РќРµРєРѕСЂСЂРµРєС‚РЅС‹Р№ JSON: РѕС€РёР±РєР° РЅР° СЃС‚СЂРѕРєРµ ${line}, РїРѕР·РёС†РёСЏ ${column}.`,
    };
  }
}

function resetCatalogModalState() {
  pendingCatalogContext = null;
  if (catalogModalTitle) catalogModalTitle.textContent = "Р РµРґР°РєС‚РёСЂРѕРІР°РЅРёРµ РєР°С‚Р°Р»РѕРіР°";
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
  if (catalogPublishedHost) catalogPublishedHost.textContent = "вЂ”";
  if (catalogDraftHost) catalogDraftHost.textContent = "вЂ”";
  if (catalogSaveButton) {
    catalogSaveButton.hidden = false;
    catalogSaveButton.disabled = false;
    catalogSaveButton.textContent = "РЎРѕС…СЂР°РЅРёС‚СЊ";
  }
  if (catalogCancelButton) catalogCancelButton.textContent = "Р—Р°РєСЂС‹С‚СЊ";
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
    const baseTitle = mode === "view" ? "РџСЂРѕСЃРјРѕС‚СЂ СЌР»РµРјРµРЅС‚Р°" : (config?.isCreate ? "РЎРѕР·РґР°РЅРёРµ СЌР»РµРјРµРЅС‚Р°" : "Р РµРґР°РєС‚РёСЂРѕРІР°РЅРёРµ СЌР»РµРјРµРЅС‚Р°");
    catalogModalTitle.textContent = `${baseTitle}: ${String(item.title || "").trim() || "Р±РµР· РЅР°Р·РІР°РЅРёСЏ"}`;
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
      extractVersionPayload(publishedVersion) ?? "РћРїСѓР±Р»РёРєРѕРІР°РЅРЅР°СЏ РІРµСЂСЃРёСЏ РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚."
    );
  }
  if (catalogDraftHost) {
    catalogDraftHost.textContent = formatJsonForDisplay(
      extractVersionPayload(draftVersion) ?? "Р§РµСЂРЅРѕРІРёРє РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚."
    );
  }
  if (catalogSaveButton) {
    catalogSaveButton.hidden = mode === "view";
    catalogSaveButton.disabled = false;
  }
  if (catalogCancelButton) {
    catalogCancelButton.textContent = mode === "view" ? "Р—Р°РєСЂС‹С‚СЊ" : "РћС‚РјРµРЅР°";
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
    setStateError(catalogModalErrors, "РЈРєР°Р¶РёС‚Рµ РЅР°Р·РІР°РЅРёРµ СЌР»РµРјРµРЅС‚Р°.");
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
      setStateError(catalogModalErrors, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ СЌР»РµРјРµРЅС‚."));
      if (catalogSaveButton) catalogSaveButton.disabled = false;
      return;
    }
    showMessage(isCreate ? "Р­Р»РµРјРµРЅС‚ СЃРѕР·РґР°РЅ." : "Р­Р»РµРјРµРЅС‚ РѕР±РЅРѕРІР»РµРЅ.");
    closeCatalogModal();
    await loadCatalog(activeCatalogEntity);
  } catch (error) {
    setStateError(catalogModalErrors, error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ СЌР»РµРјРµРЅС‚.");
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
    [/^\/api\/admin\/users\/[^/]+\/deactivate$/, "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ РјСЏРіРєРѕ РґРµР°РєС‚РёРІРёСЂСѓРµС‚ Р°РєРєР°СѓРЅС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ."],
    [/^\/api\/admin\/users\/[^/]+\/reactivate$/, "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ СЃРЅРёРјР°РµС‚ РґРµР°РєС‚РёРІР°С†РёСЋ Р°РєРєР°СѓРЅС‚Р°."],
    [/^\/api\/admin\/users\/[^/]+\/daily-quota$/, "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ Р·Р°РґР°РµС‚ СЃСѓС‚РѕС‡РЅС‹Р№ Р»РёРјРёС‚ API РґР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ."],
    [/^\/api\/admin\/users\/bulk-actions$/, "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ Р·Р°РїСѓСЃРєР°РµС‚ РјР°СЃСЃРѕРІСѓСЋ РѕРїРµСЂР°С†РёСЋ РїРѕ РІС‹Р±СЂР°РЅРЅС‹Рј РїРѕР»СЊР·РѕРІР°С‚РµР»СЏРј."],
    [/^\/api\/admin\/tasks\/[^/]+$/, "РџСЂРѕРІРµСЂРєР° СЃС‚Р°С‚СѓСЃР° С„РѕРЅРѕРІРѕР№ Р·Р°РґР°С‡Рё Р°РґРјРёРЅ-РѕРїРµСЂР°С†РёР№."],
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
    admin_deactivate_user: "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ РґРµР°РєС‚РёРІРёСЂРѕРІР°Р» Р°РєРєР°СѓРЅС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ.",
    admin_reactivate_user: "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ СЃРЅСЏР» РґРµР°РєС‚РёРІР°С†РёСЋ Р°РєРєР°СѓРЅС‚Р°.",
    admin_set_daily_quota: "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ РѕР±РЅРѕРІРёР» СЃСѓС‚РѕС‡РЅСѓСЋ РєРІРѕС‚Сѓ API РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ.",
  };
  return descriptions[normalized] || "РЎРёСЃС‚РµРјРЅРѕРµ СЃРѕР±С‹С‚РёРµ Р±РµР· РґРѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕРіРѕ РѕРїРёСЃР°РЅРёСЏ.";
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
  if (riskScore >= 4) return renderBadge("Р РёСЃРє: РІС‹СЃРѕРєРёР№", "danger");
  if (riskScore >= 2) return renderBadge("Р РёСЃРє: СЃСЂРµРґРЅРёР№", "info");
  return renderBadge("Р В Р С‘РЎРѓР С”: Р Р…Р С‘Р В·Р С”Р С‘Р в„–", "success-soft");
}

function renderFilterChip(label, key) {
  return `
    <button type="button" class="admin-filter-chip" data-clear-filter="${escapeHtml(key)}">
      <span>${escapeHtml(label)}</span>
      <span class="admin-filter-chip__close" aria-hidden="true">Р“вЂ”</span>
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

function renderKeyValueField(label, value) {
  return `
    <div class="legal-field">
      <span class="legal-field__label">${escapeHtml(label)}</span>
      <div class="admin-user-cell__secondary">${escapeHtml(String(value || "-"))}</div>
    </div>
  `;
}

function compactLegacyRefValue(value) {
  const safeDash = "-";
  if (value === null || value === undefined || value === "") {
    return safeDash;
  }
  if (Array.isArray(value)) {
    const parts = value.map((item) => compactLegacyRefValue(item)).filter((item) => item && item !== safeDash);
    return parts.length ? parts.join(", ") : safeDash;
  }
  if (typeof value === "object") {
    const summaryParts = [];
    if (value.id) summaryParts.push(`id=${String(value.id)}`);
    if (value.version) summaryParts.push(`version=${String(value.version)}`);
    if (value.version_number) summaryParts.push(`version=${String(value.version_number)}`);
    if (value.hash) summaryParts.push(`hash=${String(value.hash)}`);
    if (value.code) summaryParts.push(`code=${String(value.code)}`);
    if (value.name) summaryParts.push(`name=${String(value.name)}`);
    if (value.title) summaryParts.push(`title=${String(value.title)}`);
    return summaryParts.length ? summaryParts.join(", ") : safeDash;
  }

  const normalized = String(value || "").trim();
  if (!normalized) {
    return safeDash;
  }
  if (!(normalized.startsWith("{") && normalized.endsWith("}"))) {
    return normalized;
  }

  const matches = [
    [/['"]id['"]:\s*['"]([^'"]+)['"]/i, "id"],
    [/['"]version(?:_number)?['"]:\s*['"]?([^,'"}\]]+)['"]?/i, "version"],
    [/['"]hash['"]:\s*['"]([^'"]+)['"]/i, "hash"],
    [/['"]code['"]:\s*['"]([^'"]+)['"]/i, "code"],
    [/['"]name['"]:\s*['"]([^'"]+)['"]/i, "name"],
    [/['"]title['"]:\s*['"]([^'"]+)['"]/i, "title"],
  ];
  const extracted = matches
    .map(([pattern, key]) => {
      const match = normalized.match(pattern);
      return match?.[1] ? `${key}=${match[1]}` : "";
    })
    .filter(Boolean);
  return extracted.length ? extracted.join(", ") : normalized;
}

function renderNormalizedKeyValueField(label, value) {
  return renderKeyValueField(label, compactLegacyRefValue(value));
}

function derivePilotRolloutState(featureFlags) {
  const items = Array.isArray(featureFlags) ? featureFlags : [];
  const adapter = items.find((item) => String(item?.flag || "") === "pilot_runtime_adapter_v1") || {};
  const shadow = items.find((item) => String(item?.flag || "") === "pilot_shadow_compare_v1") || {};
  const adapterActive = Boolean(adapter.use_new_flow);
  const shadowActive = Boolean(shadow.use_new_flow);
  if (adapterActive) {
    return "new_runtime_active";
  }
  if (shadowActive) {
    return "shadow_compare";
  }
  return "legacy_only";
}

function describePilotWarningSignal(eventType) {
  const key = String(eventType || "").trim();
  const catalog = {
    rollout_generation_latency: ["Generation latency", "info", "Compare recent generation timings with the pre-pilot baseline."],
    rollout_async_queue_lag: ["Async queue lag", "info", "Inspect queue backlog and confirm no retry storm is forming."],
    rollout_validation_fail_rate: ["Validation fail rate", "info", "Review recent validation failures before any rollout change."],
    rollout_error_rate: ["Rollout error rate", "danger-soft", "Investigate error spikes first; do not expand rollout while active."],
  };
  const [label, tone, action] = catalog[key] || [key || "Unknown signal", "info", "Classify this signal before changing rollout state."];
  return { label, tone, action };
}

function renderPilotRolloutMarkup(payload) {
  const data = payload?.data || payload || {};
  const featureFlags = Array.isArray(data.feature_flags) ? data.feature_flags : [];
  const rolloutState = derivePilotRolloutState(featureFlags);
  const rolloutTone = rolloutState === "new_runtime_active"
    ? "success-soft"
    : rolloutState === "shadow_compare"
      ? "info"
      : "muted";
  const adapter = featureFlags.find((item) => String(item?.flag || "") === "pilot_runtime_adapter_v1") || {};
  const shadow = featureFlags.find((item) => String(item?.flag || "") === "pilot_shadow_compare_v1") || {};
  const warningSignals = Array.isArray(data.warning_signals) ? data.warning_signals : [];
  const warningRows = warningSignals.map((item) => ({
    event_type: String(item?.event_type || ""),
    total: Number(item?.total || 0),
    ...describePilotWarningSignal(item?.event_type),
  }));
  const rollbackHistory = Array.isArray(data.rollback_history) ? data.rollback_history : [];
  const checklist = [
    {
      label: "Shadow compare enabled before cutover",
      status: rolloutState === "shadow_compare" || rolloutState === "new_runtime_active" ? "pass" : "warn",
      note: rolloutState === "legacy_only"
        ? "Pilot is still fully legacy-only."
        : "Shadow compare is available for pilot monitoring.",
    },
    {
      label: "No active rollout warning signals",
      status: warningSignals.length === 0 ? "pass" : "warn",
      note: warningSignals.length === 0
        ? "No warning signals recorded for the pilot server."
        : `${warningSignals.length} rollout warning signal(s) need review first.`,
    },
    {
      label: "Fallback remains low and explainable",
      status: Number(data.fallback_to_legacy_usage || 0) === 0 ? "pass" : "warn",
      note: `Fallback-to-legacy events: ${String(data.fallback_to_legacy_usage || 0)}.`,
    },
    {
      label: "Rollback path exists and is visible",
      status: "pass",
      note: `Rollback history entries visible: ${String(rollbackHistory.length || 0)}.`,
    },
    {
      label: "Admin provenance review is available",
      status: "pass",
      note: "Generated document review and provenance trace are visible in the same dashboard workspace.",
    },
  ];
  const actionHint = checklist.some((item) => item.status !== "pass")
    ? "Preflight gate is not clean yet: keep the pilot on legacy or shadow mode."
    : "Preflight gate looks clean: pilot activation can be considered if rollout owners agree.";

  return `
    <div class="admin-performance-grid">
      <article class="legal-status-card">
        <span class="legal-status-card__label">Pilot state</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${renderBadge(rolloutState, rolloutTone)}</strong>
        <span class="admin-user-cell__secondary">Derived from pilot adapter + shadow flags.</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Adapter mode</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(adapter.mode || "off"))}</strong>
        <span class="admin-user-cell__secondary">cohort=${escapeHtml(String(adapter.cohort || "default"))}, active=${escapeHtml(String(Boolean(adapter.use_new_flow)))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Shadow compare</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(shadow.mode || "off"))}</strong>
        <span class="admin-user-cell__secondary">cohort=${escapeHtml(String(shadow.cohort || "default"))}, active=${escapeHtml(String(Boolean(shadow.use_new_flow)))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Fallback / rollback</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(data.fallback_to_legacy_usage || 0))} / ${escapeHtml(String(rollbackHistory.length || 0))}</strong>
        <span class="admin-user-cell__secondary">fallback events / rollback batches</span>
      </article>
    </div>
    <div class="legal-field-grid legal-field-grid--two">
      <div class="legal-field">
        <span class="legal-field__label">Pilot flags</span>
        <div class="legal-table-shell">
          <table class="legal-table admin-table admin-table--compact">
            <thead><tr><th>Flag</th><th>Mode</th><th>Cohort</th><th>Active</th><th>Enforcement</th></tr></thead>
            <tbody>
              ${featureFlags
                .filter((item) => ["pilot_runtime_adapter_v1", "pilot_shadow_compare_v1"].includes(String(item?.flag || "")))
                .map((item) => `
                  <tr>
                    <td>${escapeHtml(String(item.flag || "вЂ”"))}</td>
                    <td>${escapeHtml(String(item.mode || "off"))}</td>
                    <td>${escapeHtml(String(item.cohort || "default"))}</td>
                    <td>${escapeHtml(String(Boolean(item.use_new_flow)))}</td>
                    <td>${escapeHtml(String(item.enforcement || "off"))}</td>
                  </tr>
                `)
                .join("")}
            </tbody>
          </table>
        </div>
      </div>
      <div class="legal-field">
        <span class="legal-field__label">Warning signals</span>
        ${
          warningRows.length
            ? `
              <div class="legal-table-shell">
                <table class="legal-table admin-table admin-table--compact">
                  <thead><tr><th>Signal</th><th>Status</th><th>Total</th><th>Next action</th></tr></thead>
                  <tbody>
                    ${warningRows
                      .map((item) => `
                        <tr>
                          <td>${escapeHtml(String(item.label || item.event_type || "-"))}</td>
                          <td>${renderBadge(item.tone === "danger-soft" ? "critical" : "review", item.tone)}</td>
                          <td>${escapeHtml(String(item.total || 0))}</td>
                          <td>${escapeHtml(String(item.action || "-"))}</td>
                        </tr>
                      `)
                      .join("")}
                  </tbody>
                </table>
              </div>
            `
            : '<div class="admin-user-cell__secondary">No rollout warning signals recorded for the pilot server.</div>'
        }
      </div>
    </div>
    <div class="legal-field">
      <span class="legal-field__label">Activation checklist</span>
      <div class="legal-table-shell">
        <table class="legal-table admin-table admin-table--compact">
          <thead><tr><th>Gate</th><th>Status</th><th>Note</th></tr></thead>
          <tbody>
            ${checklist
              .map((item) => `
                <tr>
                  <td>${escapeHtml(String(item.label || "вЂ”"))}</td>
                  <td>${renderBadge(item.status === "pass" ? "pass" : "review", item.status === "pass" ? "success-soft" : "info")}</td>
                  <td>${escapeHtml(String(item.note || "вЂ”"))}</td>
                </tr>
              `)
              .join("")}
          </tbody>
        </table>
      </div>
      <div class="admin-user-cell__secondary">${escapeHtml(actionHint)}</div>
    </div>
    <div class="legal-field">
      <span class="legal-field__label">Operator playbooks</span>
      <div class="legal-table-shell">
        <table class="legal-table admin-table admin-table--compact">
          <thead><tr><th>Use case</th><th>Reference</th><th>When to use</th></tr></thead>
          <tbody>
            <tr>
              <td>Preflight before any cutover</td>
              <td><code>PILOT_ACTIVATION_CHECKLIST.md</code></td>
              <td>Before enabling or expanding pilot runtime activation.</td>
            </tr>
            <tr>
              <td>Record rollout decision and observation window</td>
              <td><code>PILOT_CUTOVER_REPORT_TEMPLATE.md</code></td>
              <td>Immediately after a proceed, hold, or rollback decision.</td>
            </tr>
            <tr>
              <td>Prepare next server or procedure rollout</td>
              <td><code>SCALE_OUT_CHECKLIST_TEMPLATE.md</code></td>
              <td>After pilot observation is accepted and reuse starts.</td>
            </tr>
            <tr>
              <td>Log each observation-window review</td>
              <td><code>PILOT_OBSERVATION_LOG_TEMPLATE.md</code></td>
              <td>During steady-state monitoring before sign-off or rollback.</td>
            </tr>
            <tr>
              <td>Track legacy cleanup candidates</td>
              <td><code>LEGACY_DEPRECATION_CANDIDATES.md</code></td>
              <td>During observation and after rollback risk is low.</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="admin-user-cell__secondary">These playbooks stay read-only here; rollout changes still require explicit operator action.</div>
    </div>
    <div class="legal-field">
      <span class="legal-field__label">Observation guidance</span>
      <div class="legal-table-shell">
        <table class="legal-table admin-table admin-table--compact">
          <thead><tr><th>Checkpoint</th><th>Expected signal</th></tr></thead>
          <tbody>
            <tr>
              <td>Warning signals</td>
              <td>${warningSignals.length === 0 ? "No active warnings before continuing rollout." : `${warningSignals.length} warning signal(s) still need explanation.`}</td>
            </tr>
            <tr>
              <td>Fallback usage</td>
              <td>${escapeHtml(String(data.fallback_to_legacy_usage || 0))} fallback event(s) recorded for the current release view.</td>
            </tr>
            <tr>
              <td>Rollback readiness</td>
              <td>${escapeHtml(String(rollbackHistory.length || 0))} rollback batch reference(s) visible to operators.</td>
            </tr>
            <tr>
              <td>Review journal</td>
              <td>Use <code>PILOT_OBSERVATION_LOG_TEMPLATE.md</code> for every observation checkpoint until sign-off.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `;
}
function renderProvenanceTraceMarkup(trace) {
  if (!trace) {
    return '<p class="legal-section__description">Trace РЅРµ РЅР°Р№РґРµРЅ.</p>';
  }
  const config = trace.config || {};
  const ai = trace.ai || {};
  const retrieval = trace.retrieval || {};
  const validation = trace.validation || {};
  return `
    <div class="admin-performance-grid">
      <article class="legal-status-card">
        <span class="legal-status-card__label">Document version</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(trace.document_version_id || "вЂ”"))}</strong>
        <span class="admin-user-cell__secondary">${escapeHtml(String(trace.document_kind || "вЂ”"))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Server</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(trace.server_id || "вЂ”"))}</strong>
        <span class="admin-user-cell__secondary">Snapshot: ${escapeHtml(String(trace.generation_snapshot_id || "вЂ”"))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Generated at</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(trace.generation_timestamp || "вЂ”"))}</strong>
        <span class="admin-user-cell__secondary">Validation: ${escapeHtml(String(validation.latest_status || "вЂ”"))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Retrieval</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(retrieval.citations_count || 0))}</strong>
        <span class="admin-user-cell__secondary">Citations in final trace.</span>
      </article>
    </div>
    <div class="legal-field-grid legal-field-grid--two">
      <div class="legal-field">
        <span class="legal-field__label">Configuration lineage</span>
        <div class="legal-field-grid">
          ${renderNormalizedKeyValueField("Server config version", config.server_config_version)}
          ${renderNormalizedKeyValueField("Procedure version", config.procedure_version)}
          ${renderNormalizedKeyValueField("Template version", config.template_version)}
          ${renderNormalizedKeyValueField("Law set version", config.law_set_version)}
          ${renderNormalizedKeyValueField("Law version id", config.law_version_id)}
        </div>
      </div>
      <div class="legal-field">
        <span class="legal-field__label">Execution lineage</span>
        <div class="legal-field-grid">
          ${renderNormalizedKeyValueField("AI provider", ai.provider)}
          ${renderNormalizedKeyValueField("Model id", ai.model_id)}
          ${renderNormalizedKeyValueField("Prompt version", ai.prompt_version)}
          ${renderNormalizedKeyValueField("Retrieval run id", retrieval.retrieval_run_id)}
          ${renderKeyValueField("Citation ids", Array.isArray(retrieval.citation_ids) && retrieval.citation_ids.length ? retrieval.citation_ids.join(", ") : "вЂ”")}
          ${renderNormalizedKeyValueField("Latest validation run", validation.latest_run_id)}
        </div>
      </div>
    </div>
  `;
}

function renderRecentGeneratedDocumentsMarkup(payload) {
  const items = Array.isArray(payload?.items) ? payload.items : [];
  if (!items.length) {
    return '<p class="legal-section__description">РќРµРґР°РІРЅРёС… generated documents СЃРµР№С‡Р°СЃ РЅРµС‚.</p>';
  }
  return `
    <div class="legal-table-shell">
      <table class="legal-table admin-table admin-table--compact">
        <thead><tr><th>Doc ID</th><th>User</th><th>Server</th><th>Kind</th><th>Created</th><th>Trace</th></tr></thead>
        <tbody>
          ${items
            .map(
              (item) => `
                <tr>
                  <td>${escapeHtml(String(item.id || "вЂ”"))}</td>
                  <td>${escapeHtml(String(item.username || "вЂ”"))}</td>
                  <td>${escapeHtml(String(item.server_code || "вЂ”"))}</td>
                  <td>${escapeHtml(String(item.document_kind || "вЂ”"))}</td>
                  <td>${escapeHtml(String(item.created_at || "вЂ”"))}</td>
                  <td>
                    <button
                      type="button"
                      class="ghost-button"
                      data-provenance-generated-document-id="${escapeHtml(String(item.id || ""))}"
                    >
                      Inspect trace
                    </button>
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

function renderGeneratedDocumentContextMarkup(payload) {
  const generatedDocument = payload?.generated_document || {};
  const snapshotSummary = payload?.snapshot_summary || {};
  const documentVersion = payload?.document_version || {};
  const validationSummary = payload?.validation_summary || {};
  const workflowLinkage = payload?.workflow_linkage || {};
  const citationsSummary = payload?.citations_summary || {};
  const artifactSummary = payload?.artifact_summary || {};
  const citations = Array.isArray(citationsSummary.items) ? citationsSummary.items : [];
  const exports = Array.isArray(artifactSummary.exports) ? artifactSummary.exports : [];
  const attachments = Array.isArray(artifactSummary.attachments) ? artifactSummary.attachments : [];
  return `
    <div class="admin-performance-grid">
      <article class="legal-status-card">
        <span class="legal-status-card__label">Generated document</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(generatedDocument.id || "вЂ”"))}</strong>
        <span class="admin-user-cell__secondary">${escapeHtml(String(generatedDocument.document_kind || "вЂ”"))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Document version</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(documentVersion.id || "вЂ”"))}</strong>
        <span class="admin-user-cell__secondary">Version: ${escapeHtml(String(documentVersion.version_number || "вЂ”"))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Latest validation</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(validationSummary.latest_status || "вЂ”"))}</strong>
        <span class="admin-user-cell__secondary">Issues: ${escapeHtml(String(validationSummary.issues_count || 0))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Snapshot</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(generatedDocument.generation_snapshot_id || "вЂ”"))}</strong>
        <span class="admin-user-cell__secondary">${escapeHtml(String(generatedDocument.created_at || "вЂ”"))}</span>
      </article>
    </div>
    <div class="admin-section-toolbar">
      <a class="ghost-button" href="/api/generated-documents/${encodeURIComponent(String(generatedDocument.id || ""))}/snapshot" target="_blank" rel="noreferrer">Open snapshot API</a>
      <a class="ghost-button" href="/api/document-versions/${encodeURIComponent(String(documentVersion.id || ""))}/validation" target="_blank" rel="noreferrer">Open validation API</a>
      <a class="ghost-button" href="/api/document-versions/${encodeURIComponent(String(documentVersion.id || ""))}/citations" target="_blank" rel="noreferrer">Open citations API</a>
      <a class="ghost-button" href="/api/document-versions/${encodeURIComponent(String(documentVersion.id || ""))}/exports" target="_blank" rel="noreferrer">Open exports API</a>
    </div>
    <div class="legal-field-grid legal-field-grid--two">
      <div class="legal-field">
        <span class="legal-field__label">Snapshot summary</span>
        <div class="legal-field-grid">
          ${renderNormalizedKeyValueField("Server", generatedDocument.server_code)}
          ${renderNormalizedKeyValueField("Procedure", snapshotSummary.procedure)}
          ${renderNormalizedKeyValueField("Template version", snapshotSummary.template_version)}
          ${renderNormalizedKeyValueField("Law version set", snapshotSummary.law_version_set)}
          ${renderNormalizedKeyValueField("Validation rules", snapshotSummary.validation_rules_version)}
          ${renderNormalizedKeyValueField("Prompt version", snapshotSummary.prompt_version)}
        </div>
      </div>
      <div class="legal-field">
        <span class="legal-field__label">Content preview</span>
        <div class="legal-table-shell">
          <pre class="admin-ops-log">${escapeHtml(String(documentVersion.bbcode_preview || "вЂ”"))}</pre>
        </div>
      </div>
    </div>
    <div class="legal-field">
      <span class="legal-field__label">Validation issue preview</span>
      ${
        Array.isArray(validationSummary.issues) && validationSummary.issues.length
          ? `
            <div class="legal-table-shell">
              <table class="legal-table admin-table admin-table--compact">
                <thead><tr><th>Code</th><th>Severity</th><th>Field</th><th>Message</th></tr></thead>
                <tbody>
                  ${validationSummary.issues
                    .map(
                      (item) => `
                        <tr>
                          <td>${escapeHtml(String(item.issue_code || "-"))}</td>
                          <td>${escapeHtml(String(item.severity || "-"))}</td>
                          <td>${escapeHtml(String(item.field_ref || "-"))}</td>
                          <td>${escapeHtml(String(item.message || "-"))}</td>
                        </tr>
                      `,
                    )
                    .join("")}
                </tbody>
              </table>
            </div>
          `
          : `<div class="admin-user-cell__secondary">Validation issues preview is empty for this document.</div>`
      }
    </div>
    <div class="legal-field">
      <span class="legal-field__label">Workflow linkage</span>
      <div class="legal-field-grid legal-field-grid--two">
        ${renderKeyValueField("Linkage mode", workflowLinkage.linkage_mode || "-")}
        ${renderKeyValueField("Direct catalog mapping", workflowLinkage.direct_catalog_mapping_available ? "yes" : "no")}
        ${renderNormalizedKeyValueField("Procedure ref", workflowLinkage.procedure_ref)}
        ${renderNormalizedKeyValueField("Template ref", workflowLinkage.template_ref)}
        ${renderNormalizedKeyValueField("Prompt version", workflowLinkage.prompt_version)}
        ${renderNormalizedKeyValueField("Server config version", workflowLinkage.server_config_version)}
        ${renderNormalizedKeyValueField("Law set version", workflowLinkage.law_set_version)}
        ${renderNormalizedKeyValueField("Validation run anchor", workflowLinkage.latest_validation_run_id)}
      </div>
      <div class="admin-user-cell__secondary">This block shows confirmed snapshot/workflow refs only. Direct change request linkage is not claimed yet.</div>
    </div>
    <div class="legal-field">
      <span class="legal-field__label">Citation drilldown</span>
      ${
        citations.length
          ? `
            <div class="legal-table-shell">
              <table class="legal-table admin-table admin-table--compact">
                <thead><tr><th>Ref</th><th>Usage</th><th>Excerpt</th></tr></thead>
                <tbody>
                  ${citations
                    .map(
                      (item) => `
                        <tr>
                          <td>${escapeHtml(String(item.canonical_ref || "-"))}</td>
                          <td>${escapeHtml(String(item.usage_type || "-"))}</td>
                          <td>${escapeHtml(String(item.quoted_text || "-"))}</td>
                        </tr>
                      `,
                    )
                    .join("")}
                </tbody>
              </table>
            </div>
          `
          : `<div class="admin-user-cell__secondary">No citations are linked in this review context yet. Total: ${escapeHtml(String(citationsSummary.count || 0))}</div>`
      }
    </div>
    <div class="legal-field-grid legal-field-grid--two">
      <div class="legal-field">
        <span class="legal-field__label">Export artifacts</span>
        ${
          exports.length
            ? `
              <div class="legal-table-shell">
                <table class="legal-table admin-table admin-table--compact">
                  <thead><tr><th>ID</th><th>Format</th><th>Status</th><th>Created</th></tr></thead>
                  <tbody>
                    ${exports
                      .map(
                        (item) => `
                          <tr>
                            <td>${escapeHtml(String(item.id || "-"))}</td>
                            <td>${escapeHtml(String(item.format || "-"))}</td>
                            <td>${escapeHtml(String(item.status || "-"))}</td>
                            <td>${escapeHtml(String(item.created_at || "-"))}</td>
                          </tr>
                        `,
                      )
                      .join("")}
                  </tbody>
                </table>
              </div>
            `
            : `<div class="admin-user-cell__secondary">No export artifacts yet. Total: ${escapeHtml(String(artifactSummary.exports_count || 0))}</div>`
        }
      </div>
      <div class="legal-field">
        <span class="legal-field__label">Attachments</span>
        ${
          attachments.length
            ? `
              <div class="legal-table-shell">
                <table class="legal-table admin-table admin-table--compact">
                  <thead><tr><th>ID</th><th>Filename</th><th>Status</th><th>Link</th></tr></thead>
                  <tbody>
                    ${attachments
                      .map(
                        (item) => `
                          <tr>
                            <td>${escapeHtml(String(item.id || "-"))}</td>
                            <td>${escapeHtml(String(item.filename || "-"))}</td>
                            <td>${escapeHtml(String(item.upload_status || "-"))}</td>
                            <td>${escapeHtml(String(item.link_type || "-"))}</td>
                          </tr>
                        `,
                      )
                      .join("")}
                  </tbody>
                </table>
              </div>
            `
            : `<div class="admin-user-cell__secondary">No attachments yet. Total: ${escapeHtml(String(artifactSummary.attachments_count || 0))}</div>`
        }
      </div>
    </div>
  `;
}

async function loadDocumentProvenanceTrace() {
  if (!provenanceTraceHost || !provenanceTraceVersionField || !provenanceTraceDocumentField) {
    return;
  }
  const versionId = Number(provenanceTraceVersionField.value || "0");
  const generatedDocumentId = Number(provenanceTraceDocumentField.value || "0");
  const hasVersionId = Number.isInteger(versionId) && versionId > 0;
  const hasGeneratedDocumentId = Number.isInteger(generatedDocumentId) && generatedDocumentId > 0;
  if (!hasVersionId && !hasGeneratedDocumentId) {
    setStateError(errorsHost, "РЈРєР°Р¶РёС‚Рµ РєРѕСЂСЂРµРєС‚РЅС‹Р№ document version id РёР»Рё generated document id.");
    provenanceTraceVersionField.focus();
    return;
  }
  clearMessage();
  setStateIdle(errorsHost);
  provenanceTraceLoadButton && (provenanceTraceLoadButton.disabled = true);
  renderLoadingState(provenanceTraceHost, { count: 4, compact: true });
  try {
    const endpoint = hasVersionId
      ? `/api/document-versions/${encodeURIComponent(String(versionId))}/provenance`
      : `/api/admin/generated-documents/${encodeURIComponent(String(generatedDocumentId))}/provenance`;
    const response = await apiFetch(endpoint);
    const payload = await parsePayload(response);
    if (!response.ok) {
      const targetLabel = hasVersionId ? `version #${versionId}` : `generated document #${generatedDocumentId}`;
      provenanceTraceHost.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, `РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ provenance trace РґР»СЏ ${targetLabel}.`))}</p>`;
      return;
    }
    provenanceTraceHost.innerHTML = renderProvenanceTraceMarkup(payload);
    showMessage(
      hasVersionId
        ? `Provenance trace РґР»СЏ document version #${versionId} Р·Р°РіСЂСѓР¶РµРЅ.`
        : `Provenance trace РґР»СЏ generated document #${generatedDocumentId} Р·Р°РіСЂСѓР¶РµРЅ.`,
    );
  } catch (error) {
    provenanceTraceHost.innerHTML = `<p class="legal-section__description">${escapeHtml(error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ provenance trace.")}</p>`;
  } finally {
    provenanceTraceLoadButton && (provenanceTraceLoadButton.disabled = false);
  }
}

async function loadRecentGeneratedDocuments({ silent = false } = {}) {
  if (!generatedDocumentsReviewHost) {
    return;
  }
  if (!silent) {
    renderLoadingState(generatedDocumentsReviewHost, { count: 4, compact: true });
  }
  try {
    const response = await apiFetch("/api/admin/generated-documents/recent?limit=8");
    const payload = await parsePayload(response);
    if (!response.ok) {
      generatedDocumentsReviewHost.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ recent generated documents."))}</p>`;
      return;
    }
    generatedDocumentsReviewHost.innerHTML = renderRecentGeneratedDocumentsMarkup(payload);
  } catch (error) {
    generatedDocumentsReviewHost.innerHTML = `<p class="legal-section__description">${escapeHtml(error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ recent generated documents.")}</p>`;
  }
}

async function loadGeneratedDocumentReviewContext(documentId) {
  if (!generatedDocumentContextHost) {
    return;
  }
  const normalizedId = Number(documentId || "0");
  if (!Number.isInteger(normalizedId) || normalizedId <= 0) {
    generatedDocumentContextHost.innerHTML = '<p class="legal-section__description">Р’С‹Р±РµСЂРёС‚Рµ РєРѕСЂСЂРµРєС‚РЅС‹Р№ generated document.</p>';
    return;
  }
  renderLoadingState(generatedDocumentContextHost, { count: 4, compact: true });
  try {
    const response = await apiFetch(`/api/admin/generated-documents/${encodeURIComponent(String(normalizedId))}/review-context`);
    const payload = await parsePayload(response);
    if (!response.ok) {
      generatedDocumentContextHost.innerHTML = `<p class="legal-section__description">${escapeHtml(formatHttpError(response, payload, `РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ review context РґР»СЏ generated document #${normalizedId}.`))}</p>`;
      return;
    }
    generatedDocumentContextHost.innerHTML = renderGeneratedDocumentContextMarkup(payload);
  } catch (error) {
    generatedDocumentContextHost.innerHTML = `<p class="legal-section__description">${escapeHtml(error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ review context.")}</p>`;
  }
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
      setStateError(errorsHost, formatHttpError(response, payload, `РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РїСѓСЃС‚РёС‚СЊ synthetic suite ${normalizedSuite}.`));
      return;
    }
    showMessage(`Synthetic suite ${normalizedSuite} Р·Р°РІРµСЂС€РµРЅ: ${String(payload?.status || "unknown")}.`);
    await loadAdminOverview({ silent: true });
  } catch (error) {
    setStateError(errorsHost, error?.message || `РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РїСѓСЃС‚РёС‚СЊ synthetic suite ${normalizedSuite}.`);
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
  if (filters.event_type) chips.push(renderFilterChip(`Р СћР С‘Р С—: ${filters.event_type}`, "event_type"));
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
    user.deactivated_at ? renderBadge("Р”РµР°РєС‚РёРІРёСЂРѕРІР°РЅ", "danger") : null,
    user.is_tester ? renderBadge("РўРµСЃС‚РµСЂ", "info") : renderBadge("РћР±С‹С‡РЅС‹Р№", "neutral"),
    user.is_gka ? renderBadge("Р“РљРђ-Р—Р“РљРђ", "info") : null,
    Number(user.api_quota_daily || 0) > 0 ? renderBadge(`РљРІРѕС‚Р°/РґРµРЅСЊ: ${Number(user.api_quota_daily || 0)}`, "info") : renderBadge("РљРІРѕС‚Р°: Р±РµР· Р»РёРјРёС‚Р°", "muted"),
    riskLabel(user),
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
    userModalTitle.textContent = `Р Р°Р·Р±РѕСЂ РѕС‚РІРµС‚Р° В· СЃС‚СЂРѕРєР° ${entry.source_row || "вЂ”"}`;
  }

  userModalBody.innerHTML = `
    <div class="legal-status-row legal-status-row--three">
      <article class="legal-status-card">
        <span class="legal-status-card__label">РЎС‚СЂРѕРєР°</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(entry.source_row || "вЂ”"))}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">РљР°РЅРґРёРґР°С‚</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(entry.full_name || "вЂ”")}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">РЎСЂРµРґРЅРёР№ Р±Р°Р»Р»</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatExamAverage(entry))}</strong>
      </article>
    </div>

    <div class="legal-status-row legal-status-row--three">
      <article class="legal-status-card">
        <span class="legal-status-card__label">Р¤РѕСЂРјР°С‚</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(entry.exam_format || "вЂ”")}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">РћС‚РІРµС‚РѕРІ</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(entry.answer_count || 0))}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">РћР±РЅРѕРІР»РµРЅРѕ</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(entry.updated_at || entry.imported_at || "вЂ”")}</strong>
      </article>
    </div>

    <div id="admin-exam-detail-score" class="legal-subcard" hidden></div>

    <section class="legal-subcard admin-user-detail-card">
      <div class="legal-subcard__header">
        <div>
          <span class="legal-field__label">РСЃС…РѕРґРЅС‹Рµ РїРѕР»СЏ СЃС‚СЂРѕРєРё</span>
          <p class="legal-section__description">РќРёР¶Рµ РІРёРґРЅРѕ, РєР°РєРёРµ РґР°РЅРЅС‹Рµ РїСЂРёС€Р»Рё РёР· С‚Р°Р±Р»РёС†С‹ Рё СЃ С‡РµРј СЃСЂР°РІРЅРёРІР°Р»Р°СЃСЊ РїСЂРѕРІРµСЂРєР°.</p>
        </div>
      </div>
      <div class="legal-table-shell exam-detail-shell exam-detail-shell--payload">
        <table class="legal-table admin-table admin-table--compact exam-detail-table exam-detail-table--payload">
          <thead>
            <tr>
              <th>РЎС‚РѕР»Р±РµС† / РџРѕР»Рµ</th>
              <th>Р—РЅР°С‡РµРЅРёРµ</th>
            </tr>
          </thead>
          <tbody id="admin-exam-detail-body">
            <tr>
              <td colspan="2" class="legal-table__empty">Р”Р°РЅРЅС‹Рµ СЃС‚СЂРѕРєРё Р·Р°РіСЂСѓР¶РµРЅС‹.</td>
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
    setStateError(errorsHost, "РќРµ СѓРґР°Р»РѕСЃСЊ РѕРїСЂРµРґРµР»РёС‚СЊ СЃС‚СЂРѕРєСѓ СЌРєР·Р°РјРµРЅР° РґР»СЏ СЂР°Р·Р±РѕСЂР°.");
    return;
  }

  try {
    const response = await apiFetch(`/api/exam-import/rows/${encodeURIComponent(normalizedSourceRow)}`);
    const payload = await parsePayload(response);
    if (!response.ok) {
      setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЂР°Р·Р±РѕСЂ РѕС‚РІРµС‚Р°."));
      return;
    }
    selectedUser = null;
    renderExamEntryDetailModal(payload);
    userModal.open();
  } catch (error) {
    setStateError(errorsHost, error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЂР°Р·Р±РѕСЂ РѕС‚РІРµС‚Р°.");
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
        setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ AI Pipeline."));
      }
      return;
    }
    renderAiPipeline(payload);
    const partialErrors = Array.isArray(payload?.partial_errors) ? payload.partial_errors : [];
    if (partialErrors.length && !silent) {
      const first = partialErrors[0] || {};
      const source = first.source ? `[${String(first.source)}] ` : "";
      const message = String(first.message || "").trim();
      setStateError(errorsHost, `AI Pipeline Р·Р°РіСЂСѓР¶РµРЅ С‡Р°СЃС‚РёС‡РЅРѕ (${partialErrors.length}). ${source}${message}`.trim());
    }
  } catch (error) {
    if (!silent) {
      setStateError(errorsHost, error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ AI Pipeline.");
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
        setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РёСЃС‚РѕСЂРёСЋ СЂРѕР»РµР№."));
      }
      return;
    }
    renderRoleHistory(payload);
  } catch (error) {
    if (!silent) {
      setStateError(errorsHost, error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РёСЃС‚РѕСЂРёСЋ СЂРѕР»РµР№.");
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
        setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РјРµС‚СЂРёРєРё РїСЂРѕРёР·РІРѕРґРёС‚РµР»СЊРЅРѕСЃС‚Рё."));
      }
      return;
    }
    const payload = await parsePayload(response);
    renderPerformance(payload);
  } catch (error) {
    if (!silent) {
      setStateError(errorsHost, error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РјРµС‚СЂРёРєРё РїСЂРѕРёР·РІРѕРґРёС‚РµР»СЊРЅРѕСЃС‚Рё.");
    }
  }
}

async function loadAdminAsyncJobs({ silent = false } = {}) {
  if (!asyncJobsHost) {
    return;
  }
  if (!silent) {
    renderLoadingState(asyncJobsHost, { count: 4, compact: true });
  }
  try {
    const response = await apiFetch("/api/admin/async-jobs/overview");
    const payload = await parsePayload(response);
    if (!response.ok) {
      if (!silent) {
        setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ async jobs overview."));
      }
      return;
    }
    asyncJobsHost.innerHTML = renderAsyncJobsMarkup(payload, {
      escapeHtml,
      renderAsyncJobActions(item) {
        const jobId = Number(item?.id || "0");
        const canonicalStatus = String(item?.canonical_status || "").trim().toLowerCase();
        if (!jobId) {
          return '<span class="admin-user-cell__secondary">РІР‚вЂќ</span>';
        }
        if (canonicalStatus === "failed") {
          return `<button type="button" class="ghost-button" data-async-job-action="retry" data-async-job-id="${escapeHtml(String(jobId))}">Retry</button>`;
        }
        if (canonicalStatus === "retry_scheduled") {
          return `<button type="button" class="ghost-button" data-async-job-action="cancel" data-async-job-id="${escapeHtml(String(jobId))}">Cancel retry</button>`;
        }
        return '<span class="admin-user-cell__secondary">РІР‚вЂќ</span>';
      },
    });
  } catch (error) {
    if (!silent) {
      setStateError(errorsHost, error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ async jobs overview.");
    }
  }
}

async function loadExamImportOps({ silent = false } = {}) {
  if (!examImportOpsHost) {
    return;
  }
  if (!silent) {
    renderLoadingState(examImportOpsHost, { count: 4, compact: true });
  }
  try {
    const response = await apiFetch("/api/admin/exam-import/overview");
    const payload = await parsePayload(response);
    if (!response.ok) {
      if (!silent) {
        setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ exam import ops overview."));
      }
      return;
    }
    examImportOpsHost.innerHTML = renderExamImportOpsMarkup(payload, { escapeHtml });
  } catch (error) {
    if (!silent) {
      setStateError(errorsHost, error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ exam import ops overview.");
    }
  }
}

async function loadPilotRollout({ silent = false } = {}) {
  if (!pilotRolloutHost) {
    return;
  }
  if (!silent) {
    renderLoadingState(pilotRolloutHost, { count: 3, compact: true });
  }
  try {
    const response = await apiFetch("/api/admin/dashboard/sections/release");
    const payload = await parsePayload(response);
    if (!response.ok) {
      if (!silent) {
        setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ pilot rollout state."));
      }
      return;
    }
    pilotRolloutHost.innerHTML = renderPilotRolloutMarkup(payload);
  } catch (error) {
    if (!silent) {
      setStateError(errorsHost, error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ pilot rollout state.");
    }
  }
}

async function handleAsyncJobAction(target) {
  const button = target.closest("[data-async-job-action]");
  if (!(button instanceof HTMLButtonElement)) {
    return;
  }
  const action = String(button.getAttribute("data-async-job-action") || "").trim().toLowerCase();
  const jobId = Number(button.getAttribute("data-async-job-id") || "0");
  if (!action || !jobId) {
    setStateError(errorsHost, "Р СњР Вµ РЎС“Р Т‘Р В°Р В»Р С•РЎРѓРЎРЉ Р С•Р С—РЎР‚Р ВµР Т‘Р ВµР В»Р С‘РЎвЂљРЎРЉ async job action.");
    return;
  }
  clearMessage();
  setStateIdle(errorsHost);
  button.disabled = true;
  try {
    const response = await apiFetch(`/api/jobs/${encodeURIComponent(String(jobId))}/${encodeURIComponent(action)}`, {
      method: "POST",
    });
    const payload = await parsePayload(response);
    if (!response.ok) {
      setStateError(errorsHost, formatHttpError(response, payload, `Р СњР Вµ РЎС“Р Т‘Р В°Р В»Р С•РЎРѓРЎРЉ Р Р†РЎвЂ№Р С—Р С•Р В»Р Р…Р С‘РЎвЂљРЎРЉ action ${action} Р Т‘Р В»РЎРЏ job #${jobId}.`));
      return;
    }
    showMessage(
      action === "retry"
        ? `Async job #${jobId} Р С—Р С•РЎРѓРЎвЂљР В°Р Р†Р В»Р ВµР Р…Р В° Р Р…Р В° РЎР‚РЎС“РЎвЂЎР Р…Р С•Р в„– retry.`
        : `Async job #${jobId} РЎРѓР Р…РЎРЏРЎвЂљР В° РЎРѓ Р С•РЎвЂЎР ВµРЎР‚Р ВµР Т‘Р С‘ Р С—Р С•Р Р†РЎвЂљР С•РЎР‚Р Р…Р С•Р в„– Р С—Р С•Р С—РЎвЂ№РЎвЂљР С”Р С‘.`,
    );
    await loadAdminAsyncJobs({ silent: true });
  } catch (error) {
    setStateError(errorsHost, error?.message || `Р СњР Вµ РЎС“Р Т‘Р В°Р В»Р С•РЎРѓРЎРЉ Р Р†РЎвЂ№Р С—Р С•Р В»Р Р…Р С‘РЎвЂљРЎРЉ action ${action} Р Т‘Р В»РЎРЏ job #${jobId}.`);
  } finally {
    button.disabled = false;
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
    setLiveStatus("Live: РІС‹РєР»СЋС‡РµРЅРѕ", "muted");
    return;
  }

  const intervalSeconds = Number(liveIntervalField?.value || 30);
  const safeIntervalMs = Math.max(10, intervalSeconds) * 1000;
  setLiveStatus(`Live: РёРЅС‚РµСЂРІР°Р» ${Math.max(10, intervalSeconds)}СЃ`, "info");

  adminLiveTimer = window.setInterval(async () => {
    if (document.hidden) {
      return;
    }
    await Promise.all([
      loadAdminOverview({ silent: true }),
      loadAdminPerformance({ silent: true }),
      loadAdminAsyncJobs({ silent: true }),
      loadLawJobsOverview(),
      loadExamImportOps({ silent: true }),
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
      setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕР»СѓС‡РёС‚СЊ СЃС‚Р°С‚СѓСЃ bulk-Р·Р°РґР°С‡Рё."));
      return;
    }
    const progress = payload.progress || {};
    if (statusHost) {
      statusHost.textContent = `Bulk: ${payload.status} (${progress.done || 0}/${progress.total || 0})`;
    }
    if (payload.status === "finished") {
      showMessage(`Bulk Р·Р°РІРµСЂС€РµРЅ: ok ${payload.result?.success_count || 0}, РѕС€РёР±РѕРє ${payload.result?.failed_count || 0}.`);
      selectedBulkUsers = new Set();
      await loadAdminOverview();
      return;
    }
    if (payload.status === "failed") {
      setStateError(errorsHost, payload.error || "Bulk-Р·Р°РґР°С‡Р° Р·Р°РІРµСЂС€РёР»Р°СЃСЊ РѕС€РёР±РєРѕР№.");
      return;
    }
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  setStateError(errorsHost, "РўР°Р№РјР°СѓС‚ РѕР¶РёРґР°РЅРёСЏ bulk-Р·Р°РґР°С‡Рё.");
}

async function runBulkAction() {
  const usernames = Array.from(selectedBulkUsers);
  if (!usernames.length) {
    setStateError(errorsHost, "Р’С‹Р±РµСЂРёС‚Рµ С…РѕС‚СЏ Р±С‹ РѕРґРЅРѕРіРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РґР»СЏ РјР°СЃСЃРѕРІРѕР№ РѕРїРµСЂР°С†РёРё.");
    return;
  }
  const action = String(document.getElementById("admin-bulk-action")?.value || "").trim();
  if (!action) {
    setStateError(errorsHost, "Р’С‹Р±РµСЂРёС‚Рµ РјР°СЃСЃРѕРІРѕРµ РґРµР№СЃС‚РІРёРµ.");
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
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РїСѓСЃС‚РёС‚СЊ bulk-РѕРїРµСЂР°С†РёСЋ."));
    return;
  }
  showMessage("Bulk-Р·Р°РґР°С‡Р° РґРѕР±Р°РІР»РµРЅР° РІ РѕС‡РµСЂРµРґСЊ.");
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
    if (statusHost) statusHost.textContent = `Р’С‹Р±СЂР°РЅРѕ: ${selectedBulkUsers.size}`;
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
    if (statusHost) statusHost.textContent = `Р’С‹Р±СЂР°РЅРѕ: ${selectedBulkUsers.size}`;
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
    await performAdminAction(catalogEndpoint(activeCatalogEntity), "Р­Р»РµРјРµРЅС‚ СЃРѕР·РґР°РЅ.", payload);
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
      setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЌР»РµРјРµРЅС‚ catalog."));
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
      setStateError(errorsHost, formatHttpError(itemResponse, itemPayload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЌР»РµРјРµРЅС‚ catalog."));
      return;
    }
    const payload = await openCatalogFormDialog(activeCatalogEntity, extractCatalogEditableData(itemPayload));
    if (!payload) return;
    const response = await apiFetch(catalogEndpoint(activeCatalogEntity, editId), {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    if (response.ok) showMessage("Р­Р»РµРјРµРЅС‚ РѕР±РЅРѕРІР»РµРЅ.");
    await loadCatalog(activeCatalogEntity);
    return;
  }
  const workflowItemId = target.getAttribute("data-catalog-workflow-item");
  if (workflowItemId) {
    const action = String(target.getAttribute("data-catalog-workflow-action") || "").trim().toLowerCase();
    const changeRequestId = Number(target.getAttribute("data-catalog-workflow-cr-id") || "0");
    if (!action || !changeRequestId) {
      setStateError(errorsHost, "РќРµ СѓРґР°Р»РѕСЃСЊ РѕРїСЂРµРґРµР»РёС‚СЊ РґРµР№СЃС‚РІРёРµ workflow: РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ change request.");
      return;
    }
    if (action === "validate") {
      clearMessage();
      setStateIdle(errorsHost);
      const response = await apiFetch(`/api/admin/change-requests/${encodeURIComponent(String(changeRequestId))}/validate`);
      const payload = await parsePayload(response);
      if (!response.ok) {
        setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРѕРІРµСЂРёС‚СЊ С‡РµСЂРЅРѕРІРёРє."));
        return;
      }
      const result = payload?.result || {};
      const validationErrors = Array.isArray(result?.errors) ? result.errors.filter(Boolean) : [];
      if (result?.ok) {
        showMessage(`Р§РµСЂРЅРѕРІРёРє #${changeRequestId} РїСЂРѕС€РµР» РІР°Р»РёРґР°С†РёСЋ Рё РіРѕС‚РѕРІ Рє РѕС‚РїСЂР°РІРєРµ РЅР° СЂРµРІСЊСЋ.`);
      } else {
        setStateError(
          errorsHost,
          `Р§РµСЂРЅРѕРІРёРє #${changeRequestId} РЅРµ РїСЂРѕС€РµР» РІР°Р»РёРґР°С†РёСЋ: ${validationErrors.join("; ") || "РµСЃС‚СЊ РѕС€РёР±РєРё РєРѕРЅС‚СЂР°РєС‚Р°."}`,
        );
      }
      return;
    }
    await performAdminAction(`${catalogEndpoint(activeCatalogEntity, workflowItemId)}/workflow`, "Workflow РѕР±РЅРѕРІР»РµРЅ.", {
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
      showMessage("JSON СЃРєРѕРїРёСЂРѕРІР°РЅ.");
    } catch {
      showMessage("РќРµ СѓРґР°Р»РѕСЃСЊ СЃРєРѕРїРёСЂРѕРІР°С‚СЊ JSON.");
    }
    return;
  }
  const rollbackId = target.getAttribute("data-catalog-rollback");
  if (rollbackId) {
    const version = Number(window.prompt("Rollback to version", "1") || "1");
    await performAdminAction(`${catalogEndpoint(activeCatalogEntity, rollbackId)}/rollback`, "Rollback РІС‹РїРѕР»РЅРµРЅ.", { version });
    await loadCatalog(activeCatalogEntity);
    return;
  }
  const deleteId = target.getAttribute("data-catalog-delete");
  if (deleteId) {
    const response = await apiFetch(catalogEndpoint(activeCatalogEntity, deleteId), { method: "DELETE" });
    if (response.ok) showMessage("Р­Р»РµРјРµРЅС‚ СѓРґР°Р»РµРЅ.");
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
    loadAdminAsyncJobs(),
    loadLawJobsOverview(),
    loadExamImportOps(),
    loadPilotRollout(),
    loadRecentGeneratedDocuments({ silent: true }),
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
asyncJobsHost?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  await handleAsyncJobAction(target);
});
provenanceTraceForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  await loadDocumentProvenanceTrace();
});
generatedDocumentsReviewHost?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const button = target.closest("[data-provenance-generated-document-id]");
  if (!(button instanceof HTMLButtonElement) || !provenanceTraceDocumentField) {
    return;
  }
  provenanceTraceVersionField && (provenanceTraceVersionField.value = "");
  provenanceTraceDocumentField.value = String(button.getAttribute("data-provenance-generated-document-id") || "");
  await Promise.all([
    loadDocumentProvenanceTrace(),
    loadGeneratedDocumentReviewContext(provenanceTraceDocumentField.value),
  ]);
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
      loadAdminAsyncJobs({ silent: true }),
      loadLawJobsOverview(),
      loadExamImportOps({ silent: true }),
      loadPilotRollout({ silent: true }),
      loadRecentGeneratedDocuments({ silent: true }),
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
  loadAdminAsyncJobs(),
  loadLawJobsOverview(),
  loadExamImportOps(),
  loadPilotRollout(),
  loadRecentGeneratedDocuments(),
  loadAiPipeline(),
  loadRoleHistory(),
  loadCatalog(),
]).then(() => {
  scheduleLiveRefresh();
});
