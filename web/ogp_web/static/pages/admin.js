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
const catalogKeyInput = document.getElementById("admin-catalog-key");
const catalogDescriptionInput = document.getElementById("admin-catalog-description");
const catalogStatusInput = document.getElementById("admin-catalog-status");
const catalogTypedFieldsHost = document.getElementById("admin-catalog-typed-fields");
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
const DEFAULT_USER_MODAL_TITLE = userModalTitle?.textContent || "РљР°СЂС‚РѕС‡РєР° РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ";

let adminSearchTimer = null;
let adminLiveTimer = null;
let selectedUser = null;
let pendingAction = null;
let selectedBulkUsers = new Set();
const userIndex = new Map();
let activeCatalogEntity = String(catalogHost?.dataset.catalogEntity || "servers");
let activeSyntheticSuite = "";
let pendingCatalogContext = null;

function catalogEndpoint(entityType, itemId = "") {
  const suffix = itemId ? `/${encodeURIComponent(itemId)}` : "";
  return `/api/admin/catalog/${encodeURIComponent(entityType)}${suffix}`;
}

function slugifyCatalogKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_\-.Р°-СЏС‘]/gi, "")
    .replace(/_+/g, "_");
}

function getCatalogEntityFieldMeta(entityType) {
  const byEntity = {
    servers: {
      description: "РџСЂРѕС„РёР»СЊ СЃРµСЂРІРµСЂР°: РјРѕРґРµР»СЊ, URL Рё С‚РµС…РЅРёС‡РµСЃРєРёРµ РѕРіСЂР°РЅРёС‡РµРЅРёСЏ.",
      fields: [
        { name: "server_code", label: "РљРѕРґ СЃРµСЂРІРµСЂР°", placeholder: "blackberry", help: "РЈРЅРёРєР°Р»СЊРЅС‹Р№ РєРѕРґ РѕРєСЂСѓР¶РµРЅРёСЏ." },
        { name: "base_url", label: "Base URL", placeholder: "https://api.example.com", help: "Р‘Р°Р·РѕРІС‹Р№ URL СЃРµСЂРІРµСЂР° РёР»Рё РёРЅС‚РµРіСЂР°С†РёРё." },
        { name: "timeout_sec", label: "Timeout (СЃРµРє)", type: "number", min: 0, placeholder: "30", help: "РўР°Р№РјР°СѓС‚ Р·Р°РїСЂРѕСЃРѕРІ РІ СЃРµРєСѓРЅРґР°С…." },
      ],
    },
    laws: {
      description: "РќРѕСЂРјР°С‚РёРІРЅС‹Р№ РёСЃС‚РѕС‡РЅРёРє Рё РµРіРѕ СЂРµРєРІРёР·РёС‚С‹.",
      fields: [
        { name: "law_code", label: "РљРѕРґ Р·Р°РєРѕРЅР°", placeholder: "uk_rf_2026", help: "Р’РЅСѓС‚СЂРµРЅРЅРёР№ РєРѕРґ Р·Р°РєРѕРЅР° РёР»Рё СЃР±РѕСЂРЅРёРєР°." },
        { name: "source", label: "РСЃС‚РѕС‡РЅРёРє", placeholder: "consultant", help: "РћС‚РєСѓРґР° РІР·СЏС‚ С‚РµРєСЃС‚." },
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
        { name: "audience", label: "РђСѓРґРёС‚РѕСЂРёСЏ", placeholder: "testers", help: "РљРѕРјСѓ РІРєР»СЋС‡РµРЅРѕ." },
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
  return byEntity[entityType] || { description: "JSON-СЂРµР¶РёРј Р±РµР· С‚РёРїРёР·РёСЂРѕРІР°РЅРЅС‹С… РїРѕР»РµР№.", fields: [] };
}

function formatJsonForDisplay(value) {
  if (value === null || value === undefined) {
    return "вЂ”";
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

function extractVersionPayload(version) {
  if (!version || typeof version !== "object") return null;
  if (version.payload_json !== undefined) return version.payload_json;
  if (version.payload !== undefined) return version.payload;
  if (version.config !== undefined) return version.config;
  return null;
}

function renderCatalogTypedFields(entityType, seed = {}, disabled = false) {
  if (!catalogTypedFieldsHost) {
    }); }
    }); }
    return;
  }
  const meta = getCatalogEntityFieldMeta(entityType);
  catalogTypedFieldsHost.innerHTML = meta.fields
    .map((field) => {
      const type = field.type || "text";
      const value = String(seed[field.name] ?? "");
      const min = field.min !== undefined ? ` min="${field.min}"` : "";
      const max = field.max !== undefined ? ` max="${field.max}"` : "";
      return `
        <label class="legal-field admin-catalog-typed-field">
          <span class="legal-field__label">${escapeHtml(field.label)}</span>
          <input type="${escapeHtml(type)}" id="admin-catalog-field-${escapeHtml(field.name)}" data-catalog-field="${escapeHtml(field.name)}" value="${escapeHtml(value)}" placeholder="${escapeHtml(field.placeholder || "")}"${min}${max}${disabled ? " disabled" : ""}>
          <span class="legal-field__hint">${escapeHtml(field.help || "")}</span>
        </label>
      `;
    })
    .join("");
}

function resetCatalogModalState() {
  pendingCatalogContext = null;
  if (catalogModalTitle) catalogModalTitle.textContent = "Р РµРґР°РєС‚РёСЂРѕРІР°РЅРёРµ РєР°С‚Р°Р»РѕРіР°";
  if (catalogTitleInput) {
    catalogTitleInput.value = "";
    catalogTitleInput.disabled = false;
  }
  if (catalogKeyInput) {
    catalogKeyInput.value = "";
    catalogKeyInput.disabled = false;
  }
  if (catalogDescriptionInput) {
    catalogDescriptionInput.value = "";
    catalogDescriptionInput.disabled = false;
  }
  if (catalogStatusInput) {
    catalogStatusInput.value = "draft";
    catalogStatusInput.disabled = false;
  }
  renderCatalogTypedFields(activeCatalogEntity, {}, false);
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
  const publishedVersion = versions.find((version) => String(version?.id || "") === String(item?.current_published_version_id || ""));
  const latestVersion = versions.length ? versions[versions.length - 1] : null;
  const latestPayload = extractVersionPayload(latestVersion) || {};
  const publishedPayload = extractVersionPayload(publishedVersion) || {};
  const editableSeed = {
    title: String(item.title || ""),
    key: String(item.content_key || latestPayload.key || ""),
    description: String(latestPayload.description || ""),
    status: String(item.status || latestPayload.status || "draft"),
    ...latestPayload,
  };

  if (catalogModalTitle) {
    const baseTitle = mode === "view" ? "РџСЂРѕСЃРјРѕС‚СЂ СЌР»РµРјРµРЅС‚Р°" : (config?.isCreate ? "РЎРѕР·РґР°РЅРёРµ СЌР»РµРјРµРЅС‚Р°" : "Р РµРґР°РєС‚РёСЂРѕРІР°РЅРёРµ СЌР»РµРјРµРЅС‚Р°");
    catalogModalTitle.textContent = `${baseTitle}: ${String(item.title || "").trim() || activeCatalogEntity}`;
  }
  if (catalogTitleInput) {
    catalogTitleInput.value = editableSeed.title || "";
    catalogTitleInput.disabled = mode === "view";
  }
  if (catalogKeyInput) {
    catalogKeyInput.value = editableSeed.key || "";
    catalogKeyInput.disabled = mode === "view";
  }
  if (catalogDescriptionInput) {
    catalogDescriptionInput.value = editableSeed.description || "";
    catalogDescriptionInput.disabled = mode === "view";
  }
  if (catalogStatusInput) {
    catalogStatusInput.value = editableSeed.status || "draft";
    catalogStatusInput.disabled = mode === "view";
  }
  renderCatalogTypedFields(activeCatalogEntity, editableSeed, mode === "view");
  if (catalogJsonInput) {
    catalogJsonInput.value = formatJsonForDisplay(latestPayload);
    catalogJsonInput.disabled = mode === "view";
  }
  if (catalogPublishedHost) catalogPublishedHost.textContent = formatJsonForDisplay(publishedPayload || "РћРїСѓР±Р»РёРєРѕРІР°РЅРЅР°СЏ РІРµСЂСЃРёСЏ РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚.");
  if (catalogDraftHost) catalogDraftHost.textContent = formatJsonForDisplay(latestPayload || "Р§РµСЂРЅРѕРІРёРє РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚.");
  if (catalogSaveButton) {
    catalogSaveButton.hidden = mode === "view";
    catalogSaveButton.disabled = false;
  }
  if (catalogCancelButton) catalogCancelButton.textContent = mode === "view" ? "Р—Р°РєСЂС‹С‚СЊ" : "РћС‚РјРµРЅР°";
  catalogModal.open();
}

async function submitCatalogModal() {
  if (!pendingCatalogContext || pendingCatalogContext.mode === "view") {
    closeCatalogModal();
    return;
  }
  const title = String(catalogTitleInput?.value || "").trim();
  const key = slugifyCatalogKey(catalogKeyInput?.value || title);
  const description = String(catalogDescriptionInput?.value || "").trim();
  const status = String(catalogStatusInput?.value || "draft").trim().toLowerCase();
  if (!title) {
    setStateError(catalogModalErrors, "РЈРєР°Р¶РёС‚Рµ РЅР°Р·РІР°РЅРёРµ СЌР»РµРјРµРЅС‚Р°.");
    return;
  }
  try {
    const advanced = parseCatalogAdvancedJson(catalogJsonInput?.value || "{}");
    const payload = { title, key, description, status, config: advanced };
    Array.from(catalogTypedFieldsHost?.querySelectorAll("[data-catalog-field]") || []).forEach((field) => {
      const name = String(field.getAttribute("data-catalog-field") || "");
      if (!name) return;
      const rawValue = String(field.value || "").trim();
      if (!rawValue) return;
      payload[name] = field.type === "number" ? Number(rawValue) : rawValue;
    });
    if (catalogJsonError) {
      catalogJsonError.textContent = "";
      catalogJsonError.hidden = true;
    }
    setStateIdle(catalogModalErrors);
    if (catalogSaveButton) catalogSaveButton.disabled = true;
    const isCreate = Boolean(pendingCatalogContext.isCreate);
    const itemId = pendingCatalogContext.itemId;
    const url = isCreate ? catalogEndpoint(activeCatalogEntity) : catalogEndpoint(activeCatalogEntity, itemId);
    const method = isCreate ? "POST" : "PUT";
    const response = await apiFetch(url, { method, body: JSON.stringify(payload) });
    const responsePayload = await parsePayload(response);
    if (!response.ok) {
      setStateError(catalogModalErrors, formatHttpError(response, responsePayload, "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ СЌР»РµРјРµРЅС‚."));
      if (catalogSaveButton) catalogSaveButton.disabled = false;
      return;
    }
    showMessage(isCreate ? "Р­Р»РµРјРµРЅС‚ СЃРѕР·РґР°РЅ." : "Р­Р»РµРјРµРЅС‚ РѕР±РЅРѕРІР»РµРЅ.");
    closeCatalogModal();
    await loadCatalog(activeCatalogEntity);
  } catch (error) {
    const message = String(error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ СЌР»РµРјРµРЅС‚.");
    if (catalogJsonError) {
      catalogJsonError.textContent = message;
      catalogJsonError.hidden = false;
    }
    setStateError(catalogModalErrors, message);
    if (catalogSaveButton) catalogSaveButton.disabled = false;
  }
}

function renderCatalog(payload) {
  if (!catalogHost) return;
  const entityType = payload?.entity_type || activeCatalogEntity;
  activeCatalogEntity = entityType;
  const items = Array.isArray(payload?.items) ? payload.items : [];
  const audit = Array.isArray(payload?.audit) ? payload.audit : [];
  const statusLabels = {
    draft: "Р§РµСЂРЅРѕРІРёРє",
    review: "РќР° РїСЂРѕРІРµСЂРєРµ",
    approved: "РћРґРѕР±СЂРµРЅРѕ",
    published: "РћРїСѓР±Р»РёРєРѕРІР°РЅРѕ",
    archived: "РђСЂС…РёРІ",
  };
  const workflowActionLabels = {
    submit_for_review: "РќР° РїСЂРѕРІРµСЂРєСѓ",
    approve: "РћРґРѕР±СЂРёС‚СЊ",
    request_changes: "Р’РµСЂРЅСѓС‚СЊ",
    publish: "РџСѓР±Р»РёРєРѕРІР°С‚СЊ",
  };
  const allowedActionsByState = {
    draft: ["submit_for_review"],
    review: ["approve", "request_changes"],
    approved: ["publish", "request_changes"],
    published: ["request_changes"],
  };
  const entityLabels = {
    servers: "РЎРµСЂРІРµСЂС‹",
    laws: "Р—Р°РєРѕРЅС‹",
    templates: "РЁР°Р±Р»РѕРЅС‹",
    features: "Р¤СѓРЅРєС†РёРё",
    rules: "РџСЂР°РІРёР»Р°",
  };
  const entityDescriptions = {
    servers: "РЎРµСЂРІРµСЂРЅС‹Рµ РїСЂРѕС„РёР»Рё Рё Р±Р°Р·РѕРІС‹Рµ РЅР°СЃС‚СЂРѕР№РєРё РѕРєСЂСѓР¶РµРЅРёСЏ.",
    laws: "РџСЂР°РІРѕРІС‹Рµ РёСЃС‚РѕС‡РЅРёРєРё Рё РЅР°Р±РѕСЂС‹ РЅРѕСЂРј, РЅР° РєРѕС‚РѕСЂС‹Рµ РѕРїРёСЂР°РµС‚СЃСЏ СЃРёСЃС‚РµРјР°.",
    templates: "РЁР°Р±Р»РѕРЅС‹ РґРѕРєСѓРјРµРЅС‚РѕРІ Рё Р·Р°РіРѕС‚РѕРІРєРё РґР»СЏ РіРµРЅРµСЂР°С†РёРё.",
    features: "РџРµСЂРµРєР»СЋС‡Р°С‚РµР»Рё С„СѓРЅРєС†РёР№ Рё rollout-РЅР°СЃС‚СЂРѕР№РєРё.",
    rules: "РџСЂР°РІРёР»Р° РїСѓР±Р»РёРєР°С†РёРё, СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ Рё governance-РїРѕР»РёС‚РёРєРё.",
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
      <label class="legal-field"><span class="legal-field__label">Р Р°Р·РґРµР»</span>
        <select id="catalog-entity">
          ${["servers", "laws", "templates", "features", "rules"]
            .map((name) => `<option value="${name}" ${name === entityType ? "selected" : ""}>${entityLabels[name]}</option>`)
            .join("")}
        </select>
      </label>
      <button type="button" id="catalog-create" class="primary-button">РЎРѕР·РґР°С‚СЊ</button>
    </div>
    <p class="legal-section__description">${escapeHtml(entityDescriptions[entityType] || "")}</p>
    <div class="legal-table-wrap">
      <table class="legal-table">
        <thead><tr><th>РќР°Р·РІР°РЅРёРµ</th><th>РЎС‚Р°С‚СѓСЃ</th><th>Р’РµСЂСЃРёСЏ</th><th>РђРІС‚РѕСЂ</th><th>Р”РµР№СЃС‚РІРёСЏ</th></tr></thead>
        <tbody>
          ${items.length
            ? items
            .map((item) => {
              const entityId = String(item.id || "");
              const auditRow = auditByEntityId.get(entityId) || {};
              const state = String(item.status || item.state || "draft");
              const version = item.current_published_version_id ?? item.version_number ?? "вЂ”";
              const author = String(
                auditRow.author || item.updated_by || item.created_by || "system"
              );
              const activeChangeRequestId = item.active_change_request_id ?? "";
              const workflowActions = (allowedActionsByState[state] || [])
                .map((action) => `<button type="button" class="ghost-button" data-catalog-workflow-item="${escapeHtml(String(item.id || ""))}" data-catalog-workflow-action="${escapeHtml(action)}" data-catalog-workflow-cr-id="${escapeHtml(String(activeChangeRequestId || ""))}">${escapeHtml(workflowActionLabels[action] || action)}</button>`)
                .join("");
              return `
              <tr>
                <td>${escapeHtml(String(item.title || ""))}</td>
                <td>${escapeHtml(statusLabels[state] || state)}</td>
                <td>${escapeHtml(String(version))}</td>
                <td>${escapeHtml(author)}</td>
                <td>
                  <button type="button" class="ghost-button" data-catalog-view="${escapeHtml(String(item.id || ""))}">РћС‚РєСЂС‹С‚СЊ</button>
                  <button type="button" class="ghost-button" data-catalog-preview="${escapeHtml(String(item.id || ""))}">Preview</button>
                  ${workflowActions}
                  <button type="button" class="ghost-button" data-catalog-edit="${escapeHtml(String(item.id || ""))}">РР·РјРµРЅРёС‚СЊ</button>
                  <button type="button" class="ghost-button" data-catalog-legacy-next="${escapeHtml(String(item.id || ""))}" hidden>Р”Р°Р»РµРµ</button>
                  <button type="button" class="ghost-button" data-catalog-rollback="${escapeHtml(String(item.id || ""))}">РћС‚РєР°С‚</button>
                  <button type="button" class="ghost-button" data-catalog-delete="${escapeHtml(String(item.id || ""))}">РЈРґР°Р»РёС‚СЊ</button>
                </td>
              </tr>
            `;
            })
            .join("")
            : '<tr><td colspan="5" class="legal-section__description">Р”Р»СЏ СЌС‚РѕРіРѕ СЂР°Р·РґРµР»Р° РїРѕРєР° РЅРµС‚ Р·Р°РїРёСЃРµР№.</td></tr>'}
        </tbody>
      </table>
      <section id="catalog-preview-panel" class="admin-catalog-preview" hidden>
        <div class="admin-catalog-preview__header">
          <div>
            <div class="admin-catalog-preview__title">Preview effective payload</div>
            <div class="admin-catalog-preview__meta" id="catalog-preview-meta">Р’С‹Р±РµСЂРёС‚Рµ Р·Р°РїРёСЃСЊ, С‡С‚РѕР±С‹ РїРѕСЃРјРѕС‚СЂРµС‚СЊ СЌС„С„РµРєС‚РёРІРЅС‹Рµ РґР°РЅРЅС‹Рµ.</div>
          </div>
          <button type="button" class="ghost-button" id="catalog-preview-copy">РљРѕРїРёСЂРѕРІР°С‚СЊ JSON</button>
        </div>
        <div class="admin-catalog-preview__summary" id="catalog-preview-summary"></div>
        <pre class="admin-catalog-preview__json" id="catalog-preview-json">{}</pre>
      </section>
    </div>
    <p class="legal-section__description">Р–СѓСЂРЅР°Р» РёР·РјРµРЅРµРЅРёР№ (Р°РІС‚РѕСЂ Рё diff):</p>
    <pre class="legal-field__hint">${escapeHtml(audit.slice(0, 8).map((row) => `${row.created_at} ${row.author} ${row.action} ${row.workflow_from || ""}->${row.workflow_to || ""}\n${row.diff || ""}`).join("\n\n"))}</pre>
  `;
}

function renderCatalogPreviewSummary(payload) {
  const summary = document.getElementById("catalog-preview-summary");
  const meta = document.getElementById("catalog-preview-meta");
  const jsonHost = document.getElementById("catalog-preview-json");
  const panel = document.getElementById("catalog-preview-panel");
  if (!summary || !meta || !jsonHost || !panel) return;
  const item = payload?.item || {};
  const effectiveVersion = payload?.effective_version || {};
  const effectivePayload = payload?.effective_payload || {};
  summary.innerHTML = `
    <div class="admin-catalog-preview__summary-row"><strong>РќР°Р·РІР°РЅРёРµ:</strong> ${escapeHtml(String(item.title || "вЂ”"))}</div>
    <div class="admin-catalog-preview__summary-row"><strong>РЎС‚Р°С‚СѓСЃ:</strong> ${escapeHtml(String(item.status || item.state || "draft"))}</div>
    <div class="admin-catalog-preview__summary-row"><strong>Р’РµСЂСЃРёСЏ:</strong> ${escapeHtml(String(effectiveVersion?.version_number ?? item.current_version_number ?? item.current_published_version_id ?? "вЂ”"))}</div>
  `;
  meta.textContent = `Entity: ${String(payload?.entity_type || activeCatalogEntity)} | Item ID: ${String(item.id || "вЂ”")} | Effective version ID: ${String(effectiveVersion?.id || "вЂ”")}`;
  jsonHost.textContent = formatJsonForDisplay(effectivePayload);
  panel.hidden = false;
}

function renderCatalogPreview(payload) {
  renderCatalogPreviewSummary(payload);
}

async function loadCatalogPreview(itemId) {
  const response = await apiFetch(catalogEndpoint(activeCatalogEntity, itemId));
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ preview catalog."));
    return;
  }
  renderCatalogPreview(payload);
}

async function loadCatalog(entityType = activeCatalogEntity) {
  if (!catalogHost) return;
  const response = await apiFetch(catalogEndpoint(entityType));
  const payload = await parsePayload(response);
  if (!response.ok) {
    setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ catalog."));
    return;
  }
  renderCatalog(payload);
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
  if (actionConfirmButton) actionConfirmButton.textContent = "РџРѕРґС‚РІРµСЂРґРёС‚СЊ";
  setStateIdle(actionModalErrors);
}

function openActionModal(config) {
  pendingAction = config;
  if (actionModalTitle) {
    actionModalTitle.textContent = config.title || "РџРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ РґРµР№СЃС‚РІРёСЏ";
  }
  if (actionModalDescription) {
    actionModalDescription.textContent = config.description || "";
  }
  if (actionConfirmButton) {
    actionConfirmButton.textContent = config.confirmLabel || "РџРѕРґС‚РІРµСЂРґРёС‚СЊ";
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
  if (riskScore >= 4) return renderBadge("Р РёСЃРє: РІС‹СЃРѕРєРёР№", "danger");
  if (riskScore >= 2) return renderBadge("Р РёСЃРє: СЃСЂРµРґРЅРёР№", "info");
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
    ["AI cost (USD)", `$${formatUsd(totals.ai_estimated_cost_total_usd || 0)}`, `РћС†РµРЅРєР° РїРѕ ${formatNumber(totals.ai_estimated_cost_samples || 0)} РІС‹Р·РѕРІР°Рј`],
    ["AI С‚РѕРєРµРЅС‹ (in/out/total)", `${formatNumber(totals.ai_input_tokens_total || 0)} / ${formatNumber(totals.ai_output_tokens_total || 0)} / ${formatNumber(totals.ai_total_tokens_total || 0)}`, `РЎСѓРјРјР° РїРѕ ${formatNumber(totals.ai_generation_total || 0)} РіРµРЅРµСЂР°С†РёСЏРј`],
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

function renderSynthetic(summary) {
  if (!syntheticHost) {
    return;
  }
  const bySuite = summary?.by_suite || {};
  const suites = ["smoke", "nightly", "load", "fault"];
  const suiteDescriptions = {
    smoke: "Р‘С‹СЃС‚СЂР°СЏ РїСЂРѕРІРµСЂРєР° РѕСЃРЅРѕРІРЅС‹С… СЃС†РµРЅР°СЂРёРµРІ РіРµРЅРµСЂР°С†РёРё, СЃРЅР°РїС€РѕС‚РѕРІ, С†РёС‚Р°С‚ Рё РїСѓР±Р»РёРєР°С†РёРё.",
    nightly: "Р Р°СЃС€РёСЂРµРЅРЅС‹Р№ СЂРµРіСЂРµСЃСЃРёРѕРЅРЅС‹Р№ РїСЂРѕРіРѕРЅ РїРѕР»РЅРѕРіРѕ workflow, РІР»РѕР¶РµРЅРёР№, Р°СЂС‚РµС„Р°РєС‚РѕРІ Рё rollback.",
    load: "РќР°РіСЂСѓР·РѕС‡РЅР°СЏ РїСЂРѕРІРµСЂРєР° burst/sustained СЃС†РµРЅР°СЂРёРµРІ РіРµРЅРµСЂР°С†РёРё, СЌРєСЃРїРѕСЂС‚Р° Рё content workflow.",
    fault: "РџСЂРѕРІРµСЂРєР° РѕС‚РєР°Р·РѕСѓСЃС‚РѕР№С‡РёРІРѕСЃС‚Рё: retry, DLQ, idempotency, isolation Рё policy gates.",
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
        <button type="button" class="ghost-button" data-synthetic-run="${suite}" ${isRunning ? "disabled" : ""}>${isRunning ? "Р—Р°РїСѓСЃРє..." : "Р—Р°РїСѓСЃС‚РёС‚СЊ"}</button>
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
    : '<p class="legal-section__description">РџР°РґРµРЅРёР№ synthetic suite РЅРµ РѕР±РЅР°СЂСѓР¶РµРЅРѕ.</p>';
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
  const samples = Number(totals?.ai_estimated_cost_samples || 0);
  costSummaryHost.innerHTML = `
    <article class="legal-status-card">
      <span class="legal-status-card__label">AI cost (USD)</span>
      <strong class="legal-status-card__value legal-status-card__value--small">$${escapeHtml(formatUsd(totals?.ai_estimated_cost_total_usd || 0))}</strong>
      <span class="admin-user-cell__secondary">РЎСЌРјРїР»РѕРІ: ${escapeHtml(String(samples))}</span>
    </article>
    <article class="legal-status-card">
      <span class="legal-status-card__label">AI С‚РѕРєРµРЅС‹ (in/out/total)</span>
      <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatNumber(totals?.ai_input_tokens_total || 0))} / ${escapeHtml(formatNumber(totals?.ai_output_tokens_total || 0))} / ${escapeHtml(formatNumber(totals?.ai_total_tokens_total || 0))}</strong>
      <span class="admin-user-cell__secondary">Р“РµРЅРµСЂР°С†РёР№: ${escapeHtml(String(totals?.ai_generation_total || 0))}</span>
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
        <span class="legal-status-card__label">Р“РµРЅРµСЂР°С†РёРё</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(summary?.total_generations || 0))}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">РћС†РµРЅРєР° СЃС‚РѕРёРјРѕСЃС‚Рё</span>
        <strong class="legal-status-card__value legal-status-card__value--small">$${escapeHtml(formatUsd(summary?.estimated_cost_total_usd || 0))}</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">p95 latency</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(summary?.latency_ms_p95 ?? "вЂ”"))} ms</strong>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Budget warnings</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(summary?.budget_warning_count || 0))}</strong>
      </article>
    </div>
    <div class="admin-section-toolbar">
      <span class="admin-user-cell__secondary">РњРѕРґРµР»Рё: ${escapeHtml(models.map(([name, count]) => `${name} (${count})`).join(", ") || "РЅРµС‚ РґР°РЅРЅС‹С…")}</span>
    </div>
    ${
      feedback.length
        ? `
      <div class="legal-table-shell">
        <table class="legal-table admin-table admin-table--compact">
          <thead><tr><th>РљРѕРіРґР°</th><th>Flow</th><th>Issue</th><th>РљРѕРјРјРµРЅС‚Р°СЂРёР№</th></tr></thead>
          <tbody>
            ${feedback
              .map(
                (row) => `
                <tr>
                  <td>${escapeHtml(String(row.created_at || "вЂ”"))}</td>
                  <td>${escapeHtml(String((row.meta || {}).flow || "вЂ”"))}</td>
                  <td>${escapeHtml(String((row.meta || {}).issue_type || "вЂ”"))}</td>
                  <td>${escapeHtml(String((row.meta || {}).comment || "вЂ”"))}</td>
                </tr>
              `,
              )
              .join("")}
          </tbody>
        </table>
      </div>`
        : '<p class="legal-section__description">РќРµС‚ РѕР±СЂР°С‚РЅРѕР№ СЃРІСЏР·Рё РїРѕ AI-РїР°Р№РїР»Р°Р№РЅСѓ.</p>'
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
      const message = String(item?.message || "РќРµРёР·РІРµСЃС‚РЅР°СЏ РѕС€РёР±РєР°").trim();
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
        ? `<div class="legal-alert legal-alert--warning">AI Pipeline Р·Р°РіСЂСѓР¶РµРЅ С‡Р°СЃС‚РёС‡РЅРѕ (${escapeHtml(String(partialErrors.length))}). ${escapeHtml(partialErrorsSummary || "РџРѕРґСЂРѕР±РЅРѕСЃС‚Рё РґРѕСЃС‚СѓРїРЅС‹ РІ server logs.")}</div>`
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
    roleHistoryHost.innerHTML = '<p class="legal-section__description">РР·РјРµРЅРµРЅРёР№ СЂРѕР»РµР№ РїРѕРєР° РЅРµС‚.</p>';
    return;
  }
  roleHistoryHost.innerHTML = `
    <div class="legal-table-shell">
      <table class="legal-table admin-table admin-table--compact">
        <thead><tr><th>РљРѕРіРґР°</th><th>РђРґРјРёРЅ</th><th>Р”РµР№СЃС‚РІРёРµ</th><th>РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ</th></tr></thead>
        <tbody>
          ${items
            .slice(0, 20)
            .map(
              (item) => `
              <tr>
                <td>${escapeHtml(String(item.created_at || "вЂ”"))}</td>
                <td>${escapeHtml(String(item.username || "вЂ”"))}</td>
                <td>${escapeHtml(String(item.event_type || "вЂ”"))}</td>
                <td>${escapeHtml(String((item.meta || {}).target_username || "вЂ”"))}</td>
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
    return "РўСЂРµР±СѓРµС‚СЃСЏ РїРѕРІС‚РѕСЂРЅС‹Р№ РІС…РѕРґ РІ СЃРёСЃС‚РµРјСѓ.";
  }

  const details = extractErrorMessage(payload, fallback);
  const requestId = String(response?.headers?.get?.("x-request-id") || "").trim();

  let prefix = "";
  if (status === 403) {
    prefix = "Р”РѕСЃС‚СѓРї Р·Р°РїСЂРµС‰РµРЅ.";
  } else if (status === 429) {
    prefix = "РџСЂРµРІС‹С€РµРЅ Р»РёРјРёС‚ Р·Р°РїСЂРѕСЃРѕРІ.";
  } else if (status >= 500) {
    prefix = "РћС€РёР±РєР° СЃРµСЂРІРµСЂР°.";
  } else if (status >= 400) {
    prefix = "РћС€РёР±РєР° Р·Р°РїСЂРѕСЃР°.";
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
  const recentEntries = Array.isArray(summary.recent_entries) ? summary.recent_entries : [];
  const failedEntries = Array.isArray(summary.failed_entries) ? summary.failed_entries : [];

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
    ${renderAdminExamEntriesSection({
      title: "РџРѕСЃР»РµРґРЅРёРµ РѕС‚РІРµС‚С‹ Рё РѕС†РµРЅРєРё",
      description: "РџРѕСЃР»РµРґРЅРёРµ РёРјРїРѕСЂС‚РёСЂРѕРІР°РЅРЅС‹Рµ СЃС‚СЂРѕРєРё СЃ С‚РµРєСѓС‰РёРј Р±Р°Р»Р»РѕРј, СЃС‚Р°С‚СѓСЃРѕРј Рё Р±С‹СЃС‚СЂС‹Рј РїРµСЂРµС…РѕРґРѕРј Рє РґРµС‚Р°Р»СЊРЅРѕРјСѓ СЂР°Р·Р±РѕСЂСѓ.",
      entries: recentEntries,
      emptyText: "РџРѕРєР° РЅРµС‚ СЃС‚СЂРѕРє, РєРѕС‚РѕСЂС‹Рµ РјРѕР¶РЅРѕ РїРѕРєР°Р·Р°С‚СЊ РІ Р°РґРјРёРЅРєРµ.",
    })}
    ${renderAdminExamEntriesSection({
      title: "РќСѓР¶РґР°СЋС‚СЃСЏ РІ РїРµСЂРµРїСЂРѕРІРµСЂРєРµ",
      description: "РЎС‚СЂРѕРєРё, РіРґРµ Сѓ РѕС‚РІРµС‚РѕРІ РѕСЃС‚Р°Р»РёСЃСЊ РЅРµРєРѕСЂСЂРµРєС‚РЅС‹Рµ РёР»Рё РЅРµРїРѕР»РЅС‹Рµ СЂРµР·СѓР»СЊС‚Р°С‚С‹ РїСЂРѕРІРµСЂРєРё.",
      entries: failedEntries,
      emptyText: "РЎС‚СЂРѕРє, С‚СЂРµР±СѓСЋС‰РёС… РїРµСЂРµРїСЂРѕРІРµСЂРєРё, СЃРµР№С‡Р°СЃ РЅРµС‚.",
      emphasizeFailed: true,
    })}
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

function getExamEntryStatus(entry) {
  if (ExamView?.getEntryStatus) {
    return ExamView.getEntryStatus(entry);
  }
  const average = Number(entry?.average_score);
  if (entry?.average_score == null || Number.isNaN(average)) {
    return { key: "pending", label: "РћР¶РёРґР°РµС‚ РѕС†РµРЅРєРё", tone: "pending" };
  }
  if (average >= 73) {
    return { key: "good", label: "РЎРґР°РЅ С…РѕСЂРѕС€Рѕ", tone: "ok" };
  }
  if (average > 55) {
    return { key: "medium", label: "РЎРґР°РЅ РЅР° СЃСЂРµРґРЅРµРј СѓСЂРѕРІРЅРµ", tone: "warn" };
  }
  return { key: "poor", label: "РЎРґР°РЅ СЃР»Р°Р±Рѕ", tone: "problem" };
}

function formatExamAverage(entry) {
  if (ExamView?.formatAverage) {
    return ExamView.formatAverage(entry);
  }
  return entry?.average_score != null ? `${entry.average_score} / 100` : "вЂ”";
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
              <th>РЎС‚СЂРѕРєР°</th>
              <th>РљР°РЅРґРёРґР°С‚</th>
              <th>Р¤РѕСЂРјР°С‚</th>
              <th>Р‘Р°Р»Р»</th>
              <th>РЎС‚Р°С‚СѓСЃ</th>
              <th>РћС‚РІРµС‚РѕРІ</th>
              <th>РРјРїРѕСЂС‚</th>
              <th>Р”РµР№СЃС‚РІРёРµ</th>
            </tr>
          </thead>
          <tbody>
            ${entries
              .map((entry) => {
                const status = getExamEntryStatus(entry);
                const reviewBadge = emphasizeFailed || entry?.needs_rescore
                  ? renderBadge("РќСѓР¶РЅР° РїРµСЂРµРїСЂРѕРІРµСЂРєР°", "danger")
                  : "";
                return `
                  <tr>
                    <td>${escapeHtml(entry.source_row ?? "вЂ”")}</td>
                    <td>
                      <div class="admin-user-cell">
                        <strong class="admin-user-cell__name">${escapeHtml(entry.full_name || "вЂ”")}</strong>
                        <span class="admin-user-cell__secondary">${escapeHtml(entry.discord_tag || "вЂ”")}</span>
                      </div>
                    </td>
                    <td>${escapeHtml(entry.exam_format || "вЂ”")}</td>
                    <td>${escapeHtml(formatExamAverage(entry))}</td>
                    <td>
                      <div class="admin-badge-row">
                        <span class="exam-status-badge exam-status-badge--${escapeHtml(status.tone)}">${escapeHtml(status.label)}</span>
                        ${reviewBadge}
                      </div>
                    </td>
                    <td>${escapeHtml(String(entry.answer_count ?? 0))}</td>
                    <td>${escapeHtml(entry.imported_at || "вЂ”")}</td>
                    <td>
                      <button
                        type="button"
                        class="ghost-button admin-exam-detail-btn"
                        data-exam-source-row="${escapeHtml(entry.source_row ?? "")}"
                      >
                        Р Р°Р·Р±РѕСЂ
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

  if (!users.length) {
    usersHost.innerHTML = '<p class="legal-section__description">РџРѕ С‚РµРєСѓС‰РµРјСѓ С„РёР»СЊС‚СЂСѓ РїРѕР»СЊР·РѕРІР°С‚РµР»Рё РЅРµ РЅР°Р№РґРµРЅС‹.</p>';
    return;
  }

  usersHost.innerHTML = `
    <div class="admin-section-toolbar">
      <p class="legal-section__description">РџРѕРєР°Р·Р°РЅРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№: ${escapeHtml(String(users.length))}. РЎРѕСЂС‚РёСЂРѕРІРєР°: ${escapeHtml(String(userSort))}</p>
    </div>
    <div class="admin-section-toolbar">
      <label class="legal-field">
        <span class="legal-field__label">РњР°СЃСЃРѕРІРѕРµ РґРµР№СЃС‚РІРёРµ</span>
        <select id="admin-bulk-action">
          <option value="">Р’С‹Р±РµСЂРёС‚Рµ РґРµР№СЃС‚РІРёРµ</option>
          <option value="verify_email">РџРѕРґС‚РІРµСЂРґРёС‚СЊ email</option>
          <option value="block">Р—Р°Р±Р»РѕРєРёСЂРѕРІР°С‚СЊ</option>
          <option value="unblock">Р Р°Р·Р±Р»РѕРєРёСЂРѕРІР°С‚СЊ</option>
          <option value="grant_tester">Р’С‹РґР°С‚СЊ С‚РµСЃС‚РµСЂР°</option>
          <option value="revoke_tester">РЎРЅСЏС‚СЊ С‚РµСЃС‚РµСЂР°</option>
          <option value="grant_gka">Р’С‹РґР°С‚СЊ Р“РљРђ-Р—Р“РљРђ</option>
          <option value="revoke_gka">РЎРЅСЏС‚СЊ Р“РљРђ-Р—Р“РљРђ</option>
          <option value="deactivate">Р”РµР°РєС‚РёРІРёСЂРѕРІР°С‚СЊ</option>
          <option value="reactivate">Р РµР°РєС‚РёРІРёСЂРѕРІР°С‚СЊ</option>
          <option value="set_daily_quota">РЈСЃС‚Р°РЅРѕРІРёС‚СЊ РєРІРѕС‚Сѓ/РґРµРЅСЊ</option>
        </select>
      </label>
      <input id="admin-bulk-reason" type="text" placeholder="РџСЂРёС‡РёРЅР° (РґР»СЏ block/deactivate)">
      <input id="admin-bulk-quota" type="number" min="0" step="1" placeholder="РљРІРѕС‚Р°/РґРµРЅСЊ (РґР»СЏ quota)">
      <button type="button" id="admin-bulk-run" class="ghost-button">Р—Р°РїСѓСЃС‚РёС‚СЊ РІ РѕС‡РµСЂРµРґРё</button>
      <span id="admin-bulk-status" class="admin-badge admin-badge--muted">Р’С‹Р±СЂР°РЅРѕ: ${selectedBulkUsers.size}</span>
    </div>
    <div class="legal-table-shell">
      <table class="legal-table admin-table">
        <thead>
          <tr>
            <th><input type="checkbox" id="admin-users-select-all"></th>
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
  if (!eventsHost) {
    return;
  }
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

function renderErrorExplorer(payload) {
  if (!errorExplorerHost) {
    return;
  }
  const items = Array.isArray(payload?.items) ? payload.items : [];
  const byType = Array.isArray(payload?.by_event_type) ? payload.by_event_type : [];
  const byPath = Array.isArray(payload?.by_path) ? payload.by_path : [];

  if (!items.length) {
    errorExplorerHost.innerHTML = '<p class="legal-section__description">РћС€РёР±РѕРє РїРѕ С‚РµРєСѓС‰РµРјСѓ С„РёР»СЊС‚СЂСѓ РЅРµ РЅР°Р№РґРµРЅРѕ.</p>';
    return;
  }

  const topTypeText = byType.slice(0, 3).map((item) => `${item.event_type}: ${item.count}`).join(" В· ");
  const topPathText = byPath.slice(0, 3).map((item) => `${item.path}: ${item.count}`).join(" В· ");

  errorExplorerHost.innerHTML = `
    <div class="admin-section-toolbar">
      <p class="legal-section__description">
        РћС€РёР±РѕРє: ${escapeHtml(String(payload?.total || items.length))}
      </p>
      <p class="legal-section__description">
        РўРѕРї С‚РёРїРѕРІ: ${escapeHtml(topTypeText || "вЂ”")}
      </p>
      <p class="legal-section__description">
        РўРѕРї endpoint: ${escapeHtml(topPathText || "вЂ”")}
      </p>
    </div>
    <div class="legal-table-shell">
      <table class="legal-table admin-table admin-table--compact">
        <thead>
          <tr>
            <th>Р’СЂРµРјСЏ</th>
            <th>РўРёРї</th>
            <th>Endpoint</th>
            <th>HTTP</th>
            <th>РћС€РёР±РєР°</th>
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
  if (userModalTitle) {
    userModalTitle.textContent = DEFAULT_USER_MODAL_TITLE;
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
        <button type="button" class="ghost-button" data-set-quota="${escapeHtml(user.username || "")}" data-current-quota="${escapeHtml(String(user.api_quota_daily || 0))}">РљРІРѕС‚Р° API/РґРµРЅСЊ</button>
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
          user.deactivated_at
            ? `<button type="button" class="ghost-button" data-reactivate-user="${escapeHtml(user.username || "")}">Р РµР°РєС‚РёРІРёСЂРѕРІР°С‚СЊ</button>`
            : `<button type="button" class="ghost-button" data-deactivate-user="${escapeHtml(user.username || "")}">Р”РµР°РєС‚РёРІРёСЂРѕРІР°С‚СЊ</button>`
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

async function loadAdminOverview({ silent = false } = {}) {
  if (!silent) {
    setStateIdle(errorsHost);
    clearMessage();
    showOverviewLoading();
  } else {
    setLiveStatus("Live: РѕР±РЅРѕРІР»РµРЅРёРµ...", "info");
  }

  try {
    const response = await apiFetch(buildOverviewUrl());
    if (!response.ok) {
      const payload = await parsePayload(response);
      if (!silent) {
        setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РґР°РЅРЅС‹Рµ Р°РґРјРёРЅ-РїР°РЅРµР»Рё."));
      } else {
        setLiveStatus("Live: РѕС€РёР±РєР° РѕР±РЅРѕРІР»РµРЅРёСЏ", "danger");
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
      setStateError(errorsHost, `РџР°РЅРµР»СЊ Р·Р°РіСЂСѓР¶РµРЅР° С‡Р°СЃС‚РёС‡РЅРѕ (${partialErrors.length}). ${source}${message}`.trim());
    }

    if (selectedUser && userIndex.has(String(selectedUser).toLowerCase())) {
      renderUserModal(userIndex.get(String(selectedUser).toLowerCase()));
    }
    if (silent) {
      setLiveStatus(`Live: СЃРёРЅС…СЂРѕРЅРЅРѕ ${new Date().toLocaleTimeString("ru-RU")}`, "success-soft");
    }
  } catch (error) {
    if (!silent) {
      setStateError(errorsHost, error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РґР°РЅРЅС‹Рµ Р°РґРјРёРЅ-РїР°РЅРµР»Рё.");
    } else {
      setLiveStatus("Live: РѕС€РёР±РєР° РѕР±РЅРѕРІР»РµРЅРёСЏ", "danger");
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
      setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ РІС‹РїРѕР»РЅРёС‚СЊ РґРµР№СЃС‚РІРёРµ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂР°."));
      return;
    }
    showMessage(successText);
    await loadAdminOverview();
  } catch (error) {
    setStateError(errorsHost, error?.message || "РќРµ СѓРґР°Р»РѕСЃСЊ РІС‹РїРѕР»РЅРёС‚СЊ РґРµР№СЃС‚РІРёРµ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂР°.");
  }
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
    openActionModal({
      action: "block-user",
      username: blockUsername,
      askReason: true,
      title: "Р‘Р»РѕРєРёСЂРѕРІРєР° РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ",
      description: `Р’С‹ Р±Р»РѕРєРёСЂСѓРµС‚Рµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ ${blockUsername}. РџСЂРё РЅРµРѕР±С…РѕРґРёРјРѕСЃС‚Рё СѓРєР°Р¶РёС‚Рµ РїСЂРёС‡РёРЅСѓ.`,
      confirmLabel: "Р—Р°Р±Р»РѕРєРёСЂРѕРІР°С‚СЊ",
    });
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
    openActionModal({
      action: "change-email",
      username: changeEmailUsername,
      askEmail: true,
      defaultEmail: target.getAttribute("data-current-email") || "",
      title: "РЎРјРµРЅР° email",
      description: `РЈРєР°Р¶РёС‚Рµ РЅРѕРІС‹Р№ email РґР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ ${changeEmailUsername}.`,
      confirmLabel: "РЎРѕС…СЂР°РЅРёС‚СЊ email",
    });
    return true;
  }

  const resetPasswordUsername = target.getAttribute("data-reset-password");
  if (resetPasswordUsername) {
    openActionModal({
      action: "reset-password",
      username: resetPasswordUsername,
      askPassword: true,
      title: "РЎР±СЂРѕСЃ РїР°СЂРѕР»СЏ",
      description: `Р’РІРµРґРёС‚Рµ РЅРѕРІС‹Р№ РїР°СЂРѕР»СЊ РґР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ ${resetPasswordUsername}.`,
      confirmLabel: "РЎРјРµРЅРёС‚СЊ РїР°СЂРѕР»СЊ",
    });
    return true;
  }

  const deactivateUsername = target.getAttribute("data-deactivate-user");
  if (deactivateUsername) {
    openActionModal({
      action: "deactivate-user",
      username: deactivateUsername,
      askReason: true,
      title: "Р”РµР°РєС‚РёРІР°С†РёСЏ Р°РєРєР°СѓРЅС‚Р°",
      description: `РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ ${deactivateUsername} Р±СѓРґРµС‚ РґРµР°РєС‚РёРІРёСЂРѕРІР°РЅ (soft-delete).`,
      confirmLabel: "Р”РµР°РєС‚РёРІРёСЂРѕРІР°С‚СЊ",
    });
    return true;
  }

  const reactivateUsername = target.getAttribute("data-reactivate-user");
  if (reactivateUsername) {
    await performAdminAction(`/api/admin/users/${encodeURIComponent(reactivateUsername)}/reactivate`, "РђРєРєР°СѓРЅС‚ СЂРµР°РєС‚РёРІРёСЂРѕРІР°РЅ.");
    return true;
  }

  const setQuotaUsername = target.getAttribute("data-set-quota");
  if (setQuotaUsername) {
    openActionModal({
      action: "set-daily-quota",
      username: setQuotaUsername,
      askQuota: true,
      defaultQuota: target.getAttribute("data-current-quota") || "0",
      title: "РЎСѓС‚РѕС‡РЅР°СЏ РєРІРѕС‚Р° API",
      description: `РЈСЃС‚Р°РЅРѕРІРёС‚Рµ Р»РёРјРёС‚ API Р·Р°РїСЂРѕСЃРѕРІ РІ СЃСѓС‚РєРё РґР»СЏ ${setQuotaUsername} (0 = Р±РµР· Р»РёРјРёС‚Р°).`,
      confirmLabel: "РЎРѕС…СЂР°РЅРёС‚СЊ РєРІРѕС‚Сѓ",
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
    await performAdminAction(`/api/admin/users/${encodeURIComponent(username)}/block`, "Р”РѕСЃС‚СѓРї РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ Р·Р°Р±Р»РѕРєРёСЂРѕРІР°РЅ.", {
      reason,
    });
    closeActionModal();
    return;
  }

  if (action === "change-email") {
    const email = String(actionEmailInput?.value || "").trim();
    if (!email) {
      setStateError(actionModalErrors, "РЈРєР°Р¶РёС‚Рµ РЅРѕРІС‹Р№ email.");
      return;
    }
    await performAdminAction(`/api/admin/users/${encodeURIComponent(username)}/email`, "Email РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РѕР±РЅРѕРІР»РµРЅ.", {
      email,
    });
    closeActionModal();
    return;
  }

  if (action === "reset-password") {
    const password = String(actionPasswordInput?.value || "").trim();
    if (!password) {
      setStateError(actionModalErrors, "Р’РІРµРґРёС‚Рµ РЅРѕРІС‹Р№ РїР°СЂРѕР»СЊ.");
      return;
    }
    if (password.length < 10) {
      setStateError(actionModalErrors, "РџР°СЂРѕР»СЊ РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РЅРµ РєРѕСЂРѕС‡Рµ 10 СЃРёРјРІРѕР»РѕРІ.");
      return;
    }
    await performAdminAction(
      `/api/admin/users/${encodeURIComponent(username)}/reset-password`,
      "РџР°СЂРѕР»СЊ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РѕР±РЅРѕРІР»РµРЅ.",
      { password },
    );
    closeActionModal();
    return;
  }

  if (action === "deactivate-user") {
    const reason = String(actionReasonInput?.value || "").trim();
    await performAdminAction(`/api/admin/users/${encodeURIComponent(username)}/deactivate`, "РђРєРєР°СѓРЅС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РґРµР°РєС‚РёРІРёСЂРѕРІР°РЅ.", {
      reason,
    });
    closeActionModal();
    return;
  }

  if (action === "set-daily-quota") {
    const quota = Number(actionQuotaInput?.value || 0);
    if (!Number.isFinite(quota) || quota < 0) {
      setStateError(actionModalErrors, "РљРІРѕС‚Р° РґРѕР»Р¶РЅР° Р±С‹С‚СЊ РЅРµРѕС‚СЂРёС†Р°С‚РµР»СЊРЅС‹Рј С‡РёСЃР»РѕРј.");
      return;
    }
    await performAdminAction(`/api/admin/users/${encodeURIComponent(username)}/daily-quota`, "РљРІРѕС‚Р° РѕР±РЅРѕРІР»РµРЅР°.", {
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
  if (target.id === "catalog-entity") {
    await loadCatalog(String(target.value || "servers"));
  }
});

catalogHost?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (target.id === "catalog-create") {
    openCatalogModal({
      mode: "edit",
      isCreate: true,
      item: { title: "", status: "draft" },
      versions: [],
    });
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
      item: payload?.item || {},
      versions: Array.isArray(payload?.versions) ? payload.versions : [],
    });
    return;
  }
  const editId = target.getAttribute("data-catalog-edit");
  if (editId) {
    const response = await apiFetch(catalogEndpoint(activeCatalogEntity, editId));
    const payload = await parsePayload(response);
    if (!response.ok) {
      setStateError(errorsHost, formatHttpError(response, payload, "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЌР»РµРјРµРЅС‚ catalog."));
      return;
    }
    openCatalogModal({
      mode: "edit",
      item: payload?.item || {},
      versions: Array.isArray(payload?.versions) ? payload.versions : [],
    });
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
    if (text) {
      await navigator.clipboard.writeText(text);
      showMessage("JSON СЃРєРѕРїРёСЂРѕРІР°РЅ.");
    }
    return;
  }
  const workflowItemId = target.getAttribute("data-catalog-workflow-item");
  if (workflowItemId) {
    const action = String(target.getAttribute("data-catalog-workflow-action") || "").trim();
    const changeRequestId = Number(target.getAttribute("data-catalog-workflow-cr-id") || 0);
    await performAdminAction(`${catalogEndpoint(activeCatalogEntity, workflowItemId)}/workflow`, "Workflow РѕР±РЅРѕРІР»РµРЅ.", {
      action,
      change_request_id: Number.isFinite(changeRequestId) ? changeRequestId : 0,
    });
    await loadCatalog(activeCatalogEntity);
    return;
  }
  const nextId = target.getAttribute("data-catalog-legacy-next");
  if (nextId) {
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
catalogCancelButton?.addEventListener("click", closeCatalogModal);
document.getElementById("admin-catalog-modal-close")?.addEventListener("click", closeCatalogModal);
catalogForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  await submitCatalogModal();
});
catalogJsonInput?.addEventListener("input", () => {
  if (catalogJsonError) {
    catalogJsonError.hidden = true;
    catalogJsonError.textContent = "";
  }
  setStateIdle(catalogModalErrors);
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

