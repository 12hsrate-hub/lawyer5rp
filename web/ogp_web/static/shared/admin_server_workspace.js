window.OGPAdminServerWorkspace = {
  bootServerWorkspace(deps = {}) {
    const host = deps.host;
    if (!(host instanceof HTMLElement)) {
      return;
    }
    const serverCode = String(host.dataset.serverCode || "").trim().toLowerCase();
    if (!serverCode) {
      return;
    }
    const escapeHtml = deps.escapeHtml || ((value) => String(value ?? ""));
    const state = {
      activeTab: "overview",
      workspace: null,
      activity: null,
      lawsSummary: null,
      lawsEffective: null,
      lawsDiff: null,
      lawProjectionStatus: null,
      lawSourceSetsData: null,
      lawBindingEditor: null,
      lawManualEditor: null,
      accessSummary: null,
      rolesData: null,
      permissionsData: null,
      auditData: null,
      issuesData: null,
      auditKindFilter: "all",
      auditSearch: "",
      issueSeverityFilter: "all",
      issueSourceFilter: "all",
      selectedAccessUsername: "",
      featuresData: null,
      templatesData: null,
      featureEditorKey: "",
      templateEditorKey: "",
      templatePreviewByKey: {},
      templatePlaceholdersByKey: {},
    };

    function normalizeKey(value) {
      return String(value || "").trim().toLowerCase();
    }

    function getFeatureItems() {
      return Array.isArray(state.featuresData?.effective_items) ? state.featuresData.effective_items : [];
    }

    function getTemplateItems() {
      return Array.isArray(state.templatesData?.effective_items) ? state.templatesData.effective_items : [];
    }

    function getAccessItems() {
      return Array.isArray(state.accessSummary?.items) ? state.accessSummary.items : [];
    }

    function getLawSourceSetItems() {
      return Array.isArray(state.lawSourceSetsData?.items) ? state.lawSourceSetsData.items : [];
    }

    function getLawBindingItems() {
      return Array.isArray(state.lawsSummary?.bindings) ? state.lawsSummary.bindings : [];
    }

    function findLawBinding(bindingId) {
      const items = getLawBindingItems();
      return items.find((item) => Number(item?.id || 0) === Number(bindingId || 0)) || null;
    }

    function buildLawBindingEditorState() {
      const editor = state.lawBindingEditor;
      if (!editor) {
        return null;
      }
      const binding = editor.mode === "edit" ? findLawBinding(editor.bindingId) : null;
      return {
        mode: editor.mode,
        bindingId: binding ? Number(binding.id || 0) : null,
        sourceSetKey: String(binding?.source_set_key || ""),
        priority: String(binding?.priority ?? 100),
        isActive: binding ? Boolean(binding.is_active) : true,
      };
    }

    function buildLawManualEditorState() {
      const editor = state.lawManualEditor;
      if (!editor) {
        return null;
      }
      return {
        mode: String(editor.mode || "create"),
        sourceSetKey: String(editor.sourceSetKey || ""),
        canonicalIdentityKey: String(editor.canonicalIdentityKey || ""),
        normalizedUrl: String(editor.normalizedUrl || ""),
        title: String(editor.title || ""),
        bodyText: String(editor.bodyText || ""),
      };
    }

    function getSelectedAccessUser() {
      const normalized = normalizeKey(state.selectedAccessUsername);
      return getAccessItems().find((item) => normalizeKey(item?.username) === normalized) || null;
    }

    function findEffectiveItem(items, contentKey) {
      const normalizedKey = normalizeKey(contentKey);
      return items.find((item) => normalizeKey(item?.content_key) === normalizedKey) || null;
    }

    function buildWorkflowActionLabel(action) {
      if (action === "submit_for_review") return "Отправить на ревью";
      if (action === "approve") return "Approve";
      if (action === "request_changes") return "На доработку";
      if (action === "publish") return "Publish";
      return action;
    }

    function buildWorkflowActions(item) {
      const request = item?.active_change_request;
      const status = normalizeKey(request?.status || item?.status);
      if (!request?.id) {
        return [];
      }
      if (status === "draft") {
        return ["submit_for_review"];
      }
      if (status === "in_review" || status === "review") {
        return ["approve", "request_changes"];
      }
      if (status === "approved") {
        return ["publish"];
      }
      return [];
    }

    function buildFeatureEditorState() {
      const item = findEffectiveItem(getFeatureItems(), state.featureEditorKey);
      const effectivePayload = item?.effective_payload || {};
      const draftPayload = item?.draft_payload || {};
      const basePayload = { ...effectivePayload, ...draftPayload };
      const contentKey = normalizeKey(item?.content_key || (state.featureEditorKey === "__new__" ? "" : state.featureEditorKey));
      return {
        item,
        contentKey,
        title: String(basePayload.title || item?.title || contentKey || ""),
        status: String(basePayload.status || item?.status || "draft"),
        enabled: Boolean(typeof basePayload.enabled === "boolean" ? basePayload.enabled : item?.status !== "disabled"),
        order: basePayload.order ?? "",
        rollout: String(basePayload.rollout || ""),
        owner: String(basePayload.owner || ""),
        notes: String(basePayload.notes || ""),
        hidden: Boolean(basePayload.hidden || false),
      };
    }

    function buildTemplateEditorState() {
      const item = findEffectiveItem(getTemplateItems(), state.templateEditorKey);
      const effectivePayload = item?.effective_payload || {};
      const draftPayload = item?.draft_payload || {};
      const basePayload = { ...effectivePayload, ...draftPayload };
      const contentKey = normalizeKey(item?.content_key || (state.templateEditorKey === "__new__" ? "" : state.templateEditorKey));
      return {
        item,
        contentKey,
        title: String(basePayload.title || item?.title || contentKey || ""),
        status: String(basePayload.status || item?.status || "draft"),
        format: String(basePayload.format || "bbcode"),
        body: String(basePayload.body || ""),
        notes: String(basePayload.notes || ""),
      };
    }

    function setBusy(isBusy) {
      const refreshButton = document.getElementById("admin-server-workspace-refresh");
      if (refreshButton instanceof HTMLButtonElement) {
        refreshButton.disabled = Boolean(isBusy);
        refreshButton.textContent = isBusy ? "Обновляем..." : "Обновить workspace";
      }
    }

    function badgeClass(status) {
      const normalized = String(status || "").trim().toLowerCase();
      if (normalized === "ready") return "admin-badge--success";
      if (normalized === "ready_with_compatibility") return "admin-badge--warning";
      if (normalized === "error") return "admin-badge--danger";
      if (normalized === "update_required" || normalized === "partial") return "admin-badge--warning";
      return "admin-badge--muted";
    }

    function statusLabel(status) {
      const normalized = String(status || "").trim().toLowerCase();
      if (normalized === "ready") return "Готов";
      if (normalized === "ready_with_compatibility") return "Готов с compatibility";
      if (normalized === "blocked") return "Заблокировано";
      if (normalized === "error") return "Есть ошибки";
      if (normalized === "update_required") return "Требует обновления";
      if (normalized === "partial") return "Настроен частично";
      if (normalized === "not_configured") return "Не настроен";
      return normalized || "unknown";
    }

    function issueSeverityClass(severity) {
      const normalized = String(severity || "").trim().toLowerCase();
      if (normalized === "error") return "admin-badge--danger";
      if (normalized === "warn" || normalized === "warning") return "admin-badge--warning";
      return "admin-badge--muted";
    }

    function permissionLabel(code, permissions) {
      const normalized = normalizeKey(code);
      const items = Array.isArray(permissions) ? permissions : [];
      const match = items.find((item) => normalizeKey(item?.code) === normalized);
      return String(match?.description || normalized || "permission");
    }

    function summarizeIssueNextStep(item) {
      const issueId = normalizeKey(item?.issue_id);
      if (issueId === "laws_runtime_health") {
        return "Откройте вкладку «Законы», запустите проверку наполнения и затем сделайте recheck.";
      }
      if (issueId === "laws_bindings_missing") {
        return "Во вкладке «Законы» добавьте хотя бы один активный source set binding.";
      }
      if (issueId === "runtime_config_fallback") {
        return "Закрепите published или bootstrap runtime pack, чтобы сервер перестал зависеть от neutral fallback.";
      }
      if (issueId === "synthetic_failures") {
        return "Запустите retry. Если ошибка останется, откройте «Диагностика» и проверьте synthetic / ops сигналы.";
      }
      if (issueId === "integrity_checks") {
        return "Откройте «Диагностика» и ops/dashboard: эта проблема требует технической сверки целостности.";
      }
      if (issueId === "jobs_dlq") {
        return "Нужна операторская проверка очередей и downstream-обработчиков. Из карточки сервера это обычно не чинится напрямую.";
      }
      return "Проверьте смежную вкладку сервера или «Диагностика», чтобы уточнить источник и следующий шаг.";
    }

    function renderOperationalSummaryCard({ title, summary, actionTab, actionLabel }) {
      const normalizedStatus = String(summary?.status || "").trim().toLowerCase() || "partial";
      return `
        <div class="legal-subcard">
          <div class="legal-subcard__header">
            <div>
              <span class="legal-field__label">${escapeHtml(String(title || "Summary"))}</span>
              <div><span class="admin-badge ${badgeClass(normalizedStatus)}">${escapeHtml(statusLabel(normalizedStatus))}</span></div>
            </div>
            ${actionTab ? `<button type="button" class="ghost-button" data-server-workspace-switch="${escapeHtml(String(actionTab || ""))}">${escapeHtml(String(actionLabel || "Открыть"))}</button>` : ""}
          </div>
          <div class="admin-user-cell__secondary">${escapeHtml(String(summary?.detail || "—"))}</div>
          <div class="admin-user-cell__secondary">${escapeHtml(String(summary?.next_step || "—"))}</div>
        </div>
      `;
    }

    function uniqueValues(items, getter) {
      const values = new Set();
      (Array.isArray(items) ? items : []).forEach((item) => {
        const value = String(getter(item) || "").trim().toLowerCase();
        if (value) {
          values.add(value);
        }
      });
      return Array.from(values).sort();
    }

    function renderSummary() {
      const summaryHost = document.getElementById("admin-server-workspace-summary");
      if (!(summaryHost instanceof HTMLElement)) {
        return;
      }
      const readiness = state.workspace?.readiness || {};
      const counters = readiness.counters || {};
      const health = state.workspace?.health?.summary || {};
      const onboarding = state.workspace?.health?.onboarding || {};
      const runtimeTruth = state.workspace?.health?.runtime_requirements || {};
      const issues = state.issuesData || state.workspace?.issues || {};
      const accessSummary = state.accessSummary?.summary || state.workspace?.overview?.access?.summary || {};
      const auditSummary = state.auditData?.summary || {};
      const issuesSummary = issues.summary || {};
      const latestAudit = Array.isArray(state.auditData?.items) ? state.auditData.items[0] : null;
      summaryHost.innerHTML = `
        <div class="legal-field">
          <span class="legal-field__label">Сервер</span>
          <div><strong>${escapeHtml(state.workspace?.server?.title || serverCode)}</strong></div>
          <div class="admin-user-cell__secondary">${escapeHtml(serverCode)}</div>
        </div>
        <div class="legal-field">
          <span class="legal-field__label">Общая готовность</span>
          <div><span class="admin-badge ${badgeClass(readiness.overall_status)}">${escapeHtml(statusLabel(readiness.overall_status))}</span></div>
          <div class="admin-user-cell__secondary">errors: ${escapeHtml(String(counters.errors || 0))} • warnings: ${escapeHtml(String(counters.warnings || 0))}</div>
        </div>
        <div class="legal-field">
          <span class="legal-field__label">Health</span>
          <div><strong>${health.is_ready ? "готов" : "нужна проверка"}</strong></div>
          <div class="admin-user-cell__secondary">${escapeHtml(String(health.ready_count || 0))}/${escapeHtml(String(health.total_count || 0))} checks</div>
        </div>
        <div class="legal-field">
          <span class="legal-field__label">Migrated runtime</span>
          <div><strong>${escapeHtml(String(runtimeTruth.status || "unknown"))}</strong></div>
          <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeTruth.ready_count || 0))}/${escapeHtml(String(runtimeTruth.total_count || 0))} routes ready • compatibility: ${escapeHtml(String(runtimeTruth.compatibility_count || 0))}</div>
        </div>
        <div class="legal-field">
          <span class="legal-field__label">Runtime source</span>
          <div><strong>${escapeHtml(String(onboarding.resolution_label || "unknown"))}</strong></div>
          <div class="admin-user-cell__secondary">${onboarding.requires_explicit_runtime_pack ? "Нужен published/bootstrap pack, сейчас сервер ещё на neutral fallback." : "Runtime source-of-truth уже закреплён без neutral fallback."}</div>
        </div>
        <div class="legal-field">
          <span class="legal-field__label">Сигналы</span>
          <div><strong>${escapeHtml(String(issues.unresolved_count || 0))}</strong></div>
          <div class="admin-user-cell__secondary">errors: ${escapeHtml(String(issues.error_count || 0))} • warnings: ${escapeHtml(String(issues.warning_count || 0))}</div>
        </div>
        <div class="legal-field">
          <span class="legal-field__label">Последнее изменение</span>
          <div><strong>${escapeHtml(String(latestAudit?.title || "—"))}</strong></div>
          <div class="admin-user-cell__secondary">${escapeHtml(String(latestAudit?.created_at || "—"))}</div>
        </div>
        <div class="legal-field">
          <span class="legal-field__label">Быстрые действия</span>
          <div class="admin-section-toolbar">
            <button type="button" class="ghost-button" data-server-workspace-switch="laws">Законы</button>
            <button type="button" class="ghost-button" data-server-workspace-switch="features">Функции</button>
            <button type="button" class="ghost-button" data-server-workspace-switch="templates">Шаблоны</button>
            <button type="button" class="ghost-button" data-server-workspace-switch="users">Пользователи</button>
            <button type="button" class="ghost-button" data-server-workspace-switch="access">Доступ</button>
            <button type="button" class="ghost-button" data-server-workspace-switch="audit">Аудит</button>
            <button type="button" class="ghost-button" data-server-workspace-switch="errors">Проблемы</button>
            <a class="ghost-button button-link" href="/admin/audit">Global users / audit</a>
          </div>
        </div>
        <div class="legal-field">
          <span class="legal-field__label">Operational loop</span>
          <div class="admin-section-toolbar">
            <span class="admin-badge ${badgeClass(accessSummary.status)}">access: ${escapeHtml(statusLabel(accessSummary.status || "partial"))}</span>
            <span class="admin-badge ${badgeClass(auditSummary.status)}">audit: ${escapeHtml(statusLabel(auditSummary.status || "partial"))}</span>
            <span class="admin-badge ${badgeClass(issuesSummary.status)}">issues: ${escapeHtml(statusLabel(issuesSummary.status || "partial"))}</span>
          </div>
          <div class="admin-user-cell__secondary">${escapeHtml(String(issuesSummary.next_step || accessSummary.next_step || auditSummary.next_step || "Откройте смежные вкладки сервера, чтобы отработать доступ, аудит и проблемы."))}</div>
        </div>
      `;
    }

    function renderOverview() {
      const hostNode = document.getElementById("admin-server-workspace-panel-overview");
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      const readiness = state.workspace?.readiness || {};
      const blocks = readiness.blocks || {};
      const onboardingSummary = state.workspace?.overview?.onboarding || {};
      const runtimeTruth = state.workspace?.overview?.runtime_truth || state.workspace?.health?.runtime_requirements || {};
      const candidateRuntimeTruth = state.workspace?.overview?.candidate_runtime_truth || state.workspace?.overview?.runtime_pack?.candidate_runtime_requirements || {};
      const runtimeFocus = state.workspace?.overview?.runtime_focus || {};
      const strictCutoverCandidates = state.workspace?.overview?.strict_cutover_candidates || {};
      const runtimePack = state.workspace?.overview?.runtime_pack || {};
      const dashboard = state.workspace?.overview?.dashboard || {};
      const issues = state.issuesData || state.workspace?.issues || {};
      const accessSummary = state.accessSummary?.summary || state.workspace?.overview?.access?.summary || {};
      const auditSummary = state.auditData?.summary || {};
      const issuesSummary = issues.summary || {};
      const auditItems = Array.isArray(state.auditData?.items) ? state.auditData.items : [];
      const activityItems = Array.isArray(state.workspace?.activity) ? state.workspace.activity.slice(0, 8) : [];
      const warningSignals = Array.isArray(dashboard.release?.warning_signals) ? dashboard.release.warning_signals : [];
      const recentIssues = Array.isArray(issues.items) ? issues.items.slice(0, 4) : [];
      const onboarding = state.workspace?.health?.onboarding || {};
      const onboardingSteps = Array.isArray(onboardingSummary.steps) ? onboardingSummary.steps : [];
      const onboardingStates = Array.isArray(onboardingSummary.states) ? onboardingSummary.states : [];
      const runtimeTruthItems = Array.isArray(runtimeTruth.items) ? runtimeTruth.items : [];
      const candidateRuntimeTruthItems = Array.isArray(candidateRuntimeTruth.items) ? candidateRuntimeTruth.items : [];
      const strictCutoverItems = Array.isArray(strictCutoverCandidates.items) ? strictCutoverCandidates.items : [];
      const onboardingNextFocus = onboardingSummary.next_focus || {};
      const recentChanges = auditItems
        .filter((item) => ["workflow_audit", "content_audit", "law_projection"].includes(String(item.kind || "")))
        .slice(0, 5);
      const blockCards = [
        {
          key: "laws",
          title: "Законы",
          status: blocks.laws?.status,
          detail: `bindings: ${escapeHtml(String(state.lawsSummary?.bindings?.length || state.workspace?.overview?.laws?.binding_count || 0))} • effective: ${escapeHtml(String(state.lawsEffective?.summary?.count || 0))}`,
        },
        {
          key: "features",
          title: "Функции",
          status: blocks.features?.status,
          detail: `effective: ${escapeHtml(String(state.featuresData?.counts?.effective || 0))} • overrides: ${escapeHtml(String(state.featuresData?.counts?.server || 0))}`,
        },
        {
          key: "templates",
          title: "Шаблоны вывода",
          status: blocks.templates?.status,
          detail: `effective: ${escapeHtml(String(state.templatesData?.counts?.effective || 0))} • overrides: ${escapeHtml(String(state.templatesData?.counts?.server || 0))}`,
        },
        {
          key: "access",
          title: "Доступ",
          status: accessSummary.status || (Number(issues.error_count || 0) > 0 ? "partial" : "ready"),
          detail: escapeHtml(String(accessSummary.detail || `users: ${String(getAccessItems().length || 0)} • roles: ${String(state.rolesData?.items?.length || 0)}`)),
        },
      ];
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Обзор сервера</span>
            <p class="legal-section__description">Понятная сводка по готовности сервера, последним изменениям и проблемам без сырой технички по умолчанию.</p>
          </div>
        </div>
        <div class="legal-subcard">
          <div class="legal-subcard__header">
            <div>
              <span class="legal-field__label">Runtime truth</span>
              <p class="legal-section__description">Эти verdict’ы должны совпадать с тем, что реально используют migrated runtime routes. Если здесь блокировка, в проде маршрут тоже не должен считаться готовым.</p>
            </div>
          </div>
          <div class="legal-field-grid legal-field-grid--two">
            <div class="legal-field">
              <span class="legal-field__label">Summary</span>
              <div><span class="admin-badge ${badgeClass(runtimeTruth.status)}">${escapeHtml(statusLabel(runtimeTruth.status || "partial"))}</span></div>
              <div class="admin-user-cell__secondary">ready: ${escapeHtml(String(runtimeTruth.ready_count || 0))}/${escapeHtml(String(runtimeTruth.total_count || 0))} • blocked: ${escapeHtml(String(runtimeTruth.blocked_count || 0))} • compatibility: ${escapeHtml(String(runtimeTruth.compatibility_count || 0))}</div>
            </div>
            ${
              runtimeTruthItems.slice(0, 3).map((item) => `
                <div class="legal-field">
                  <span class="legal-field__label">${escapeHtml(String(item.section_code || item.capability_code || "capability"))}</span>
                  <div><span class="admin-badge ${badgeClass(item.route_status)}">${escapeHtml(statusLabel(item.route_status || "partial"))}</span></div>
                  <div class="admin-user-cell__secondary">${escapeHtml(String(item.route_reason_code || "—"))}</div>
                  <div class="admin-user-cell__secondary">${escapeHtml(String(item.route_reason_detail || "—"))}</div>
                </div>
              `).join("")
            }
          </div>
          <div class="admin-user-cell__secondary">
            current published pack: ${escapeHtml(String(runtimePack.published_version || 0))} • rollback available: ${escapeHtml(String(Boolean(runtimePack.rollback?.available)))}
            ${runtimePack.rollback?.target_version ? ` • target version: ${escapeHtml(String(runtimePack.rollback.target_version))}` : ""}
          </div>
        </div>
        <div class="legal-subcard">
          <div class="legal-subcard__header">
            <div>
              <span class="legal-field__label">Candidate publish truth</span>
              <p class="legal-section__description">Это прогноз shared runtime gate для кандидата pack publish. Он показывает, что станет доступно после publish, а не только текущее live-состояние.</p>
            </div>
          </div>
          <div class="legal-field-grid legal-field-grid--two">
            <div class="legal-field">
              <span class="legal-field__label">Summary</span>
              <div><span class="admin-badge ${badgeClass(candidateRuntimeTruth.status)}">${escapeHtml(statusLabel(candidateRuntimeTruth.status || "partial"))}</span></div>
              <div class="admin-user-cell__secondary">ready: ${escapeHtml(String(candidateRuntimeTruth.ready_count || 0))}/${escapeHtml(String(candidateRuntimeTruth.total_count || 0))} • blocked: ${escapeHtml(String(candidateRuntimeTruth.blocked_count || 0))} • compatibility: ${escapeHtml(String(candidateRuntimeTruth.compatibility_count || 0))}</div>
            </div>
            ${
              candidateRuntimeTruthItems.slice(0, 3).map((item) => `
                <div class="legal-field">
                  <span class="legal-field__label">${escapeHtml(String(item.section_code || item.capability_code || "capability"))}</span>
                  <div><span class="admin-badge ${badgeClass(item.route_status)}">${escapeHtml(statusLabel(item.route_status || "partial"))}</span></div>
                  <div class="admin-user-cell__secondary">${escapeHtml(String(item.route_reason_code || "—"))}</div>
                  <div class="admin-user-cell__secondary">${escapeHtml(String(item.route_reason_detail || "—"))}</div>
                </div>
              `).join("")
            }
          </div>
          <div class="admin-user-cell__secondary">
            publish blockers: ${escapeHtml(String(runtimePack.count || 0))} • can publish: ${escapeHtml(String(Boolean(runtimePack.can_publish)))}
          </div>
        </div>
        <div class="legal-subcard">
          <div class="legal-subcard__header">
            <div>
              <span class="legal-field__label">Next runtime focus</span>
              <p class="legal-section__description">Один короткий операторский сигнал: что именно сейчас мешает следующему publish или strict cutover для migrated flows.</p>
            </div>
          </div>
          <div class="legal-field-grid legal-field-grid--two">
            <div class="legal-field">
              <span class="legal-field__label">Summary</span>
              <div><span class="admin-badge ${badgeClass(runtimeFocus.status)}">${escapeHtml(statusLabel(runtimeFocus.status || "partial"))}</span></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeFocus.message || "—"))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Target</span>
              <div><strong>${escapeHtml(String(runtimeFocus.section_code || "all_migrated_flows"))}</strong></div>
              <div class="admin-user-cell__secondary">source=${escapeHtml(String(runtimeFocus.source || "current"))} • verdict=${escapeHtml(String(runtimeFocus.route_status || runtimeFocus.status || "ready"))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Reason</span>
              <div><strong>${escapeHtml(String(runtimeFocus.reason_code || "aligned"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeFocus.reason_detail || "Current runtime truth and candidate publish truth are aligned."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Next action</span>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeFocus.next_action || "No immediate runtime cutover action is required."))}</div>
            </div>
          </div>
        </div>
        <div class="legal-subcard">
          <div class="legal-subcard__header">
            <div>
              <span class="legal-field__label">Strict cutover candidates</span>
              <p class="legal-section__description">Derived rollout view for migrated flows: can we already flip strict runtime, is it already active, or is candidate publish truth still blocking the cutover?</p>
            </div>
          </div>
          <div class="legal-field-grid legal-field-grid--two">
            <div class="legal-field">
              <span class="legal-field__label">Summary</span>
              <div><span class="admin-badge ${badgeClass(strictCutoverCandidates.status)}">${escapeHtml(statusLabel(strictCutoverCandidates.status || "partial"))}</span></div>
              <div class="admin-user-cell__secondary">ready_to_flip: ${escapeHtml(String(strictCutoverCandidates.ready_to_flip_count || 0))} • strict_active: ${escapeHtml(String(strictCutoverCandidates.strict_active_count || 0))} • blocked: ${escapeHtml(String(strictCutoverCandidates.blocked_count || 0))}</div>
            </div>
            ${
              strictCutoverItems.slice(0, 3).map((item) => `
                <div class="legal-field">
                  <span class="legal-field__label">${escapeHtml(String(item.section_code || "capability"))}</span>
                  <div><span class="admin-badge ${badgeClass(item.status)}">${escapeHtml(statusLabel(item.status || "partial"))}</span></div>
                  <div class="admin-user-cell__secondary">${escapeHtml(String(item.detail || "—"))}</div>
                  <div class="admin-user-cell__secondary">${escapeHtml(String(item.next_action || "—"))}</div>
                  <div class="admin-user-cell__secondary">strict: ${escapeHtml(String(item.strict_env || "—"))}</div>
                  <div class="admin-user-cell__secondary">rollback: ${escapeHtml(String(item.rollback_env || "—"))}</div>
                </div>
              `).join("")
            }
          </div>
        </div>
        <div class="legal-subcard">
          <div class="legal-subcard__header">
            <div>
              <span class="legal-field__label">Onboarding checklist</span>
              <p class="legal-section__description">Новый сервер нужно доводить до usable state через этот server workspace, а не через `/admin/laws` или разрозненные diagnostics surfaces.</p>
            </div>
            ${
              onboardingNextFocus.action_tab
                ? `<button type="button" class="ghost-button" data-server-workspace-switch="${escapeHtml(String(onboardingNextFocus.action_tab || ""))}">${escapeHtml(String(onboardingNextFocus.action_label || "Открыть следующий шаг"))}</button>`
                : ""
            }
          </div>
          <div class="legal-field-grid legal-field-grid--two">
            <div class="legal-field">
              <span class="legal-field__label">Usable in admin</span>
              <div><span class="admin-badge ${onboardingSummary.usable_in_admin ? "admin-badge--success" : "admin-badge--warning"}">${onboardingSummary.usable_in_admin ? "Да" : "Пока нет"}</span></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(onboardingSummary.usable_in_admin_detail || "—"))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">State progression</span>
              <div><strong>${escapeHtml(String(onboardingSummary.highest_completed_state || "not-ready"))}</strong> → ${escapeHtml(String(onboardingSummary.next_required_state || "—"))}</div>
              <div class="admin-user-cell__secondary">Primary path: ${escapeHtml(String(onboardingSummary.primary_path || `/admin/servers/${serverCode}`))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Runtime resolution</span>
              <div><strong>${escapeHtml(String(onboardingSummary.resolution?.label || onboarding.resolution_label || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">
                published=${escapeHtml(String(Boolean(onboardingSummary.resolution?.has_published_pack)))} • bootstrap=${escapeHtml(String(Boolean(onboardingSummary.resolution?.has_bootstrap_pack)))} • addressable=${escapeHtml(String(Boolean(onboardingSummary.resolution?.is_runtime_addressable)))}
              </div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Rollback reference</span>
              <div><strong>${escapeHtml(String(onboardingSummary.rollback_reference || onboarding.rollback_reference || "—"))}</strong></div>
              <div class="admin-user-cell__secondary">Используйте это как explicit rollback path для onboarding changes.</div>
            </div>
          </div>
          ${
            onboardingSteps.length
              ? `<div class="legal-field-grid legal-field-grid--two">
                  ${onboardingSteps.map((step) => `
                    <div class="legal-field">
                      <span class="legal-field__label">${escapeHtml(String(step.title || step.code || "step"))}</span>
                      <div><span class="admin-badge ${badgeClass(step.status)}">${escapeHtml(statusLabel(step.status))}</span></div>
                      <div class="admin-user-cell__secondary">${escapeHtml(String(step.detail || "—"))}</div>
                      ${
                        step.action_tab
                          ? `<div class="admin-section-toolbar"><button type="button" class="ghost-button" data-server-workspace-switch="${escapeHtml(String(step.action_tab || ""))}">${escapeHtml(String(step.action_label || "Открыть"))}</button></div>`
                          : ""
                      }
                    </div>
                  `).join("")}
                </div>`
              : ""
          }
          ${
            onboardingStates.length
              ? `<div class="legal-field-grid legal-field-grid--two">
                  ${onboardingStates.map((item) => `
                    <div class="legal-field">
                      <span class="legal-field__label">${escapeHtml(String(item.code || "state"))}</span>
                      <div><span class="admin-badge ${badgeClass(item.status)}">${escapeHtml(statusLabel(item.status))}</span></div>
                      <div class="admin-user-cell__secondary">${escapeHtml(String(item.detail || "—"))}</div>
                    </div>
                  `).join("")}
                </div>`
              : ""
          }
        </div>
        <div class="legal-subcard">
          <div class="legal-subcard__header">
            <div>
              <span class="legal-field__label">Operational admin layer</span>
              <p class="legal-section__description">Server-centric доступ, аудит и issue triage должны закрываться внутри этой карточки, а не через разрозненные глобальные поверхности.</p>
            </div>
          </div>
          <div class="legal-grid legal-grid--three">
            ${renderOperationalSummaryCard({ title: "Access summary", summary: accessSummary, actionTab: "access", actionLabel: "Открыть доступ" })}
            ${renderOperationalSummaryCard({ title: "Audit summary", summary: auditSummary, actionTab: "audit", actionLabel: "Открыть аудит" })}
            ${renderOperationalSummaryCard({ title: "Issues summary", summary: issuesSummary, actionTab: "errors", actionLabel: "Открыть проблемы" })}
          </div>
        </div>
        ${
          recentIssues.length
            ? `<div class="legal-subcard">
                <span class="legal-field__label">Требует внимания</span>
                <div class="admin-section-toolbar">
                  ${recentIssues.map((item) => `<span class="admin-badge ${issueSeverityClass(item.severity)}">${escapeHtml(String(item.title || item.issue_id || "issue"))}</span>`).join("")}
                </div>
                <p class="legal-section__description">Откройте вкладку «Ошибки / Проблемы», чтобы увидеть детали и доступные безопасные действия.</p>
              </div>`
            : '<div class="legal-subcard"><span class="legal-field__label">Требует внимания</span><p class="legal-section__description">Сейчас критичных сигналов по серверу не найдено.</p></div>'
        }
        <div class="legal-field-grid legal-field-grid--two">
          ${blockCards.map((card) => `
            <div class="legal-field">
              <span class="legal-field__label">${escapeHtml(card.title)}</span>
              <div><span class="admin-badge ${badgeClass(card.status)}">${escapeHtml(statusLabel(card.status))}</span></div>
              <div class="admin-user-cell__secondary">${card.detail}</div>
            </div>
          `).join("")}
          <div class="legal-field">
            <span class="legal-field__label">Последние обновления</span>
            <div class="admin-user-cell__secondary">publish batches: ${escapeHtml(String((dashboard.content?.publish_batches || []).length || 0))}</div>
            <div class="admin-user-cell__secondary">warning signals: ${escapeHtml(String((dashboard.release?.warning_signals || []).length || 0))}</div>
          </div>
          <div class="legal-field">
            <span class="legal-field__label">Runtime source</span>
            <div><span class="admin-badge ${onboarding.requires_explicit_runtime_pack ? "admin-badge--warning" : "admin-badge--success"}">${escapeHtml(String(onboarding.resolution_label || "unknown"))}</span></div>
            <div class="admin-user-cell__secondary">${onboarding.requires_explicit_runtime_pack ? "Сервер ещё зависит от neutral fallback. Для полной readiness нужен published/bootstrap pack." : "Сервер уже использует explicit runtime pack path."}</div>
          </div>
        </div>
        <div class="legal-field-grid legal-field-grid--two">
          <div class="legal-subcard">
            <span class="legal-field__label">Последние изменения</span>
            ${
              recentChanges.length
                ? `<ul class="legal-section__description">${recentChanges.map((item) => `<li><strong>${escapeHtml(String(item.title || item.kind || "change"))}</strong> • ${escapeHtml(String(item.created_at || "—"))}${item.description ? ` • ${escapeHtml(String(item.description || ""))}` : ""}</li>`).join("")}</ul>`
                : '<p class="legal-section__description">Пока нет recent changes для этого сервера.</p>'
            }
          </div>
          <div class="legal-subcard">
            <span class="legal-field__label">Предупреждения</span>
            ${
              warningSignals.length
                ? `<ul class="legal-section__description">${warningSignals.slice(0, 5).map((item) => `<li>${escapeHtml(String(item || ""))}</li>`).join("")}</ul>`
                : '<p class="legal-section__description">Сейчас release warning signals не зафиксированы.</p>'
            }
          </div>
        </div>
        <div class="legal-subcard">
          <span class="legal-field__label">Последняя активность</span>
          ${
            activityItems.length
              ? `<ul class="legal-section__description">${activityItems.map((item) => `<li><strong>${escapeHtml(String(item.title || item.kind || "event"))}</strong> • ${escapeHtml(String(item.created_at || "—"))} ${item.description ? `• ${escapeHtml(String(item.description || ""))}` : ""}</li>`).join("")}</ul>`
              : '<p class="legal-section__description">Для сервера пока нет recent activity.</p>'
          }
        </div>
      `;
    }

    function renderLaws() {
      const hostNode = document.getElementById("admin-server-workspace-panel-laws");
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      const laws = state.lawsSummary || {};
        const bindings = Array.isArray(laws.bindings) ? laws.bindings : [];
        const projection = laws.latest_projection_run || {};
        const runtimeConfigPosture = laws.runtime_config_posture || {};
        const runtimeConfigDebt = laws.runtime_config_debt || {};
        const runtimeResolutionPolicy = laws.runtime_resolution_policy || {};
        const runtimeProvenance = laws.runtime_provenance || {};
        const runtimeAlignment = laws.runtime_alignment || state.lawsDiff?.runtime_alignment || {};
        const runtimeItemParity = laws.runtime_item_parity || state.lawsDiff?.runtime_item_parity || {};
        const runtimeVersionParity = laws.runtime_version_parity || state.lawsDiff?.runtime_version_parity || {};
        const projectionBridgeLifecycle = laws.projection_bridge_lifecycle || state.lawsDiff?.projection_bridge_lifecycle || {};
        const projectionBridgeReadiness = laws.projection_bridge_readiness || state.lawsDiff?.projection_bridge_readiness || {};
        const promotionCandidate = laws.promotion_candidate || state.lawsDiff?.promotion_candidate || {};
        const promotionDelta = laws.promotion_delta || state.lawsDiff?.promotion_delta || {};
        const promotionBlockers = laws.promotion_blockers || state.lawsDiff?.promotion_blockers || {};
        const promotionReviewSignal = laws.promotion_review_signal || state.lawsDiff?.promotion_review_signal || {};
        const activationGap = laws.activation_gap || state.lawsDiff?.activation_gap || {};
        const runtimeShellDebt = laws.runtime_shell_debt || state.lawsDiff?.runtime_shell_debt || {};
        const runtimeConvergence = laws.runtime_convergence || state.lawsDiff?.runtime_convergence || {};
        const cutoverReadiness = laws.cutover_readiness || state.lawsDiff?.cutover_readiness || {};
        const runtimeCutoverMode = laws.runtime_cutover_mode || state.lawsDiff?.runtime_cutover_mode || {};
        const runtimeBridgePolicy = laws.runtime_bridge_policy || state.lawsDiff?.runtime_bridge_policy || {};
        const runtimeOperatingMode = laws.runtime_operating_mode || state.lawsDiff?.runtime_operating_mode || {};
        const runtimePolicyViolations = laws.runtime_policy_violations || state.lawsDiff?.runtime_policy_violations || {};
        const cutoverGuardrails = laws.cutover_guardrails || state.lawsDiff?.cutover_guardrails || {};
        const runtimePolicyEnforcement = laws.runtime_policy_enforcement || state.lawsDiff?.runtime_policy_enforcement || {};
        const policyBreachSummary = laws.policy_breach_summary || state.lawsDiff?.policy_breach_summary || {};
        const runtimeRiskRegister = laws.runtime_risk_register || state.lawsDiff?.runtime_risk_register || {};
        const runtimeGovernanceContract = laws.runtime_governance_contract || state.lawsDiff?.runtime_governance_contract || {};
        const legacyPathAllowance = laws.legacy_path_allowance || state.lawsDiff?.legacy_path_allowance || {};
        const compatibilityExitScorecard = laws.compatibility_exit_scorecard || state.lawsDiff?.compatibility_exit_scorecard || {};
        const runtimeBreachCategories = laws.runtime_breach_categories || state.lawsDiff?.runtime_breach_categories || {};
        const legacyPathControls = laws.legacy_path_controls || state.lawsDiff?.legacy_path_controls || {};
        const projectionRuntimeGate = laws.projection_runtime_gate || state.lawsDiff?.projection_runtime_gate || {};
        const compatibilityShrinkDecision = laws.compatibility_shrink_decision || state.lawsDiff?.compatibility_shrink_decision || {};
        const runtimeExceptionRegister = laws.runtime_exception_register || state.lawsDiff?.runtime_exception_register || {};
        const compatibilityPathMatrix = laws.compatibility_path_matrix || state.lawsDiff?.compatibility_path_matrix || {};
        const nextShrinkStep = laws.next_shrink_step || state.lawsDiff?.next_shrink_step || {};
        const shrinkSequence = laws.shrink_sequence || state.lawsDiff?.shrink_sequence || {};
        const bridgeShrinkChecklist = laws.bridge_shrink_checklist || state.lawsDiff?.bridge_shrink_checklist || {};
        const cutoverBlockersBreakdown = laws.cutover_blockers_breakdown || state.lawsDiff?.cutover_blockers_breakdown || {};
        const effective = state.lawsEffective || {};
      const bindingEditor = buildLawBindingEditorState();
      const manualEditor = buildLawManualEditorState();
      const sourceSetOptions = getLawSourceSetItems();
      const projectionStatus = state.lawProjectionStatus || {};
      const projectionStatusRun = projectionStatus.run || {};
      const projectionMaterialization = projectionStatus.materialization || {};
      const projectionActivation = projectionStatus.activation || {};
      const projectionRuntimeAlignment = projectionStatus.runtime_alignment || {};
      const effectiveItems = Array.isArray(effective.items) ? effective.items.slice(0, 12) : [];
      const fillSummary = laws.fill_check || effective.summary || {};
      const diffSummary = laws.diff || state.lawsDiff?.summary || {};
      const health = laws.health || {};
      const bindingSource = String(laws.binding_source || state.lawsDiff?.binding_source || "").trim() || "unknown";
      const canonicalBindingReady = Boolean(
        typeof laws.canonical_binding_ready === "boolean"
          ? laws.canonical_binding_ready
          : state.lawsDiff?.canonical_binding_ready,
      );
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Законы</span>
            <p class="legal-section__description">Основной путь: выбрать source sets, проверить итоговую выборку законов и безопасно обновить preview без runtime activation.</p>
          </div>
          <div class="admin-section-toolbar">
            <button type="button" id="admin-server-laws-add-manual" class="secondary-button">Добавить закон вручную</button>
            <button type="button" id="admin-server-laws-add-binding" class="secondary-button">Добавить binding</button>
            <button type="button" id="admin-server-laws-refresh-preview" class="primary-button">Обновить законы</button>
            <button type="button" id="admin-server-laws-recheck" class="secondary-button">Проверить наполнение</button>
            <button type="button" id="admin-server-laws-reload" class="ghost-button">Обновить блок</button>
            <button type="button" id="admin-server-laws-open-diagnostics" class="ghost-button">Диагностика</button>
            <a class="ghost-button button-link" href="/admin/laws">Открыть laws diagnostics</a>
          </div>
        </div>
        <div class="legal-field-grid legal-field-grid--two">
          <div class="legal-field">
            <span class="legal-field__label">Runtime health</span>
            <div><strong>${escapeHtml(String(laws.health?.active_law_version_id || "—"))}</strong></div>
            <div class="admin-user-cell__secondary">chunks: ${escapeHtml(String(health.chunk_count || 0))} • status: ${escapeHtml(String(health.ok ? "ready" : "check"))}</div>
          </div>
          <div class="legal-field">
            <span class="legal-field__label">Последний preview</span>
            <div><strong>${escapeHtml(String(projection.id || "—"))}</strong></div>
            <div class="admin-user-cell__secondary">status: ${escapeHtml(String(projection.status || "none"))} • selected: ${escapeHtml(String(projection.selected_count || 0))}</div>
          </div>
            <div class="legal-field">
              <span class="legal-field__label">Config posture</span>
              <div><strong>${escapeHtml(String(runtimeConfigPosture.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeConfigPosture.next_step || runtimeConfigPosture.detail || "Runtime config posture summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Config debt</span>
              <div><strong>${escapeHtml(String(runtimeConfigDebt.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeConfigDebt.detail || "Runtime config debt summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Resolution policy</span>
              <div><strong>${escapeHtml(String(runtimeResolutionPolicy.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeResolutionPolicy.next_step || runtimeResolutionPolicy.detail || "Runtime resolution policy summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Runtime provenance</span>
              <div><strong>${escapeHtml(String(runtimeProvenance.mode || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeProvenance.detail || "Runtime source-of-truth explanation is not available yet."))}</div>
            </div>
          <div class="legal-field">
            <span class="legal-field__label">Runtime alignment</span>
            <div><strong>${escapeHtml(String(runtimeAlignment.status || "unknown"))}</strong></div>
            <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeAlignment.detail || "Active runtime shell and promoted projection alignment is not available yet."))}</div>
          </div>
            <div class="legal-field">
              <span class="legal-field__label">Bindings posture</span>
              <div><strong>${escapeHtml(canonicalBindingReady ? "canonical" : bindingSource)}</strong></div>
              <div class="admin-user-cell__secondary">source: ${escapeHtml(bindingSource)} • ${canonicalBindingReady ? "Canonical source-set bindings already drive laws readiness." : "Legacy runtime bindings or missing canonical bindings still keep this server on compatibility posture."}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Item parity</span>
              <div><strong>${escapeHtml(String(runtimeItemParity.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">runtime: ${escapeHtml(String(runtimeItemParity.runtime_count || 0))} • projection: ${escapeHtml(String(runtimeItemParity.projection_count || 0))} • shared: ${escapeHtml(String(runtimeItemParity.shared_count || 0))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Version parity</span>
              <div><strong>${escapeHtml(String(runtimeVersionParity.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">active: ${escapeHtml(String(runtimeVersionParity.active_law_version_id || "—"))} • projected: ${escapeHtml(String(runtimeVersionParity.projected_law_version_id || "—"))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Bridge lifecycle</span>
              <div><strong>${escapeHtml(String(projectionBridgeLifecycle.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(projectionBridgeLifecycle.detail || "Projection bridge lifecycle summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Bridge readiness</span>
              <div><strong>${escapeHtml(String(projectionBridgeReadiness.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(projectionBridgeReadiness.next_step || projectionBridgeReadiness.detail || "Projection bridge readiness summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Promotion candidate</span>
              <div><strong>${escapeHtml(String(promotionCandidate.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(promotionCandidate.next_step || promotionCandidate.detail || "Promotion candidate summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Promotion delta</span>
              <div><strong>${escapeHtml(String(promotionDelta.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(promotionDelta.detail || "Promotion delta summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Promotion blockers</span>
              <div><strong>${escapeHtml(String(promotionBlockers.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(promotionBlockers.detail || "Promotion blockers summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Promotion review</span>
              <div><strong>${escapeHtml(String(promotionReviewSignal.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(promotionReviewSignal.next_step || promotionReviewSignal.detail || "Promotion review signal is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Activation gap</span>
              <div><strong>${escapeHtml(String(activationGap.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(activationGap.detail || "Activation gap summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Runtime shell debt</span>
              <div><strong>${escapeHtml(String(runtimeShellDebt.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeShellDebt.detail || "Runtime shell debt summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Runtime convergence</span>
              <div><strong>${escapeHtml(String(runtimeConvergence.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeConvergence.detail || "Runtime convergence summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Cutover readiness</span>
              <div><strong>${escapeHtml(String(cutoverReadiness.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(cutoverReadiness.detail || "Cutover readiness summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Cutover mode</span>
              <div><strong>${escapeHtml(String(runtimeCutoverMode.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeCutoverMode.next_step || runtimeCutoverMode.detail || "Runtime cutover mode summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Bridge policy</span>
              <div><strong>${escapeHtml(String(runtimeBridgePolicy.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeBridgePolicy.next_step || runtimeBridgePolicy.detail || "Runtime bridge policy summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Operating mode</span>
              <div><strong>${escapeHtml(String(runtimeOperatingMode.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeOperatingMode.next_step || runtimeOperatingMode.detail || "Runtime operating mode summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Policy violations</span>
              <div><strong>${escapeHtml(String(runtimePolicyViolations.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimePolicyViolations.detail || "Runtime policy violations summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Cutover guardrails</span>
              <div><strong>${escapeHtml(String(cutoverGuardrails.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(cutoverGuardrails.next_step || cutoverGuardrails.detail || "Cutover guardrails summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Policy enforcement</span>
              <div><strong>${escapeHtml(String(runtimePolicyEnforcement.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimePolicyEnforcement.next_step || runtimePolicyEnforcement.detail || "Runtime policy enforcement summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Policy breach</span>
              <div><strong>${escapeHtml(String(policyBreachSummary.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(policyBreachSummary.next_step || policyBreachSummary.detail || "Runtime policy breach summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Risk register</span>
              <div><strong>${escapeHtml(String(runtimeRiskRegister.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeRiskRegister.detail || "Runtime risk register is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Governance contract</span>
              <div><strong>${escapeHtml(String(runtimeGovernanceContract.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeGovernanceContract.next_step || runtimeGovernanceContract.detail || "Runtime governance contract is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Legacy path allowance</span>
              <div><strong>${escapeHtml(String(legacyPathAllowance.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(legacyPathAllowance.next_step || legacyPathAllowance.detail || "Legacy path allowance summary is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Exit scorecard</span>
              <div><strong>${escapeHtml(String(compatibilityExitScorecard.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(compatibilityExitScorecard.next_step || compatibilityExitScorecard.detail || "Compatibility exit scorecard is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Breach categories</span>
              <div><strong>${escapeHtml(String(runtimeBreachCategories.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeBreachCategories.detail || "Runtime breach categories are not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Legacy path controls</span>
              <div><strong>${escapeHtml(String(legacyPathControls.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(legacyPathControls.next_step || legacyPathControls.detail || "Legacy path controls are not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Projection runtime gate</span>
              <div><strong>${escapeHtml(String(projectionRuntimeGate.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(projectionRuntimeGate.next_step || projectionRuntimeGate.detail || "Projection runtime gate is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Shrink decision</span>
              <div><strong>${escapeHtml(String(compatibilityShrinkDecision.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(compatibilityShrinkDecision.next_step || compatibilityShrinkDecision.detail || "Compatibility shrink decision is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Exception register</span>
              <div><strong>${escapeHtml(String(runtimeExceptionRegister.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(runtimeExceptionRegister.detail || "Runtime exception register is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Path matrix</span>
              <div><strong>${escapeHtml(String(compatibilityPathMatrix.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">exceptions: ${escapeHtml(String(compatibilityPathMatrix.exception_count || 0))} • transitions: ${escapeHtml(String(compatibilityPathMatrix.transition_count || 0))} • blocked: ${escapeHtml(String(compatibilityPathMatrix.blocked_count || 0))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Next shrink step</span>
              <div><strong>${escapeHtml(String(nextShrinkStep.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(nextShrinkStep.target_path || "—"))} • ${escapeHtml(String(nextShrinkStep.next_step || nextShrinkStep.detail || "Next shrink step is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Shrink sequence</span>
              <div><strong>${escapeHtml(String(shrinkSequence.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">ready: ${escapeHtml(String(shrinkSequence.ready_count || 0))}/${escapeHtml(String(shrinkSequence.total_count || 0))} • ${escapeHtml(String(shrinkSequence.next_step || shrinkSequence.detail || "Shrink sequence is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Bridge shrink checklist</span>
              <div><strong>${escapeHtml(String(bridgeShrinkChecklist.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(bridgeShrinkChecklist.detail || "Bridge shrink checklist is not available yet."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Cutover blockers</span>
              <div><strong>${escapeHtml(String(cutoverBlockersBreakdown.status || "unknown"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String(cutoverBlockersBreakdown.detail || "Cutover blockers breakdown is not available yet."))}</div>
            </div>
        </div>
        <div class="legal-subcard">
          <span class="legal-field__label">Source set bindings</span>
          ${
            bindings.length
              ? `<table class="legal-table admin-table admin-table--compact"><thead><tr><th>Source set</th><th>Priority</th><th>Status</th><th></th></tr></thead><tbody>${bindings.map((item) => `<tr><td>${escapeHtml(String(item.source_set_key || "—"))}</td><td>${escapeHtml(String(item.priority || 0))}</td><td>${item.is_active ? "active" : "disabled"}</td><td><button type="button" class="ghost-button" data-server-law-binding-edit="${escapeHtml(String(item.id || ""))}">Редактировать</button></td></tr>`).join("")}</tbody></table>`
              : `<p class="legal-section__description">Для сервера пока нет source set bindings. Добавьте хотя бы один активный binding прямо здесь, а laws diagnostics используйте только для расширенной сверки.</p>
                 <div class="admin-section-toolbar">
                   <a class="ghost-button button-link" href="/admin/laws">Открыть laws diagnostics</a>
                   <button type="button" class="ghost-button" data-server-workspace-switch="diagnostics">Открыть диагностику</button>
                 </div>`
          }
          ${
            bindingEditor
              ? `<div class="legal-subcard">
                  <div class="legal-subcard__header">
                    <div>
                      <span class="legal-field__label">${bindingEditor.mode === "edit" ? "Редактирование binding" : "Новый source set binding"}</span>
                      <p class="legal-section__description">Обычная настройка binding делается в карточке сервера. Advanced laws diagnostics остаются только для углублённой проверки.</p>
                    </div>
                    <div class="admin-section-toolbar">
                      <button type="button" class="ghost-button" id="admin-server-law-binding-editor-cancel">Закрыть</button>
                    </div>
                  </div>
                  <form id="admin-server-law-binding-form" class="legal-field-grid legal-field-grid--two">
                    <label class="legal-field">
                      <span class="legal-field__label">Source set</span>
                      <select name="source_set_key" class="text-input" ${bindingEditor.mode === "edit" ? "disabled" : ""} required>
                        <option value="">Выберите source set</option>
                        ${sourceSetOptions.map((item) => {
                          const sourceSetKey = String(item?.source_set_key || "");
                          const title = String(item?.title || sourceSetKey);
                          const label = title !== sourceSetKey ? `${title} (${sourceSetKey})` : sourceSetKey;
                          return `<option value="${escapeHtml(sourceSetKey)}" ${bindingEditor.sourceSetKey === sourceSetKey ? "selected" : ""}>${escapeHtml(label)}</option>`;
                        }).join("")}
                      </select>
                    </label>
                    <label class="legal-field">
                      <span class="legal-field__label">Priority</span>
                      <input name="priority" type="number" min="1" max="10000" class="text-input" value="${escapeHtml(bindingEditor.priority)}" required />
                    </label>
                    <label class="legal-field">
                      <span class="legal-field__label">Активен</span>
                      <input name="is_active" type="checkbox" ${bindingEditor.isActive ? "checked" : ""} />
                    </label>
                    ${bindingEditor.mode === "edit" ? `<input type="hidden" name="source_set_key" value="${escapeHtml(bindingEditor.sourceSetKey)}" />` : ""}
                    <div class="admin-section-toolbar">
                      <button type="submit" class="primary-button">${bindingEditor.mode === "edit" ? "Сохранить binding" : "Добавить binding"}</button>
                    </div>
                  </form>
                </div>`
              : ""
          }
        </div>
        ${
          manualEditor
            ? `<div class="legal-subcard">
                <div class="legal-subcard__header">
                  <div>
                    <span class="legal-field__label">${manualEditor.mode === "edit" ? "Редактирование закона" : "Новый закон вручную"}</span>
                    <p class="legal-section__description">Этот flow создаёт новую canonical version через существующий source set revision path. Projection/apply остаются отдельным следующим шагом.</p>
                  </div>
                  <div class="admin-section-toolbar">
                    <button type="button" class="ghost-button" id="admin-server-law-manual-editor-cancel">Закрыть</button>
                  </div>
                </div>
                <form id="admin-server-law-manual-form" class="legal-field-grid">
                  <label class="legal-field">
                    <span class="legal-field__label">Source set</span>
                    <select name="source_set_key" class="text-input" required>
                      <option value="">Выберите source set</option>
                      ${bindings.filter((item) => item.is_active).map((item) => {
                        const key = String(item.source_set_key || "");
                        return `<option value="${escapeHtml(key)}" ${manualEditor.sourceSetKey === key ? "selected" : ""}>${escapeHtml(key)}</option>`;
                      }).join("")}
                    </select>
                  </label>
                  <label class="legal-field">
                    <span class="legal-field__label">Canonical identity key</span>
                    <input name="canonical_identity_key" class="text-input" value="${escapeHtml(manualEditor.canonicalIdentityKey)}" placeholder="manual:..." />
                  </label>
                  <label class="legal-field">
                    <span class="legal-field__label">Normalized URL</span>
                    <input name="normalized_url" class="text-input" value="${escapeHtml(manualEditor.normalizedUrl)}" placeholder="https://example.com/law/article или manual://..." />
                  </label>
                  <label class="legal-field">
                    <span class="legal-field__label">Title</span>
                    <input name="title" class="text-input" value="${escapeHtml(manualEditor.title)}" required />
                  </label>
                  <label class="legal-field">
                    <span class="legal-field__label">Body</span>
                    <textarea name="body_text" class="text-input" rows="12" required>${escapeHtml(manualEditor.bodyText)}</textarea>
                  </label>
                  <div class="admin-section-toolbar">
                    <button type="submit" class="primary-button">${manualEditor.mode === "edit" ? "Сохранить новую version" : "Добавить закон"}</button>
                  </div>
                </form>
              </div>`
            : ""
        }
        <div class="legal-field-grid legal-field-grid--two">
          <div class="legal-field">
            <span class="legal-field__label">Проверка наполнения</span>
            <div><strong>${escapeHtml(String(fillSummary.with_content || 0))}/${escapeHtml(String(fillSummary.count || 0))}</strong></div>
            <div class="admin-user-cell__secondary">missing: ${escapeHtml(String(fillSummary.missing_content || 0))} • errors: ${escapeHtml(String(fillSummary.error_count || 0))}</div>
          </div>
          <div class="legal-field">
            <span class="legal-field__label">Последний diff</span>
            <div><strong>+${escapeHtml(String(diffSummary.added || 0))} / -${escapeHtml(String(diffSummary.removed || 0))}</strong></div>
            <div class="admin-user-cell__secondary">changed: ${escapeHtml(String(diffSummary.changed || 0))} • unchanged: ${escapeHtml(String(diffSummary.unchanged || 0))}</div>
          </div>
        </div>
        <div class="legal-subcard">
          <div class="legal-subcard__header">
            <div>
              <span class="legal-field__label">Projection apply</span>
              <p class="legal-section__description">server-centric safe path: preview уже собран здесь, дальше можно approve/hold/materialize/activate без перехода в diagnostics.</p>
            </div>
            <div class="admin-section-toolbar">
              <button type="button" class="ghost-button" id="admin-server-laws-approve-run" ${projection?.id ? "" : "disabled"}>Approve</button>
              <button type="button" class="ghost-button" id="admin-server-laws-hold-run" ${projection?.id ? "" : "disabled"}>Hold</button>
              <button type="button" class="ghost-button" id="admin-server-laws-materialize-run" ${projection?.id ? "" : "disabled"}>Materialize</button>
              <button type="button" class="primary-button" id="admin-server-laws-activate-run" ${projection?.id ? "" : "disabled"}>Activate</button>
            </div>
          </div>
          <div class="legal-field-grid legal-field-grid--two">
            <div class="legal-field">
              <span class="legal-field__label">Run status</span>
              <div><strong>${escapeHtml(String(projectionStatusRun.status || projection.status || "none"))}</strong></div>
              <div class="admin-user-cell__secondary">run: ${escapeHtml(String(projectionStatusRun.id || projection.id || "—"))} • trigger: ${escapeHtml(String(projectionStatusRun.trigger_mode || projection.trigger_mode || "manual"))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Decision</span>
              <div><strong>${escapeHtml(String((projectionStatusRun.summary_json || {}).decision_status || projection.decision_status || "pending"))}</strong></div>
              <div class="admin-user-cell__secondary">${escapeHtml(String((projectionStatusRun.summary_json || {}).decision_reason || "Decision ещё не зафиксирован."))}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Materialization</span>
              <div><strong>${escapeHtml(String(projectionMaterialization.law_set_id || "—"))}</strong></div>
              <div class="admin-user-cell__secondary">item count matches: ${projectionRuntimeAlignment.item_count_matches_materialization ? "yes" : "no"}</div>
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Activation</span>
              <div><strong>${escapeHtml(String(projectionActivation.law_version_id || "—"))}</strong></div>
              <div class="admin-user-cell__secondary">active matches: ${projectionRuntimeAlignment.activation_law_version_matches_active ? "yes" : "no"}</div>
            </div>
          </div>
        </div>
        <div class="legal-subcard">
          <span class="legal-field__label">Effective laws</span>
          ${
            effectiveItems.length
              ? `<table class="legal-table admin-table admin-table--compact"><thead><tr><th>Закон</th><th>Источник</th><th>Обновлено</th><th>Статус</th><th></th></tr></thead><tbody>${effectiveItems.map((item) => `<tr><td><strong>${escapeHtml(String(item.title || item.canonical_identity_key || "—"))}</strong><div class="admin-user-cell__secondary">${escapeHtml(String(item.preview_excerpt || "Без preview"))}</div></td><td>${escapeHtml(String(item.selected_source_set_key || "—"))}<div class="admin-user-cell__secondary">rev ${escapeHtml(String(item.selected_revision || 0))}</div></td><td>${escapeHtml(String(item.updated_at || "—"))}</td><td>${item.has_content ? "content ready" : "missing content"}<div class="admin-user-cell__secondary">${escapeHtml(String(item.fetch_status || "—"))} / ${escapeHtml(String(item.parse_status || "—"))}</div></td><td><button type="button" class="ghost-button" data-server-law-manual-edit="${escapeHtml(String(item.canonical_identity_key || ""))}" data-server-law-manual-source-set="${escapeHtml(String(item.selected_source_set_key || ""))}">Редактировать</button></td></tr>`).join("")}</tbody></table>`
              : `<p class="legal-section__description">Effective laws пока не рассчитаны. Нажмите «Обновить законы», чтобы получить безопасный preview, или сначала добавьте bindings.</p>
                 <div class="admin-section-toolbar">
                   <button type="button" class="ghost-button" id="admin-server-laws-refresh-preview-empty">Запустить preview</button>
                 </div>`
          }
        </div>
      `;
    }

    function renderFeatures() {
      const hostNode = document.getElementById("admin-server-workspace-panel-features");
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      const payload = state.featuresData || {};
      const items = getFeatureItems();
      const editor = state.featureEditorKey ? buildFeatureEditorState() : null;
      const summary = payload.summary || {};
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Функции</span>
            <p class="legal-section__description">Global catalog с server overrides. По умолчанию показан effective результат для текущего сервера.</p>
          </div>
          <div class="admin-section-toolbar">
            <button type="button" id="admin-server-features-add" class="primary-button">Добавить override</button>
            <button type="button" id="admin-server-features-reload" class="ghost-button">Обновить блок</button>
          </div>
        </div>
        <div class="legal-field-grid legal-field-grid--two">
          <div class="legal-field"><span class="legal-field__label">Effective</span><div><strong>${escapeHtml(String(payload?.counts?.effective || 0))}</strong></div></div>
          <div class="legal-field"><span class="legal-field__label">Server overrides</span><div><strong>${escapeHtml(String(payload?.counts?.server || 0))}</strong></div></div>
        </div>
        <div class="legal-subcard">
          <span class="legal-field__label">Workflow summary</span>
          <div><span class="admin-badge ${badgeClass(summary.status === "workflow_pending" ? "partial" : summary.status)}">${escapeHtml(statusLabel(summary.status === "workflow_pending" ? "partial" : summary.status || "unknown"))}</span></div>
          <div class="admin-user-cell__secondary">${escapeHtml(String(summary.detail || "Feature workflow summary is not available yet."))}</div>
          <div class="admin-user-cell__secondary">pending=${escapeHtml(String(summary?.counts?.active_workflow || 0))} • draft=${escapeHtml(String(summary?.counts?.draft_workflow || 0))} • review=${escapeHtml(String(summary?.counts?.in_review_workflow || 0))}</div>
          <div class="admin-user-cell__secondary">${escapeHtml(String(summary.next_step || ""))}</div>
        </div>
        ${
          items.length
            ? `<table class="legal-table admin-table admin-table--compact"><thead><tr><th>Функция</th><th>Источник</th><th>Состояние</th><th>Workflow</th><th></th></tr></thead><tbody>${items.map((item) => {
                const workflowActions = buildWorkflowActions(item);
                const effectivePayload = item?.draft_payload && Object.keys(item.draft_payload).length ? item.draft_payload : (item?.effective_payload || {});
                return `<tr>
                  <td><strong>${escapeHtml(String(item.title || item.content_key || "—"))}</strong><div class="admin-user-cell__secondary">${escapeHtml(String(item.content_key || "—"))}</div></td>
                  <td>${escapeHtml(String(item.source_scope || "global"))}<div class="admin-user-cell__secondary">override: ${item.has_server_override ? "yes" : "no"}</div></td>
                  <td>${effectivePayload.enabled ? "enabled" : "disabled"}<div class="admin-user-cell__secondary">status: ${escapeHtml(String(item.status || "draft"))}${effectivePayload.hidden ? " • hidden" : ""}</div></td>
                  <td>${item.active_change_request?.id ? `${escapeHtml(String(item.active_change_request.status || "draft"))} #${escapeHtml(String(item.active_change_request.id || ""))}` : "—"}</td>
                  <td><div class="admin-section-toolbar"><button type="button" class="ghost-button" data-server-feature-edit="${escapeHtml(String(item.content_key || ""))}">${item.has_server_override ? "Редактировать" : "Создать override"}</button>${workflowActions.map((action) => `<button type="button" class="ghost-button" data-server-feature-workflow="${escapeHtml(String(item.content_key || ""))}" data-server-feature-workflow-action="${escapeHtml(action)}" data-server-feature-cr-id="${escapeHtml(String(item.active_change_request?.id || ""))}">${escapeHtml(buildWorkflowActionLabel(action))}</button>`).join("")}</div></td>
                </tr>`;
              }).join("")}</tbody></table>`
            : '<p class="legal-section__description">Для сервера пока нет effective функций. Добавьте server override, если нужна локальная настройка, скрытие или порядок показа.</p>'
        }
        ${
          editor
            ? `<div class="legal-subcard">
                <div class="legal-subcard__header">
                  <div>
                    <span class="legal-field__label">${editor.item ? "Редактирование server override" : "Новый server override"}</span>
                    <p class="legal-section__description">Сохранение создаёт или обновляет draft override. Publish остаётся отдельным workflow action.</p>
                  </div>
                  <div class="admin-section-toolbar">
                    <button type="button" class="ghost-button" id="admin-server-feature-editor-cancel">Закрыть</button>
                  </div>
                </div>
                <form id="admin-server-feature-form" class="legal-field-grid legal-field-grid--two">
                  <label class="legal-field">
                    <span class="legal-field__label">Feature key</span>
                    <input name="content_key" class="text-input" value="${escapeHtml(editor.contentKey)}" ${editor.item ? "readonly" : ""} required />
                  </label>
                  <label class="legal-field">
                    <span class="legal-field__label">Title</span>
                    <input name="title" class="text-input" value="${escapeHtml(editor.title)}" required />
                  </label>
                  <label class="legal-field">
                    <span class="legal-field__label">Status</span>
                    <select name="status" class="text-input">
                      ${["draft", "review", "published", "active", "disabled", "archived"].map((status) => `<option value="${status}" ${editor.status === status ? "selected" : ""}>${status}</option>`).join("")}
                    </select>
                  </label>
                  <label class="legal-field">
                    <span class="legal-field__label">Порядок</span>
                    <input name="order" type="number" class="text-input" value="${escapeHtml(String(editor.order ?? ""))}" />
                  </label>
                  <label class="legal-field">
                    <span class="legal-field__label">Enabled</span>
                    <input name="enabled" type="checkbox" ${editor.enabled ? "checked" : ""} />
                  </label>
                  <label class="legal-field">
                    <span class="legal-field__label">Скрывать в UI</span>
                    <input name="hidden" type="checkbox" ${editor.hidden ? "checked" : ""} />
                  </label>
                  <details class="legal-field" ${editor.item && (editor.rollout || editor.owner || editor.notes) ? "open" : ""}>
                    <summary class="legal-field__label">Дополнительные настройки</summary>
                    <label class="legal-field">
                      <span class="legal-field__label">Rollout</span>
                      <input name="rollout" class="text-input" value="${escapeHtml(editor.rollout)}" />
                    </label>
                    <label class="legal-field">
                      <span class="legal-field__label">Owner</span>
                      <input name="owner" class="text-input" value="${escapeHtml(editor.owner)}" />
                    </label>
                    <label class="legal-field">
                      <span class="legal-field__label">Notes</span>
                      <textarea name="notes" class="text-input" rows="4">${escapeHtml(editor.notes)}</textarea>
                    </label>
                  </details>
                  <div class="admin-section-toolbar">
                    <button type="submit" id="admin-server-feature-save" class="primary-button">Сохранить черновик</button>
                  </div>
                </form>
              </div>`
            : '<p class="legal-section__description">Выберите функцию из списка или создайте новый override, если нужно серверное включение, скрытие, локальный rollout или порядок показа.</p>'
        }
      `;
    }

    function renderTemplates() {
      const hostNode = document.getElementById("admin-server-workspace-panel-templates");
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      const payload = state.templatesData || {};
      const items = getTemplateItems();
      const editor = state.templateEditorKey ? buildTemplateEditorState() : null;
      const preview = editor ? state.templatePreviewByKey[editor.contentKey] : null;
      const placeholders = editor ? state.templatePlaceholdersByKey[editor.contentKey] : null;
      const summary = payload.summary || {};
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Шаблоны вывода</span>
            <p class="legal-section__description">Server override меняет BBCode без переписывания global defaults. Preview и placeholders доступны прямо здесь.</p>
          </div>
          <div class="admin-section-toolbar">
            <button type="button" id="admin-server-templates-add" class="primary-button">Добавить шаблон</button>
            <button type="button" id="admin-server-templates-reload" class="ghost-button">Обновить блок</button>
          </div>
        </div>
        <div class="legal-field-grid legal-field-grid--two">
          <div class="legal-field"><span class="legal-field__label">Effective</span><div><strong>${escapeHtml(String(payload?.counts?.effective || 0))}</strong></div></div>
          <div class="legal-field"><span class="legal-field__label">Server overrides</span><div><strong>${escapeHtml(String(payload?.counts?.server || 0))}</strong></div></div>
        </div>
        <div class="legal-subcard">
          <span class="legal-field__label">Workflow summary</span>
          <div><span class="admin-badge ${badgeClass(summary.status === "workflow_pending" ? "partial" : summary.status)}">${escapeHtml(statusLabel(summary.status === "workflow_pending" ? "partial" : summary.status || "unknown"))}</span></div>
          <div class="admin-user-cell__secondary">${escapeHtml(String(summary.detail || "Template workflow summary is not available yet."))}</div>
          <div class="admin-user-cell__secondary">pending=${escapeHtml(String(summary?.counts?.active_workflow || 0))} • draft=${escapeHtml(String(summary?.counts?.draft_workflow || 0))} • review=${escapeHtml(String(summary?.counts?.in_review_workflow || 0))}</div>
          <div class="admin-user-cell__secondary">${escapeHtml(String(summary.next_step || ""))}</div>
        </div>
        ${
          items.length
            ? `<table class="legal-table admin-table admin-table--compact"><thead><tr><th>Шаблон</th><th>Источник</th><th>Статус</th><th>Workflow</th><th></th></tr></thead><tbody>${items.map((item) => {
                const workflowActions = buildWorkflowActions(item);
                const draftPayload = item?.draft_payload || {};
                const effectivePayload = item?.effective_payload || {};
                const body = String(draftPayload.body || effectivePayload.body || "");
                return `<tr>
                  <td><strong>${escapeHtml(String(item.title || item.content_key || "—"))}</strong><div class="admin-user-cell__secondary">${escapeHtml(String(item.content_key || "—"))}</div></td>
                  <td>${escapeHtml(String(item.source_scope || "global"))}<div class="admin-user-cell__secondary">override: ${item.has_server_override ? "yes" : "no"}</div></td>
                  <td>${escapeHtml(String(item.status || "draft"))}<div class="admin-user-cell__secondary">${escapeHtml(body.slice(0, 120) || "Пустой шаблон")}</div></td>
                  <td>${item.active_change_request?.id ? `${escapeHtml(String(item.active_change_request.status || "draft"))} #${escapeHtml(String(item.active_change_request.id || ""))}` : "—"}</td>
                  <td><div class="admin-section-toolbar"><button type="button" class="ghost-button" data-server-template-edit="${escapeHtml(String(item.content_key || ""))}">${item.has_server_override ? "Редактировать" : "Создать override"}</button>${item.source_scope === "server" ? `<button type="button" class="ghost-button" data-server-template-reset="${escapeHtml(String(item.content_key || ""))}">Reset</button>` : ""}${workflowActions.map((action) => `<button type="button" class="ghost-button" data-server-template-workflow="${escapeHtml(String(item.content_key || ""))}" data-server-template-workflow-action="${escapeHtml(action)}" data-server-template-cr-id="${escapeHtml(String(item.active_change_request?.id || ""))}">${escapeHtml(buildWorkflowActionLabel(action))}</button>`).join("")}</div></td>
                </tr>`;
              }).join("")}</tbody></table>`
            : '<p class="legal-section__description">Для сервера пока нет effective шаблонов. Добавьте override, если нужен серверный BBCode, preview или reset к global default.</p>'
        }
        ${
          editor
            ? `<div class="legal-subcard">
                <div class="legal-subcard__header">
                  <div>
                    <span class="legal-field__label">${editor.item ? "Редактирование BBCode template override" : "Новый server template override"}</span>
                    <p class="legal-section__description">Сохранение создаёт draft override. Publish остаётся отдельным workflow action.</p>
                  </div>
                  <div class="admin-section-toolbar">
                    <button type="button" class="ghost-button" id="admin-server-template-editor-cancel">Закрыть</button>
                  </div>
                </div>
                <form id="admin-server-template-form" class="legal-field-grid">
                  <label class="legal-field">
                    <span class="legal-field__label">Template key</span>
                    <input name="content_key" class="text-input" value="${escapeHtml(editor.contentKey)}" ${editor.item ? "readonly" : ""} required />
                  </label>
                  <label class="legal-field">
                    <span class="legal-field__label">Title</span>
                    <input name="title" class="text-input" value="${escapeHtml(editor.title)}" required />
                  </label>
                  <label class="legal-field">
                    <span class="legal-field__label">Status</span>
                    <select name="status" class="text-input">
                      ${["draft", "review", "published", "active", "disabled", "archived"].map((status) => `<option value="${status}" ${editor.status === status ? "selected" : ""}>${status}</option>`).join("")}
                    </select>
                  </label>
                  <label class="legal-field">
                    <span class="legal-field__label">Body (BBCode)</span>
                    <textarea name="body" class="text-input" rows="12" required>${escapeHtml(editor.body)}</textarea>
                  </label>
                  <details class="legal-field" ${editor.item && editor.notes ? "open" : ""}>
                    <summary class="legal-field__label">Дополнительные настройки</summary>
                    <label class="legal-field">
                      <span class="legal-field__label">Format</span>
                      <input name="format" class="text-input" value="${escapeHtml(editor.format)}" />
                    </label>
                    <label class="legal-field">
                      <span class="legal-field__label">Notes</span>
                      <textarea name="notes" class="text-input" rows="4">${escapeHtml(editor.notes)}</textarea>
                    </label>
                    <label class="legal-field">
                      <span class="legal-field__label">Sample JSON для preview</span>
                      <textarea name="sample_json" class="text-input" rows="5">${escapeHtml(JSON.stringify(preview?.sample_json || {}, null, 2))}</textarea>
                    </label>
                  </details>
                  <div class="admin-section-toolbar">
                    <button type="submit" id="admin-server-template-save" class="primary-button">Сохранить черновик</button>
                    <button type="button" id="admin-server-template-preview" class="secondary-button">Предпросмотр</button>
                    ${editor.item ? `<button type="button" id="admin-server-template-reset" class="ghost-button">Сбросить к global default</button>` : ""}
                  </div>
                </form>
                <div class="legal-field-grid legal-field-grid--two">
                  <div class="legal-field">
                    <span class="legal-field__label">Placeholder-справка</span>
                    ${
                      placeholders?.items?.length
                        ? `<div class="admin-section-toolbar">${placeholders.items.map((item) => `<span class="admin-badge admin-badge--muted">${escapeHtml(String(item.name || ""))}</span>`).join("")}</div>`
                        : '<div class="admin-user-cell__secondary">Справка загрузится после открытия шаблона.</div>'
                    }
                  </div>
                  <div class="legal-field">
                    <span class="legal-field__label">Preview</span>
                    <pre class="legal-field__hint">${escapeHtml(String(preview?.preview || "Нажмите «Предпросмотр», чтобы увидеть итоговый BBCode."))}</pre>
                  </div>
                </div>
              </div>`
            : '<p class="legal-section__description">Выберите шаблон из списка, чтобы настроить server override, сделать preview, посмотреть placeholders или выполнить reset к global default.</p>'
        }
      `;
    }

    function renderUsers() {
      const hostNode = document.getElementById("admin-server-workspace-panel-users");
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      const users = getAccessItems();
      const accessSummary = state.accessSummary?.summary || state.workspace?.overview?.access?.summary || {};
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Пользователи сервера</span>
            <p class="legal-section__description">Пользователи текущего server scope с быстрыми действиями по доступу и переходом в настройки ролей.</p>
          </div>
          <div class="admin-section-toolbar">
            <button type="button" id="admin-server-users-reload" class="ghost-button">Обновить блок</button>
            <a class="ghost-button button-link" href="/admin/audit">Открыть users / audit</a>
          </div>
        </div>
        ${renderOperationalSummaryCard({ title: "User operations summary", summary: accessSummary, actionTab: "access", actionLabel: "Открыть доступ" })}
        ${
          users.length
            ? `<table class="legal-table admin-table admin-table--compact"><thead><tr><th>User</th><th>Email</th><th>Flags</th><th>Status</th><th>Действия</th></tr></thead><tbody>${users.map((item) => {
                const username = String(item.username || "").trim();
                const selected = normalizeKey(username) === normalizeKey(state.selectedAccessUsername);
                return `<tr>
                  <td>
                    <button type="button" class="ghost-button" data-server-access-select-user="${escapeHtml(username)}">${escapeHtml(String(item.display_name || username || "—"))}</button>
                    ${selected ? `<div class="admin-user-cell__secondary">выбран для доступа</div>` : ""}
                  </td>
                  <td>${escapeHtml(String(item.email || "—"))}</td>
                  <td>${item.is_tester ? "tester " : ""}${item.is_gka ? "gka" : ""}</td>
                  <td>${item.is_blocked ? "blocked" : item.is_deactivated ? "deactivated" : "active"}</td>
                  <td>
                    <div class="admin-section-toolbar">
                      ${item.is_tester
                        ? `<button type="button" class="ghost-button" data-server-user-action="revoke-tester" data-server-username="${escapeHtml(username)}">Снять тестера</button>`
                        : `<button type="button" class="ghost-button" data-server-user-action="grant-tester" data-server-username="${escapeHtml(username)}">Выдать тестера</button>`}
                      ${item.is_gka
                        ? `<button type="button" class="ghost-button" data-server-user-action="revoke-gka" data-server-username="${escapeHtml(username)}">Снять ГКА</button>`
                        : `<button type="button" class="ghost-button" data-server-user-action="grant-gka" data-server-username="${escapeHtml(username)}">Выдать ГКА</button>`}
                      ${item.is_blocked
                        ? `<button type="button" class="ghost-button" data-server-user-action="unblock" data-server-username="${escapeHtml(username)}">Разблокировать</button>`
                        : `<button type="button" class="ghost-button" data-server-user-action="block" data-server-username="${escapeHtml(username)}">Блок</button>`}
                      ${item.is_deactivated
                        ? `<button type="button" class="ghost-button" data-server-user-action="reactivate" data-server-username="${escapeHtml(username)}">Реактивировать</button>`
                        : `<button type="button" class="ghost-button" data-server-user-action="deactivate" data-server-username="${escapeHtml(username)}">Деактивировать</button>`}
                    </div>
                  </td>
                </tr>`;
              }).join("")}</tbody></table>`
            : '<p class="legal-section__description">Для сервера пока нет пользователей в выбранном server scope.</p>'
        }
      `;
    }

    function renderAccess() {
      const hostNode = document.getElementById("admin-server-workspace-panel-access");
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      const access = state.accessSummary || state.workspace?.overview?.access || {};
      const items = Array.isArray(access.items) ? access.items : [];
      const totals = Array.isArray(access.permission_totals) ? access.permission_totals : [];
      const roles = Array.isArray(state.rolesData?.items) ? state.rolesData.items : [];
      const permissions = Array.isArray(state.permissionsData?.items) ? state.permissionsData.items : [];
      const accessSummary = access.summary || {};
      const selectedUser = getSelectedAccessUser();
      const selectedAssignments = Array.isArray(selectedUser?.assignments) ? selectedUser.assignments : [];
      const selectedPermissions = Array.isArray(selectedUser?.permissions) ? selectedUser.permissions : [];
      const highlightedRoleCodes = new Set(selectedAssignments.map((entry) => normalizeKey(entry?.role_code)));
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Роли / Доступ</span>
            <p class="legal-section__description">Назначение ролей и понятное объяснение effective доступа для выбранного сервера без ухода в raw RBAC-таблицы.</p>
          </div>
          <div class="admin-section-toolbar">
            <button type="button" id="admin-server-access-reload" class="ghost-button">Обновить блок</button>
          </div>
        </div>
        ${renderOperationalSummaryCard({ title: "Access summary", summary: accessSummary, actionTab: "users", actionLabel: "Открыть пользователей" })}
        <div class="legal-subcard">
          <span class="legal-field__label">Permission totals</span>
          ${
            totals.length
              ? `<div class="admin-section-toolbar">${totals.map((item) => `<span class="admin-badge admin-badge--muted">${escapeHtml(String(item.code || ""))}: ${escapeHtml(String(item.count || 0))}</span>`).join("")}</div>`
                : '<p class="legal-section__description">Разрешения для сервера пока не вычислены.</p>'
            }
          </div>
          <div class="legal-field-grid legal-field-grid--two">
            <div class="legal-field">
            <span class="legal-field__label">Назначить роль</span>
            ${
              items.length && roles.length
                ? `<form id="admin-server-role-assignment-form" class="admin-form-stack">
                    <label class="legal-field">
                      <span class="legal-field__label">Пользователь</span>
                      <select name="username" class="text-input">
                        ${items.map((item) => {
                          const username = String(item.username || "").trim();
                          const selected = normalizeKey(username) === normalizeKey(selectedUser?.username || "");
                          return `<option value="${escapeHtml(username)}" ${selected ? "selected" : ""}>${escapeHtml(String(item.display_name || username))}</option>`;
                        }).join("")}
                      </select>
                    </label>
                    <label class="legal-field">
                      <span class="legal-field__label">Роль</span>
                      <select name="role_code" class="text-input">
                        ${roles.map((role) => `<option value="${escapeHtml(String(role.code || ""))}">${escapeHtml(String(role.name || role.code || ""))}</option>`).join("")}
                      </select>
                    </label>
                    <label class="legal-field">
                      <span class="legal-field__label">Scope</span>
                      <select name="scope" class="text-input">
                        <option value="server" selected>Только этот сервер</option>
                        <option value="global">Global</option>
                      </select>
                    </label>
                    <div class="admin-section-toolbar">
                      <button type="submit" class="primary-button">Назначить роль</button>
                    </div>
                    </form>`
                  : '<p class="legal-section__description">Сначала убедитесь, что у сервера есть пользователи и доступен каталог ролей.</p>'
              }
            </div>
            <div class="legal-field">
              <span class="legal-field__label">Выбранный пользователь</span>
              ${
                selectedUser
                  ? `<div><strong>${escapeHtml(String(selectedUser.display_name || selectedUser.username || "—"))}</strong></div>
                     <div class="admin-user-cell__secondary">${escapeHtml(String(selectedUser.username || ""))}</div>
                     <div class="admin-section-toolbar">
                       ${selectedAssignments.length
                         ? selectedAssignments.map((entry) => `<span class="admin-badge admin-badge--muted">${escapeHtml(String(entry.role_name || entry.role_code || ""))}${entry.scope === "global" ? " • global" : ""}</span>`).join("")
                         : '<span class="admin-badge admin-badge--muted">Нет явных ролей</span>'}
                     </div>
                     <div class="admin-user-cell__secondary">Flags: ${selectedUser.is_tester ? "tester " : ""}${selectedUser.is_gka ? "gka " : ""}${selectedUser.is_blocked ? "blocked" : selectedUser.is_deactivated ? "deactivated" : "active"}</div>
                     <div class="admin-section-toolbar">
                       ${selectedPermissions.length
                         ? selectedPermissions.map((code) => `<span class="admin-badge admin-badge--muted" title="${escapeHtml(permissionLabel(code, permissions))}">${escapeHtml(String(code))}</span>`).join("")
                         : '<span class="admin-badge admin-badge--muted">Нет effective permissions</span>'}
                     </div>`
                  : '<p class="legal-section__description">Выберите пользователя из таблицы ниже, чтобы увидеть его effective доступ.</p>'
              }
            </div>
          </div>
          ${
            items.length
              ? `<div class="legal-subcard">
                <span class="legal-field__label">Effective access</span>
                <table class="legal-table admin-table admin-table--compact"><thead><tr><th>User</th><th>Roles</th><th>Permissions</th><th>Flags</th></tr></thead><tbody>${items.map((item) => {
                  const username = String(item.username || "").trim();
                  const assignments = Array.isArray(item.assignments) ? item.assignments : [];
                  return `<tr>
                    <td>
                      <button type="button" class="ghost-button" data-server-access-select-user="${escapeHtml(username)}">${escapeHtml(String(item.display_name || username || "—"))}</button>
                    </td>
                    <td>${assignments.length ? assignments.map((entry) => `
                      <div class="admin-section-toolbar">
                        <span class="admin-badge admin-badge--muted">${escapeHtml(String(entry.role_code || ""))}${entry.scope === "global" ? " • global" : ""}</span>
                        <button type="button" class="ghost-button" data-server-role-revoke="${escapeHtml(String(entry.assignment_id || ""))}" data-server-username="${escapeHtml(username)}">Снять</button>
                      </div>
                    `).join("") : "—"}</td>
                    <td>${escapeHtml(String((item.permissions || []).join(", ") || "—"))}</td>
                    <td>${item.is_tester ? "tester " : ""}${item.is_gka ? "gka " : ""}${item.is_blocked ? "blocked" : item.is_deactivated ? "deactivated" : ""}</td>
                  </tr>`;
                }).join("")}</tbody></table>
                </div>`
            : ""
        }
        <div class="legal-subcard">
          <span class="legal-field__label">Каталог ролей</span>
          ${
            roles.length
              ? `<table class="legal-table admin-table admin-table--compact"><thead><tr><th>Роль</th><th>Права</th><th>Состояние</th></tr></thead><tbody>${roles.map((role) => {
                  const permissionCodes = Array.isArray(role.permission_codes) ? role.permission_codes : [];
                  const highlighted = highlightedRoleCodes.has(normalizeKey(role.code));
                  return `<tr>
                    <td><strong>${escapeHtml(String(role.name || role.code || "—"))}</strong><div class="admin-user-cell__secondary">${escapeHtml(String(role.code || ""))}</div></td>
                    <td>${permissionCodes.length ? permissionCodes.map((code) => `<span class="admin-badge admin-badge--muted" title="${escapeHtml(permissionLabel(code, permissions))}">${escapeHtml(String(code))}</span>`).join(" ") : "—"}</td>
                    <td>${highlighted ? '<span class="admin-badge admin-badge--success">Назначена</span>' : '<span class="admin-badge admin-badge--muted">Не назначена</span>'}</td>
                  </tr>`;
                }).join("")}</tbody></table>`
              : '<p class="legal-section__description">Каталог ролей пока недоступен.</p>'
          }
        </div>
      `;
    }

    function renderAudit() {
      const hostNode = document.getElementById("admin-server-workspace-panel-audit");
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      const items = Array.isArray(state.auditData?.items) ? state.auditData.items : [];
      const summary = state.auditData?.summary || {};
      const groupedCounts = items.reduce((acc, item) => {
        const kind = String(item?.kind || "event");
        acc[kind] = (acc[kind] || 0) + 1;
        return acc;
      }, {});
      const kindOptions = uniqueValues(items, (item) => item?.kind);
      const filteredItems = items.filter((item) => {
        const kind = String(item?.kind || "").trim().toLowerCase();
        const haystack = `${item?.title || ""} ${item?.description || ""}`.toLowerCase();
        if (state.auditKindFilter !== "all" && kind !== state.auditKindFilter) {
          return false;
        }
        if (state.auditSearch && !haystack.includes(state.auditSearch)) {
          return false;
        }
        return true;
      });
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Аудит</span>
            <p class="legal-section__description">Единая история изменений и событий по серверу. Здесь удобно смотреть, что меняли, когда запускали workflow и какие сигналы появились.</p>
          </div>
          <div class="admin-section-toolbar">
            <button type="button" id="admin-server-audit-reload" class="ghost-button">Обновить блок</button>
          </div>
        </div>
        ${renderOperationalSummaryCard({ title: "Audit summary", summary, actionTab: "errors", actionLabel: "Открыть проблемы" })}
        <div class="legal-subcard">
          <span class="legal-field__label">Сводка событий</span>
          ${
            items.length
              ? `<div class="admin-section-toolbar">${Object.keys(groupedCounts).sort().map((kind) => `<span class="admin-badge admin-badge--muted">${escapeHtml(kind)}: ${escapeHtml(String(groupedCounts[kind] || 0))}</span>`).join("")}</div>`
              : '<p class="legal-section__description">Для сервера пока нет audit events.</p>'
          }
        </div>
        <div class="legal-field-grid legal-field-grid--two">
          <label class="legal-field">
            <span class="legal-field__label">Тип события</span>
            <select id="admin-server-audit-kind-filter" class="text-input">
              <option value="all">Все события</option>
              ${kindOptions.map((kind) => `<option value="${escapeHtml(kind)}" ${state.auditKindFilter === kind ? "selected" : ""}>${escapeHtml(kind)}</option>`).join("")}
            </select>
          </label>
          <label class="legal-field">
            <span class="legal-field__label">Поиск</span>
            <input id="admin-server-audit-search" class="text-input" type="search" value="${escapeHtml(state.auditSearch)}" placeholder="Например: publish, projection, content_item">
          </label>
        </div>
        ${
          items.length
            ? filteredItems.length
              ? `<table class="legal-table admin-table admin-table--compact"><thead><tr><th>Когда</th><th>Тип</th><th>Событие</th><th>Что это значит</th></tr></thead><tbody>${filteredItems.map((item) => `<tr><td>${escapeHtml(String(item.created_at || "—"))}</td><td>${escapeHtml(String(item.kind || "event"))}</td><td><strong>${escapeHtml(String(item.title || "event"))}</strong><div class="admin-user-cell__secondary">${escapeHtml(String(item.description || "—"))}</div></td><td>${escapeHtml(String(item.kind === "law_projection" ? "Обновлялся server-effective набор законов." : item.kind === "workflow_audit" || item.kind === "content_audit" ? "Было изменение контента или workflow-состояния." : "Операционный сигнал или системное событие."))}</td></tr>`).join("")}</tbody></table>`
              : '<p class="legal-section__description">По текущим фильтрам событий не найдено.</p>'
            : '<p class="legal-section__description">История по серверу пока пуста.</p>'
        }
      `;
    }

    function renderErrors() {
      const hostNode = document.getElementById("admin-server-workspace-panel-errors");
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      const issues = state.issuesData || state.workspace?.issues || {};
      const items = Array.isArray(issues.items) ? issues.items : [];
      const summary = issues.summary || {};
      const actionableCount = items.filter((item) => Array.isArray(item.available_actions) && item.available_actions.length).length;
      const sourceOptions = uniqueValues(items, (item) => item?.source);
      const filteredItems = items.filter((item) => {
        const severity = String(item?.severity || "").trim().toLowerCase();
        const source = String(item?.source || "").trim().toLowerCase();
        if (state.issueSeverityFilter !== "all" && severity !== state.issueSeverityFilter) {
          return false;
        }
        if (state.issueSourceFilter !== "all" && source !== state.issueSourceFilter) {
          return false;
        }
        return true;
      });
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Ошибки / Проблемы</span>
            <p class="legal-section__description">Незакрытые проблемы по серверу с понятным следующим шагом и безопасными retry/recheck действиями там, где они уже поддерживаются.</p>
          </div>
          <div class="admin-section-toolbar">
            <button type="button" id="admin-server-issues-reload" class="ghost-button">Обновить блок</button>
          </div>
        </div>
        ${renderOperationalSummaryCard({ title: "Issues summary", summary, actionTab: "audit", actionLabel: "Открыть аудит" })}
        <div class="admin-section-toolbar">
          <span class="admin-badge ${issues.error_count ? "admin-badge--danger" : "admin-badge--muted"}">errors: ${escapeHtml(String(issues.error_count || 0))}</span>
          <span class="admin-badge ${issues.warning_count ? "admin-badge--warning" : "admin-badge--muted"}">warnings: ${escapeHtml(String(issues.warning_count || 0))}</span>
          <span class="admin-badge admin-badge--muted">unresolved: ${escapeHtml(String(issues.unresolved_count || 0))}</span>
          <span class="admin-badge admin-badge--muted">actions: ${escapeHtml(String(actionableCount || 0))}</span>
        </div>
        <div class="legal-field-grid legal-field-grid--two">
          <label class="legal-field">
            <span class="legal-field__label">Severity</span>
            <select id="admin-server-issues-severity-filter" class="text-input">
              <option value="all">Все</option>
              <option value="error" ${state.issueSeverityFilter === "error" ? "selected" : ""}>Только error</option>
              <option value="warn" ${state.issueSeverityFilter === "warn" ? "selected" : ""}>Только warn</option>
            </select>
          </label>
          <label class="legal-field">
            <span class="legal-field__label">Источник</span>
            <select id="admin-server-issues-source-filter" class="text-input">
              <option value="all">Все источники</option>
              ${sourceOptions.map((source) => `<option value="${escapeHtml(source)}" ${state.issueSourceFilter === source ? "selected" : ""}>${escapeHtml(source)}</option>`).join("")}
            </select>
          </label>
        </div>
        ${
          items.length
            ? filteredItems.length
              ? `<table class="legal-table admin-table admin-table--compact"><thead><tr><th>Severity</th><th>Source</th><th>Проблема</th><th>Что делать</th><th>Действия</th></tr></thead><tbody>${filteredItems.map((item) => `<tr><td><span class="admin-badge ${issueSeverityClass(item.severity)}">${escapeHtml(String(item.severity || "info"))}</span></td><td>${escapeHtml(String(item.source || "—"))}</td><td><strong>${escapeHtml(String(item.title || "—"))}</strong><div class="admin-user-cell__secondary">${escapeHtml(String(item.detail || "—"))}</div></td><td>${escapeHtml(summarizeIssueNextStep(item))}</td><td>${Array.isArray(item.available_actions) && item.available_actions.length ? item.available_actions.map((action) => `<button type="button" class="ghost-button" data-server-issue-action="${escapeHtml(String(action.kind || ""))}" data-server-issue-id="${escapeHtml(String(item.issue_id || ""))}">${escapeHtml(String(action.label || action.kind || ""))}</button>`).join(" ") : "—"}</td></tr>`).join("")}</tbody></table>`
              : '<p class="legal-section__description">По текущим фильтрам проблем не найдено.</p>'
            : '<p class="legal-section__description">Критичных сигналов по серверу сейчас не найдено.</p>'
        }
      `;
    }

    function renderDiagnostics() {
      const hostNode = document.getElementById("admin-server-workspace-panel-diagnostics");
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Диагностика</span>
            <p class="legal-section__description">Technical payloads and compatibility entrypoints stay secondary to the main operator flow.</p>
          </div>
          <div class="admin-section-toolbar">
            <a class="ghost-button button-link" href="/admin/laws">Advanced laws diagnostics</a>
            <a class="ghost-button button-link" href="/admin/ops">Global ops</a>
            <a class="ghost-button button-link" href="/admin/audit">Global users / audit</a>
          </div>
        </div>
        <pre class="legal-field__hint">${escapeHtml(JSON.stringify(state.workspace?.health || {}, null, 2))}</pre>
      `;
    }

    function renderPanels() {
      renderSummary();
      renderOverview();
      renderFeatures();
      renderTemplates();
      renderLaws();
      renderUsers();
      renderAccess();
      renderAudit();
      renderErrors();
      renderDiagnostics();
    }

    async function loadFeaturesData() {
      const response = await deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/features`);
      const payload = await deps.parsePayload(response);
      if (!response.ok) {
        throw new Error(deps.formatHttpError?.(response, payload, "Не удалось загрузить effective features.") || "Не удалось загрузить effective features.");
      }
      state.featuresData = payload;
    }

    async function loadAccessData() {
      const [accessResponse, rolesResponse, permissionsResponse] = await Promise.all([
        deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/access-summary`),
        deps.apiFetch("/api/admin/roles"),
        deps.apiFetch("/api/admin/permissions"),
      ]);
      const accessPayload = await deps.parsePayload(accessResponse);
      const rolesPayload = await deps.parsePayload(rolesResponse);
      const permissionsPayload = await deps.parsePayload(permissionsResponse);
      if (!accessResponse.ok) {
        throw new Error(deps.formatHttpError?.(accessResponse, accessPayload, "Не удалось загрузить server access summary.") || "Не удалось загрузить server access summary.");
      }
      if (!rolesResponse.ok) {
        throw new Error(deps.formatHttpError?.(rolesResponse, rolesPayload, "Не удалось загрузить список ролей.") || "Не удалось загрузить список ролей.");
      }
      if (!permissionsResponse.ok) {
        throw new Error(deps.formatHttpError?.(permissionsResponse, permissionsPayload, "Не удалось загрузить список permissions.") || "Не удалось загрузить список permissions.");
      }
      state.accessSummary = accessPayload;
      state.rolesData = rolesPayload;
      state.permissionsData = permissionsPayload;
      if (!normalizeKey(state.selectedAccessUsername)) {
        const firstUser = Array.isArray(accessPayload?.items) ? accessPayload.items[0] : null;
        state.selectedAccessUsername = normalizeKey(firstUser?.username || "");
      }
    }

    async function reloadAccessOnly(successMessage = "") {
      try {
        await loadAccessData();
        renderUsers();
        renderAccess();
        if (successMessage) {
          deps.showMessage?.(successMessage);
        }
      } catch (error) {
        deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось обновить блок доступа.");
      }
    }

    async function loadObservabilityData() {
      const [auditResponse, issuesResponse] = await Promise.all([
        deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/audit`),
        deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/issues`),
      ]);
      const auditPayload = await deps.parsePayload(auditResponse);
      const issuesPayload = await deps.parsePayload(issuesResponse);
      if (!auditResponse.ok) {
        throw new Error(deps.formatHttpError?.(auditResponse, auditPayload, "Не удалось загрузить аудит сервера.") || "Не удалось загрузить аудит сервера.");
      }
      if (!issuesResponse.ok) {
        throw new Error(deps.formatHttpError?.(issuesResponse, issuesPayload, "Не удалось загрузить список проблем сервера.") || "Не удалось загрузить список проблем сервера.");
      }
      state.auditData = auditPayload;
      state.issuesData = issuesPayload;
    }

    async function loadLawSourceSetsData() {
      if (state.lawSourceSetsData) {
        return state.lawSourceSetsData;
      }
      const response = await deps.apiFetch("/api/admin/law-source-sets");
      const payload = await deps.parsePayload(response);
      if (!response.ok) {
        throw new Error(deps.formatHttpError?.(response, payload, "Не удалось загрузить список source sets.") || "Не удалось загрузить список source sets.");
      }
      state.lawSourceSetsData = payload;
      return payload;
    }

    async function loadLawProjectionStatusData(runId) {
      const normalizedRunId = Number(runId || 0);
      if (normalizedRunId <= 0) {
        state.lawProjectionStatus = null;
        return null;
      }
      const response = await deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/law-projection-runs/${encodeURIComponent(String(normalizedRunId))}/status`);
      const payload = await deps.parsePayload(response);
      if (!response.ok) {
        throw new Error(deps.formatHttpError?.(response, payload, "Не удалось загрузить projection status.") || "Не удалось загрузить projection status.");
      }
      state.lawProjectionStatus = payload;
      return payload;
    }

    async function runUserAction(endpoint, successMessage, body = null) {
      deps.clearMessage?.();
      deps.setStateIdle?.(deps.errorsHost);
      const response = await deps.apiFetch(endpoint, {
        method: "POST",
        body: body ? JSON.stringify(body) : null,
      });
      const payload = await deps.parsePayload(response);
      if (!response.ok) {
        throw new Error(deps.formatHttpError?.(response, payload, "Не удалось выполнить действие с пользователем.") || "Не удалось выполнить действие с пользователем.");
      }
      await reloadAccessOnly(successMessage);
    }

    async function loadTemplateAux(contentKey) {
      const normalizedKey = normalizeKey(contentKey);
      if (!normalizedKey) {
        return;
      }
      const [itemResponse, placeholdersResponse] = await Promise.all([
        deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/templates/${encodeURIComponent(normalizedKey)}`),
        deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/templates/${encodeURIComponent(normalizedKey)}/placeholders`),
      ]);
      const itemPayload = await deps.parsePayload(itemResponse);
      const placeholdersPayload = await deps.parsePayload(placeholdersResponse);
      if (itemResponse.ok) {
        const items = getTemplateItems().filter((item) => normalizeKey(item?.content_key) !== normalizedKey);
        items.push(itemPayload);
        items.sort((left, right) => String(left?.title || left?.content_key || "").localeCompare(String(right?.title || right?.content_key || "")));
        state.templatesData = {
          ...(state.templatesData || {}),
          effective_items: items,
          counts: {
            ...(state.templatesData?.counts || {}),
            effective: items.length,
          },
        };
      }
      if (placeholdersResponse.ok) {
        state.templatePlaceholdersByKey[normalizedKey] = placeholdersPayload;
      }
    }

    async function loadTemplatesData() {
      const response = await deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/templates`);
      const payload = await deps.parsePayload(response);
      if (!response.ok) {
        throw new Error(deps.formatHttpError?.(response, payload, "Не удалось загрузить effective templates.") || "Не удалось загрузить effective templates.");
      }
      state.templatesData = payload;
      const focusedKey = normalizeKey(state.templateEditorKey && state.templateEditorKey !== "__new__" ? state.templateEditorKey : getTemplateItems()[0]?.content_key);
      if (focusedKey) {
        await loadTemplateAux(focusedKey);
      }
    }

    function applyTabState() {
      host.querySelectorAll("[data-server-workspace-tab]").forEach((button) => {
        const tabName = String(button.getAttribute("data-server-workspace-tab") || "");
        button.classList.toggle("is-active", tabName === state.activeTab);
      });
      host.querySelectorAll("[id^='admin-server-workspace-panel-']").forEach((panel) => {
        panel.hidden = panel.id !== `admin-server-workspace-panel-${state.activeTab}`;
      });
    }

    async function loadWorkspace() {
      setBusy(true);
      deps.clearMessage?.();
      deps.setStateIdle?.(deps.errorsHost);
      try {
        const [workspaceResponse, activityResponse, lawsSummaryResponse, lawsEffectiveResponse, lawsDiffResponse] = await Promise.all([
          deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/workspace`),
          deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/activity`),
          deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/laws/summary`),
          deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/laws/effective`),
          deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/laws/diff`),
        ]);
        const workspacePayload = await deps.parsePayload(workspaceResponse);
        const activityPayload = await deps.parsePayload(activityResponse);
        const lawsSummaryPayload = await deps.parsePayload(lawsSummaryResponse);
        const lawsEffectivePayload = await deps.parsePayload(lawsEffectiveResponse);
        const lawsDiffPayload = await deps.parsePayload(lawsDiffResponse);
        if (!workspaceResponse.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(workspaceResponse, workspacePayload, "Не удалось загрузить server workspace."));
          return;
        }
        if (!activityResponse.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(activityResponse, activityPayload, "Не удалось загрузить activity feed."));
          return;
        }
        if (!lawsSummaryResponse.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(lawsSummaryResponse, lawsSummaryPayload, "Не удалось загрузить laws summary."));
          return;
        }
        if (!lawsEffectiveResponse.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(lawsEffectiveResponse, lawsEffectivePayload, "Не удалось загрузить effective laws."));
          return;
        }
        if (!lawsDiffResponse.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(lawsDiffResponse, lawsDiffPayload, "Не удалось загрузить laws diff."));
          return;
        }
        state.workspace = workspacePayload;
        state.activity = activityPayload;
        state.lawsSummary = lawsSummaryPayload;
        state.lawsEffective = lawsEffectivePayload;
        state.lawsDiff = lawsDiffPayload;
        await loadLawProjectionStatusData((lawsSummaryPayload.latest_projection_run || {}).id);
        await Promise.all([loadFeaturesData(), loadTemplatesData(), loadAccessData(), loadObservabilityData()]);
        renderPanels();
        applyTabState();
      } catch (error) {
        deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось загрузить server workspace.");
      } finally {
        setBusy(false);
      }
    }

      host.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const tabButton = target.closest("[data-server-workspace-tab]");
      if (tabButton instanceof HTMLElement) {
        state.activeTab = String(tabButton.getAttribute("data-server-workspace-tab") || "overview");
        applyTabState();
        return;
      }
      const quickSwitch = target.closest("[data-server-workspace-switch]");
      if (quickSwitch instanceof HTMLElement) {
        state.activeTab = String(quickSwitch.getAttribute("data-server-workspace-switch") || "overview");
        applyTabState();
        return;
      }
      if (target.id === "admin-server-workspace-refresh") {
        loadWorkspace();
        return;
      }
      if (target.id === "admin-server-laws-open-diagnostics") {
        state.activeTab = "diagnostics";
        applyTabState();
        return;
      }
      if (target.id === "admin-server-laws-add-binding") {
        (async () => {
          deps.clearMessage?.();
          deps.setStateIdle?.(deps.errorsHost);
          try {
            await loadLawSourceSetsData();
            state.lawBindingEditor = { mode: "create", bindingId: null };
            renderLaws();
          } catch (error) {
            deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось открыть форму binding.");
          }
        })();
        return;
      }
      if (target.id === "admin-server-laws-add-manual") {
        const boundSourceSet = String(getLawBindingItems().find((item) => item?.is_active)?.source_set_key || "");
        state.lawManualEditor = {
          mode: "create",
          sourceSetKey: boundSourceSet,
          canonicalIdentityKey: "",
          normalizedUrl: "",
          title: "",
          bodyText: "",
        };
        renderLaws();
        return;
      }
      if (target.id === "admin-server-law-manual-editor-cancel") {
        state.lawManualEditor = null;
        renderLaws();
        return;
      }
      const lawManualEditButton = target.closest("[data-server-law-manual-edit]");
      if (lawManualEditButton instanceof HTMLElement) {
        (async () => {
          deps.clearMessage?.();
          deps.setStateIdle?.(deps.errorsHost);
          try {
            const canonicalIdentityKey = String(lawManualEditButton.getAttribute("data-server-law-manual-edit") || "").trim();
            const sourceSetKey = String(lawManualEditButton.getAttribute("data-server-law-manual-source-set") || "").trim();
            const response = await deps.apiFetch(
              `/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/laws/manual-editor?source_set_key=${encodeURIComponent(sourceSetKey)}&canonical_identity_key=${encodeURIComponent(canonicalIdentityKey)}`,
            );
            const payload = await deps.parsePayload(response);
            if (!response.ok) {
              deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Не удалось загрузить manual law editor."));
              return;
            }
            state.lawManualEditor = {
              mode: "edit",
              sourceSetKey: String(payload.source_set_key || ""),
              canonicalIdentityKey: String(payload.canonical_identity_key || ""),
              normalizedUrl: String(payload.normalized_url || ""),
              title: String(payload.title || ""),
              bodyText: String(payload.body_text || ""),
            };
            renderLaws();
          } catch (error) {
            deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось загрузить manual law editor.");
          }
        })();
        return;
      }
      if (target.id === "admin-server-law-binding-editor-cancel") {
        state.lawBindingEditor = null;
        renderLaws();
        return;
      }
      const lawBindingEditButton = target.closest("[data-server-law-binding-edit]");
      if (lawBindingEditButton instanceof HTMLElement) {
        (async () => {
          deps.clearMessage?.();
          deps.setStateIdle?.(deps.errorsHost);
          try {
            await loadLawSourceSetsData();
            state.lawBindingEditor = {
              mode: "edit",
              bindingId: Number(lawBindingEditButton.getAttribute("data-server-law-binding-edit") || 0),
            };
            renderLaws();
          } catch (error) {
            deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось открыть редактирование binding.");
          }
        })();
        return;
      }
      if (target.id === "admin-server-laws-reload") {
        loadWorkspace();
        return;
      }
      if (target.id === "admin-server-laws-refresh-preview" || target.id === "admin-server-laws-refresh-preview-empty") {
        (async () => {
          deps.clearMessage?.();
          deps.setStateIdle?.(deps.errorsHost);
          try {
            const response = await deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/laws/refresh-preview`, { method: "POST" });
            const payload = await deps.parsePayload(response);
            if (!response.ok) {
              deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Не удалось обновить laws preview."));
              return;
            }
            deps.showMessage?.(payload?.reused_run ? "Preview уже актуален." : "Preview законов обновлен.");
            await loadWorkspace();
            state.activeTab = "laws";
            applyTabState();
          } catch (error) {
            deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось обновить laws preview.");
          }
        })();
        return;
      }
      if (target.id === "admin-server-laws-recheck") {
        (async () => {
          deps.clearMessage?.();
          deps.setStateIdle?.(deps.errorsHost);
          try {
            const response = await deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/laws/recheck`, { method: "POST" });
            const payload = await deps.parsePayload(response);
            if (!response.ok) {
              deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Не удалось проверить наполнение законов."));
              return;
            }
            state.lawsEffective = {
              ...(state.lawsEffective || {}),
              run: payload.run,
              summary: payload.summary,
              items: Array.isArray(payload.items) ? payload.items : [],
              count: Array.isArray(payload.items) ? payload.items.length : Number(payload.summary?.count || 0),
            };
            if (state.lawsSummary) {
              state.lawsSummary = {
                ...state.lawsSummary,
                fill_check: payload.summary,
              };
            }
            renderLaws();
            deps.showMessage?.("Проверка наполнения выполнена.");
          } catch (error) {
            deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось проверить наполнение законов.");
          }
        })();
        return;
      }
      if (
        target.id === "admin-server-laws-approve-run"
        || target.id === "admin-server-laws-hold-run"
        || target.id === "admin-server-laws-materialize-run"
        || target.id === "admin-server-laws-activate-run"
      ) {
        (async () => {
          deps.clearMessage?.();
          deps.setStateIdle?.(deps.errorsHost);
          const runId = Number((state.lawsSummary?.latest_projection_run || {}).id || 0);
          if (runId <= 0) {
            deps.setStateError?.(deps.errorsHost, "Нет preview run для выполнения action.");
            return;
          }
          let endpoint = "";
          let method = "POST";
          let body = "{}";
          let successMessage = "";
          if (target.id === "admin-server-laws-approve-run") {
            endpoint = `/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/law-projection-runs/${encodeURIComponent(String(runId))}/approve`;
            body = JSON.stringify({ reason: "server_workspace_apply_flow" });
            successMessage = "Projection run approved.";
          } else if (target.id === "admin-server-laws-hold-run") {
            endpoint = `/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/law-projection-runs/${encodeURIComponent(String(runId))}/hold`;
            body = JSON.stringify({ reason: "server_workspace_manual_hold" });
            successMessage = "Projection run held.";
          } else if (target.id === "admin-server-laws-materialize-run") {
            endpoint = `/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/law-projection-runs/${encodeURIComponent(String(runId))}/materialize-law-set`;
            body = JSON.stringify({ safe_rerun: true });
            successMessage = "Projection law set materialized.";
          } else if (target.id === "admin-server-laws-activate-run") {
            endpoint = `/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/law-projection-runs/${encodeURIComponent(String(runId))}/activate-runtime`;
            body = JSON.stringify({ safe_rerun: true });
            successMessage = "Projection activated into runtime.";
          }
          try {
            const response = await deps.apiFetch(endpoint, { method, body });
            const payload = await deps.parsePayload(response);
            if (!response.ok) {
              deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Не удалось выполнить projection action."));
              return;
            }
            await loadWorkspace();
            state.activeTab = "laws";
            applyTabState();
            deps.showMessage?.(successMessage);
          } catch (error) {
            deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось выполнить projection action.");
          }
        })();
        return;
      }
      if (target.id === "admin-server-users-reload" || target.id === "admin-server-access-reload") {
        void reloadAccessOnly(target.id === "admin-server-users-reload" ? "Блок пользователей обновлен." : "Блок доступа обновлен.");
        return;
      }
      if (target.id === "admin-server-audit-reload" || target.id === "admin-server-issues-reload") {
        (async () => {
          try {
            await loadObservabilityData();
            renderAudit();
            renderErrors();
            deps.showMessage?.(target.id === "admin-server-audit-reload" ? "Блок аудита обновлен." : "Блок проблем обновлен.");
          } catch (error) {
            deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось обновить observability блок.");
          }
        })();
        return;
      }
      const accessSelectUserButton = target.closest("[data-server-access-select-user]");
      if (accessSelectUserButton instanceof HTMLElement) {
        state.selectedAccessUsername = String(accessSelectUserButton.getAttribute("data-server-access-select-user") || "");
        state.activeTab = "access";
        renderUsers();
        renderAccess();
        applyTabState();
        return;
      }
      const serverUserActionButton = target.closest("[data-server-user-action]");
      if (serverUserActionButton instanceof HTMLElement) {
        (async () => {
          const action = String(serverUserActionButton.getAttribute("data-server-user-action") || "");
          const username = String(serverUserActionButton.getAttribute("data-server-username") || "").trim();
          if (!username) {
            return;
          }
          try {
            if (action === "grant-tester") {
              await runUserAction(`/api/admin/users/${encodeURIComponent(username)}/grant-tester`, "Статус тестера выдан.");
              return;
            }
            if (action === "revoke-tester") {
              await runUserAction(`/api/admin/users/${encodeURIComponent(username)}/revoke-tester`, "Статус тестера снят.");
              return;
            }
            if (action === "grant-gka") {
              await runUserAction(`/api/admin/users/${encodeURIComponent(username)}/grant-gka`, "Статус ГКА выдан.");
              return;
            }
            if (action === "revoke-gka") {
              await runUserAction(`/api/admin/users/${encodeURIComponent(username)}/revoke-gka`, "Статус ГКА снят.");
              return;
            }
            if (action === "unblock") {
              await runUserAction(`/api/admin/users/${encodeURIComponent(username)}/unblock`, "Доступ пользователя восстановлен.");
              return;
            }
            if (action === "reactivate") {
              await runUserAction(`/api/admin/users/${encodeURIComponent(username)}/reactivate`, "Аккаунт реактивирован.");
              return;
            }
            if (action === "block") {
              const reason = window.prompt(`Причина блокировки для ${username}:`, "") || "";
              await runUserAction(`/api/admin/users/${encodeURIComponent(username)}/block`, "Пользователь заблокирован.", { reason });
              return;
            }
            if (action === "deactivate") {
              const reason = window.prompt(`Причина деактивации для ${username}:`, "") || "";
              await runUserAction(`/api/admin/users/${encodeURIComponent(username)}/deactivate`, "Аккаунт деактивирован.", { reason });
            }
          } catch (error) {
            deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось выполнить действие с пользователем.");
          }
        })();
        return;
      }
      const revokeRoleButton = target.closest("[data-server-role-revoke]");
      if (revokeRoleButton instanceof HTMLElement) {
        (async () => {
          const username = String(revokeRoleButton.getAttribute("data-server-username") || "").trim();
          const assignmentId = String(revokeRoleButton.getAttribute("data-server-role-revoke") || "").trim();
          if (!username || !assignmentId) {
            return;
          }
          if (!window.confirm(`Снять роль ${assignmentId} у пользователя ${username}?`)) {
            return;
          }
          try {
            const response = await deps.apiFetch(`/api/admin/users/${encodeURIComponent(username)}/role-assignments/${encodeURIComponent(assignmentId)}/revoke`, {
              method: "POST",
            });
            const payload = await deps.parsePayload(response);
            if (!response.ok) {
              deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Не удалось снять назначение роли."));
              return;
            }
            state.selectedAccessUsername = username;
            await reloadAccessOnly("Назначение роли снято.");
          } catch (error) {
            deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось снять назначение роли.");
          }
        })();
        return;
      }
      const issueActionButton = target.closest("[data-server-issue-action]");
      if (issueActionButton instanceof HTMLElement) {
        (async () => {
          const action = String(issueActionButton.getAttribute("data-server-issue-action") || "").trim().toLowerCase();
          const issueId = String(issueActionButton.getAttribute("data-server-issue-id") || "").trim().toLowerCase();
          if (!action || !issueId) {
            return;
          }
          try {
            const response = await deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/issues/${encodeURIComponent(issueId)}/${encodeURIComponent(action)}`, {
              method: "POST",
            });
            const payload = await deps.parsePayload(response);
            if (!response.ok) {
              deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Не удалось выполнить action для проблемы."));
              return;
            }
            await loadWorkspace();
            state.activeTab = "errors";
            applyTabState();
            deps.showMessage?.(action === "recheck" ? "Пере-проверка выполнена." : "Retry выполнен.");
          } catch (error) {
            deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось выполнить action для проблемы.");
          }
        })();
        return;
      }
      if (target.id === "admin-server-features-reload") {
          (async () => {
            try {
              await loadFeaturesData();
              renderFeatures();
              deps.showMessage?.("Блок функций обновлен.");
            } catch (error) {
              deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось обновить блок функций.");
            }
          })();
          return;
        }
        if (target.id === "admin-server-features-add") {
          state.featureEditorKey = "__new__";
          renderFeatures();
          return;
        }
        if (target.id === "admin-server-feature-editor-cancel") {
          state.featureEditorKey = "";
          renderFeatures();
          return;
        }
        const featureEditButton = target.closest("[data-server-feature-edit]");
        if (featureEditButton instanceof HTMLElement) {
          state.featureEditorKey = String(featureEditButton.getAttribute("data-server-feature-edit") || "");
          renderFeatures();
          return;
        }
        const featureWorkflowButton = target.closest("[data-server-feature-workflow]");
        if (featureWorkflowButton instanceof HTMLElement) {
          (async () => {
            const contentKey = String(featureWorkflowButton.getAttribute("data-server-feature-workflow") || "");
            const action = String(featureWorkflowButton.getAttribute("data-server-feature-workflow-action") || "");
            const changeRequestId = Number(featureWorkflowButton.getAttribute("data-server-feature-cr-id") || 0);
            try {
              const response = await deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/features/${encodeURIComponent(contentKey)}/workflow`, {
                method: "POST",
                body: JSON.stringify({ action, change_request_id: changeRequestId }),
              });
              const payload = await deps.parsePayload(response);
              if (!response.ok) {
                deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Не удалось обновить feature workflow."));
                return;
              }
              await loadFeaturesData();
              renderFeatures();
              deps.showMessage?.(`Feature workflow: ${buildWorkflowActionLabel(action)}.`);
            } catch (error) {
              deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось обновить feature workflow.");
            }
          })();
          return;
        }
        if (target.id === "admin-server-templates-reload") {
          (async () => {
            try {
              await loadTemplatesData();
              renderTemplates();
              deps.showMessage?.("Блок шаблонов обновлен.");
            } catch (error) {
              deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось обновить блок шаблонов.");
            }
          })();
          return;
        }
        if (target.id === "admin-server-templates-add") {
          state.templateEditorKey = "__new__";
          renderTemplates();
          return;
        }
        if (target.id === "admin-server-template-editor-cancel") {
          state.templateEditorKey = "";
          renderTemplates();
          return;
        }
        const templateEditButton = target.closest("[data-server-template-edit]");
        if (templateEditButton instanceof HTMLElement) {
          (async () => {
            state.templateEditorKey = String(templateEditButton.getAttribute("data-server-template-edit") || "");
            try {
              await loadTemplateAux(state.templateEditorKey);
            } catch {
              // keep editor open even if details fetch partially fails
            }
            renderTemplates();
          })();
          return;
        }
        const templateWorkflowButton = target.closest("[data-server-template-workflow]");
        if (templateWorkflowButton instanceof HTMLElement) {
          (async () => {
            const contentKey = String(templateWorkflowButton.getAttribute("data-server-template-workflow") || "");
            const action = String(templateWorkflowButton.getAttribute("data-server-template-workflow-action") || "");
            const changeRequestId = Number(templateWorkflowButton.getAttribute("data-server-template-cr-id") || 0);
            try {
              const response = await deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/templates/${encodeURIComponent(contentKey)}/workflow`, {
                method: "POST",
                body: JSON.stringify({ action, change_request_id: changeRequestId }),
              });
              const payload = await deps.parsePayload(response);
              if (!response.ok) {
                deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Не удалось обновить template workflow."));
                return;
              }
              await loadTemplatesData();
              await loadTemplateAux(contentKey);
              renderTemplates();
              deps.showMessage?.(`Template workflow: ${buildWorkflowActionLabel(action)}.`);
            } catch (error) {
              deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось обновить template workflow.");
            }
          })();
          return;
        }
        const templateResetButton = target.closest("[data-server-template-reset]");
        if (templateResetButton instanceof HTMLElement || target.id === "admin-server-template-reset") {
          (async () => {
            const contentKey = normalizeKey(
              target.id === "admin-server-template-reset"
                ? state.templateEditorKey
                : templateResetButton.getAttribute("data-server-template-reset"),
            );
            if (!contentKey) {
              return;
            }
            try {
              const response = await deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/templates/${encodeURIComponent(contentKey)}/reset-to-default`, {
                method: "POST",
              });
              const payload = await deps.parsePayload(response);
              if (!response.ok) {
                deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Не удалось сбросить шаблон к global default."));
                return;
              }
              await loadTemplatesData();
              await loadTemplateAux(contentKey);
              renderTemplates();
              deps.showMessage?.("Шаблон сброшен к global default через draft override.");
            } catch (error) {
              deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось сбросить шаблон к global default.");
            }
          })();
          return;
        }
        if (target.id === "admin-server-template-preview") {
          (async () => {
            const form = document.getElementById("admin-server-template-form");
            if (!(form instanceof HTMLFormElement)) {
              return;
            }
            const contentKey = normalizeKey(form.elements.namedItem("content_key")?.value);
            try {
              const sampleRaw = String(form.elements.namedItem("sample_json")?.value || "").trim();
              const sampleJson = sampleRaw ? JSON.parse(sampleRaw) : {};
              const response = await deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/templates/${encodeURIComponent(contentKey)}/preview`, {
                method: "POST",
                body: JSON.stringify({ sample_json: sampleJson }),
              });
              const payload = await deps.parsePayload(response);
              if (!response.ok) {
                deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Не удалось построить preview шаблона."));
                return;
              }
              state.templatePreviewByKey[contentKey] = payload;
              renderTemplates();
              deps.showMessage?.("Preview шаблона обновлен.");
            } catch (error) {
              deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось построить preview шаблона.");
            }
          })();
          return;
        }
      });

      host.addEventListener("change", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement || target instanceof HTMLTextAreaElement)) {
          return;
        }
        if (target.id === "admin-server-audit-kind-filter") {
          state.auditKindFilter = normalizeKey(target.value) || "all";
          renderAudit();
          return;
        }
        if (target.id === "admin-server-issues-severity-filter") {
          state.issueSeverityFilter = normalizeKey(target.value) || "all";
          renderErrors();
          return;
        }
        if (target.id === "admin-server-issues-source-filter") {
          state.issueSourceFilter = normalizeKey(target.value) || "all";
          renderErrors();
        }
      });

      host.addEventListener("input", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement)) {
          return;
        }
        if (target.id === "admin-server-audit-search") {
          state.auditSearch = String(target.value || "").trim().toLowerCase();
          renderAudit();
        }
      });

      host.addEventListener("submit", (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) {
          return;
        }
        if (form.id === "admin-server-role-assignment-form") {
          event.preventDefault();
          (async () => {
            const username = normalizeKey(form.elements.namedItem("username")?.value);
            const roleCode = normalizeKey(form.elements.namedItem("role_code")?.value);
            const scope = normalizeKey(form.elements.namedItem("scope")?.value) || "server";
            if (!username || !roleCode) {
              deps.setStateError?.(deps.errorsHost, "Выберите пользователя и роль.");
              return;
            }
            try {
              const response = await deps.apiFetch(`/api/admin/users/${encodeURIComponent(username)}/role-assignments`, {
                method: "POST",
                body: JSON.stringify({
                  role_code: roleCode,
                  server_code: scope === "global" ? "" : serverCode,
                }),
              });
              const payload = await deps.parsePayload(response);
              if (!response.ok) {
                deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Не удалось назначить роль."));
                return;
              }
              state.selectedAccessUsername = username;
              await reloadAccessOnly("Роль назначена.");
            } catch (error) {
              deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось назначить роль.");
            }
          })();
          return;
        }
        if (form.id === "admin-server-feature-form") {
          event.preventDefault();
          (async () => {
            const contentKey = normalizeKey(form.elements.namedItem("content_key")?.value);
            const payload = {
              title: String(form.elements.namedItem("title")?.value || "").trim(),
              key: contentKey,
              description: String(form.elements.namedItem("notes")?.value || "").trim(),
              status: String(form.elements.namedItem("status")?.value || "draft").trim().toLowerCase(),
              feature_flag: contentKey,
              config: {
                feature_code: contentKey,
                enabled: Boolean(form.elements.namedItem("enabled")?.checked),
                rollout: String(form.elements.namedItem("rollout")?.value || "").trim(),
                owner: String(form.elements.namedItem("owner")?.value || "").trim(),
                notes: String(form.elements.namedItem("notes")?.value || "").trim(),
                hidden: Boolean(form.elements.namedItem("hidden")?.checked),
                order: (() => {
                  const raw = String(form.elements.namedItem("order")?.value || "").trim();
                  return raw ? Number(raw) : null;
                })(),
              },
            };
            const existing = findEffectiveItem(getFeatureItems(), contentKey);
            const method = existing?.server_item_id ? "PUT" : "POST";
            const url = method === "PUT"
              ? `/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/features/${encodeURIComponent(contentKey)}`
              : `/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/features`;
            try {
              const response = await deps.apiFetch(url, { method, body: JSON.stringify(payload) });
              const responsePayload = await deps.parsePayload(response);
              if (!response.ok) {
                deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, responsePayload, "Не удалось сохранить feature override."));
                return;
              }
              state.featureEditorKey = contentKey;
              await loadFeaturesData();
              renderFeatures();
              deps.showMessage?.("Feature override сохранён как черновик.");
            } catch (error) {
              deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось сохранить feature override.");
            }
          })();
          return;
        }
        if (form.id === "admin-server-law-binding-form") {
          event.preventDefault();
          (async () => {
            const mode = state.lawBindingEditor?.mode || "create";
            const bindingId = Number(state.lawBindingEditor?.bindingId || 0);
            const sourceSetKey = normalizeKey(form.elements.namedItem("source_set_key")?.value);
            const priorityRaw = String(form.elements.namedItem("priority")?.value || "").trim();
            const payload = {
              source_set_key: sourceSetKey,
              priority: priorityRaw ? Number(priorityRaw) : 100,
              is_active: Boolean(form.elements.namedItem("is_active")?.checked),
              include_law_keys: [],
              exclude_law_keys: [],
              pin_policy_json: {},
              metadata_json: {},
            };
            const method = mode === "edit" ? "PUT" : "POST";
            const url = mode === "edit"
              ? `/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/source-set-bindings/${bindingId}`
              : `/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/source-set-bindings`;
            try {
              const response = await deps.apiFetch(url, { method, body: JSON.stringify(payload) });
              const responsePayload = await deps.parsePayload(response);
              if (!response.ok) {
                deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, responsePayload, "Не удалось сохранить source set binding."));
                return;
              }
              state.lawBindingEditor = null;
              await loadWorkspace();
              state.activeTab = "laws";
              applyTabState();
              deps.showMessage?.(mode === "edit" ? "Source set binding обновлён." : "Source set binding добавлен.");
            } catch (error) {
              deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось сохранить source set binding.");
            }
          })();
          return;
        }
        if (form.id === "admin-server-law-manual-form") {
          event.preventDefault();
          (async () => {
            const payload = {
              source_set_key: normalizeKey(form.elements.namedItem("source_set_key")?.value),
              canonical_identity_key: String(form.elements.namedItem("canonical_identity_key")?.value || "").trim(),
              normalized_url: String(form.elements.namedItem("normalized_url")?.value || "").trim(),
              title: String(form.elements.namedItem("title")?.value || "").trim(),
              body_text: String(form.elements.namedItem("body_text")?.value || ""),
            };
            try {
              const response = await deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/laws/manual-entry`, {
                method: "POST",
                body: JSON.stringify(payload),
              });
              const responsePayload = await deps.parsePayload(response);
              if (!response.ok) {
                deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, responsePayload, "Не удалось сохранить закон вручную."));
                return;
              }
              state.lawManualEditor = null;
              await loadWorkspace();
              state.activeTab = "laws";
              applyTabState();
              deps.showMessage?.("Ручная canonical version сохранена.");
            } catch (error) {
              deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось сохранить закон вручную.");
            }
          })();
          return;
        }
        if (form.id === "admin-server-template-form") {
          event.preventDefault();
          (async () => {
            const contentKey = normalizeKey(form.elements.namedItem("content_key")?.value);
            const payload = {
              title: String(form.elements.namedItem("title")?.value || "").trim(),
              key: contentKey,
              description: String(form.elements.namedItem("notes")?.value || "").trim(),
              status: String(form.elements.namedItem("status")?.value || "draft").trim().toLowerCase(),
              output_format: String(form.elements.namedItem("format")?.value || "bbcode").trim().toLowerCase(),
              config: {
                template_code: contentKey,
                title: String(form.elements.namedItem("title")?.value || "").trim(),
                body: String(form.elements.namedItem("body")?.value || ""),
                format: String(form.elements.namedItem("format")?.value || "bbcode").trim().toLowerCase(),
                status: String(form.elements.namedItem("status")?.value || "draft").trim().toLowerCase(),
                notes: String(form.elements.namedItem("notes")?.value || "").trim(),
              },
            };
            const existing = findEffectiveItem(getTemplateItems(), contentKey);
            const method = existing?.server_item_id ? "PUT" : "POST";
            const url = method === "PUT"
              ? `/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/templates/${encodeURIComponent(contentKey)}`
              : `/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/templates`;
            try {
              const response = await deps.apiFetch(url, { method, body: JSON.stringify(payload) });
              const responsePayload = await deps.parsePayload(response);
              if (!response.ok) {
                deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, responsePayload, "Не удалось сохранить template override."));
                return;
              }
              state.templateEditorKey = contentKey;
              await loadTemplatesData();
              await loadTemplateAux(contentKey);
              renderTemplates();
              deps.showMessage?.("Template override сохранён как черновик.");
            } catch (error) {
              deps.setStateError?.(deps.errorsHost, error?.message || "Не удалось сохранить template override.");
            }
          })();
        }
      });

    applyTabState();
    loadWorkspace();
  },
};
