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
const DEFAULT_USER_MODAL_TITLE = userModalTitle?.textContent || "Карточка пользователя";

let adminSearchTimer = null;
let adminLiveTimer = null;
let selectedUser = null;
let pendingAction = null;
let selectedBulkUsers = new Set();
const userIndex = new Map();

const userModal = createModalController({
  modal: document.getElementById("admin-user-modal"),
});
const actionModal = createModalController({
  modal: document.getElementById("admin-action-modal"),
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

  aiPipelineHost.innerHTML = `
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
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(quality?.fallback_rate ?? "n/a"))}%</strong>
        <span class="admin-user-cell__secondary">Budget warnings: ${escapeHtml(String(summary?.budget_warning_count || 0))}</span>
      </article>
    </div>
    <div class="admin-performance-grid">
      <article class="legal-status-card">
        <span class="legal-status-card__label">guard_fail_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(quality?.guard_fail_rate ?? "n/a"))}%</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.guard_fail_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">guard_warn_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(quality?.guard_warn_rate ?? "n/a"))}%</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.guard_warn_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">wrong_law_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(quality?.wrong_law_rate ?? "n/a"))}%</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.wrong_law_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">hallucination_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(quality?.hallucination_rate ?? "n/a"))}%</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.hallucination_rate)}</span>
      </article>
    </div>
    <div class="admin-performance-grid">
      <article class="legal-status-card">
        <span class="legal-status-card__label">new_fact_validation_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(quality?.new_fact_validation_rate ?? "n/a"))}%</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.new_fact_validation_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">unsupported_article_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(quality?.unsupported_article_rate ?? "n/a"))}%</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.unsupported_article_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">format_violation_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(quality?.format_violation_rate ?? "n/a"))}%</strong>
        <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.format_violation_rate)}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">safe_fallback_rate</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(quality?.safe_fallback_rate ?? "n/a"))}%</strong>
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
        <p class="admin-user-cell__secondary">validation_retry_rate: ${escapeHtml(String(quality?.validation_retry_rate ?? "n/a"))}%</p>
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
      <div class="legal-table-shell exam-detail-shell">
        <table class="legal-table admin-table admin-table--compact">
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

actionConfirmButton?.addEventListener("click", submitPendingAction);
actionCancelButton?.addEventListener("click", closeActionModal);
document.getElementById("admin-action-modal-close")?.addEventListener("click", resetActionModalFields);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    userModal.close();
    closeActionModal();
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
initCollapsibles();
Promise.all([
  loadAdminOverview(),
  loadAdminPerformance(),
  loadAiPipeline(),
  loadRoleHistory(),
]).then(() => {
  scheduleLiveRefresh();
});
