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
    };

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
      if (normalized === "error") return "admin-badge--danger";
      if (normalized === "update_required" || normalized === "partial") return "admin-badge--warning";
      return "admin-badge--muted";
    }

    function renderSummary() {
      const summaryHost = document.getElementById("admin-server-workspace-summary");
      if (!(summaryHost instanceof HTMLElement)) {
        return;
      }
      const readiness = state.workspace?.readiness || {};
      const counters = readiness.counters || {};
      const health = state.workspace?.health?.summary || {};
      summaryHost.innerHTML = `
        <div class="legal-field">
          <span class="legal-field__label">Сервер</span>
          <div><strong>${escapeHtml(state.workspace?.server?.title || serverCode)}</strong></div>
          <div class="admin-user-cell__secondary">${escapeHtml(serverCode)}</div>
        </div>
        <div class="legal-field">
          <span class="legal-field__label">Общая готовность</span>
          <div><span class="admin-badge ${badgeClass(readiness.overall_status)}">${escapeHtml(String(readiness.overall_status || "unknown"))}</span></div>
          <div class="admin-user-cell__secondary">errors: ${escapeHtml(String(counters.errors || 0))} • warnings: ${escapeHtml(String(counters.warnings || 0))}</div>
        </div>
        <div class="legal-field">
          <span class="legal-field__label">Health</span>
          <div><strong>${health.is_ready ? "готов" : "нужна проверка"}</strong></div>
          <div class="admin-user-cell__secondary">${escapeHtml(String(health.ready_count || 0))}/${escapeHtml(String(health.total_count || 0))} checks</div>
        </div>
        <div class="legal-field">
          <span class="legal-field__label">Быстрые действия</span>
          <div class="admin-section-toolbar">
            <a class="ghost-button button-link" href="/admin/laws">Advanced laws</a>
            <a class="ghost-button button-link" href="/admin/features">Advanced features</a>
            <a class="ghost-button button-link" href="/admin/templates">Advanced templates</a>
            <a class="ghost-button button-link" href="/admin/users">Users</a>
          </div>
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
      const dashboard = state.workspace?.overview?.dashboard || {};
      const activityItems = Array.isArray(state.workspace?.activity) ? state.workspace.activity.slice(0, 8) : [];
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Обзор сервера</span>
            <p class="legal-section__description">Короткая сводка по готовности, обновлениям и последней активности.</p>
          </div>
        </div>
        <div class="legal-field-grid legal-field-grid--two">
          ${["laws", "features", "templates"].map((key) => `
            <div class="legal-field">
              <span class="legal-field__label">${escapeHtml(key)}</span>
              <div><span class="admin-badge ${badgeClass(blocks[key]?.status)}">${escapeHtml(String(blocks[key]?.status || "unknown"))}</span></div>
            </div>
          `).join("")}
          <div class="legal-field">
            <span class="legal-field__label">Последние обновления</span>
            <div class="admin-user-cell__secondary">publish batches: ${escapeHtml(String((dashboard.content?.publish_batches || []).length || 0))}</div>
            <div class="admin-user-cell__secondary">warning signals: ${escapeHtml(String((dashboard.release?.warning_signals || []).length || 0))}</div>
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
      const laws = state.workspace?.overview?.laws || {};
      const bindings = Array.isArray(laws.active_source_set_bindings) ? laws.active_source_set_bindings : [];
      const projection = laws.projection_bridge || {};
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Законы</span>
            <p class="legal-section__description">Source set bindings, active runtime law version и projection bridge summary.</p>
          </div>
          <div class="admin-section-toolbar">
            <a class="ghost-button button-link" href="/admin/laws">Открыть расширенный laws workspace</a>
          </div>
        </div>
        <div class="legal-field-grid legal-field-grid--two">
          <div class="legal-field">
            <span class="legal-field__label">Active law version</span>
            <div><strong>${escapeHtml(String(laws.active_law_version_id || "—"))}</strong></div>
            <div class="admin-user-cell__secondary">chunks: ${escapeHtml(String(laws.chunk_count || 0))}</div>
          </div>
          <div class="legal-field">
            <span class="legal-field__label">Projection bridge</span>
            <div><strong>${escapeHtml(String(projection.run_id || "—"))}</strong></div>
            <div class="admin-user-cell__secondary">status: ${escapeHtml(String(projection.status || "none"))}</div>
          </div>
        </div>
        <div class="legal-subcard">
          <span class="legal-field__label">Active source set bindings</span>
          ${
            bindings.length
              ? `<table class="legal-table admin-table admin-table--compact"><thead><tr><th>Source set</th><th>Priority</th><th>Status</th></tr></thead><tbody>${bindings.map((item) => `<tr><td>${escapeHtml(String(item.source_set_key || "—"))}</td><td>${escapeHtml(String(item.priority || 0))}</td><td>${item.is_active ? "active" : "disabled"}</td></tr>`).join("")}</tbody></table>`
              : '<p class="legal-section__description">Для сервера пока нет source set bindings.</p>'
          }
        </div>
      `;
    }

    function renderContentPanel(panelId, label, payload, advancedHref) {
      const hostNode = document.getElementById(panelId);
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      const items = Array.isArray(payload?.items) ? payload.items : [];
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">${escapeHtml(label)}</span>
            <p class="legal-section__description">Effective server view: сначала server overrides, затем global defaults.</p>
          </div>
          <div class="admin-section-toolbar">
            <a class="ghost-button button-link" href="${escapeHtml(advancedHref)}">Открыть расширенный раздел</a>
          </div>
        </div>
        <div class="legal-field-grid legal-field-grid--two">
          <div class="legal-field"><span class="legal-field__label">Effective</span><div><strong>${escapeHtml(String(payload?.effective || payload?.counts?.effective || 0))}</strong></div></div>
          <div class="legal-field"><span class="legal-field__label">Server overrides</span><div><strong>${escapeHtml(String(payload?.server || payload?.counts?.server || 0))}</strong></div></div>
        </div>
        ${
          items.length
            ? `<table class="legal-table admin-table admin-table--compact"><thead><tr><th>Key</th><th>Title</th><th>Source</th><th>Status</th></tr></thead><tbody>${items.map((item) => `<tr><td>${escapeHtml(String(item.content_key || "—"))}</td><td>${escapeHtml(String(item.title || "—"))}</td><td>${escapeHtml(String(item.source_scope || "—"))}</td><td>${escapeHtml(String(item.status || "—"))}</td></tr>`).join("")}</tbody></table>`
            : `<p class="legal-section__description">Effective items for "${escapeHtml(label)}" пока не найдены.</p>`
        }
      `;
    }

    function renderUsers() {
      const hostNode = document.getElementById("admin-server-workspace-panel-users");
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      const users = Array.isArray(state.workspace?.overview?.users?.items) ? state.workspace.overview.users.items : [];
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Пользователи сервера</span>
            <p class="legal-section__description">Пользователи, у которых этот сервер выбран как текущий server scope.</p>
          </div>
          <div class="admin-section-toolbar">
            <a class="ghost-button button-link" href="/admin/users">Открыть users workspace</a>
          </div>
        </div>
        ${
          users.length
            ? `<table class="legal-table admin-table admin-table--compact"><thead><tr><th>Username</th><th>Email</th><th>Flags</th><th>Status</th></tr></thead><tbody>${users.map((item) => `<tr><td>${escapeHtml(String(item.username || "—"))}</td><td>${escapeHtml(String(item.email || "—"))}</td><td>${item.is_tester ? "tester " : ""}${item.is_gka ? "gka" : ""}</td><td>${item.access_blocked ? "blocked" : item.deactivated_at ? "deactivated" : "active"}</td></tr>`).join("")}</tbody></table>`
            : '<p class="legal-section__description">Для сервера пока нет пользователей в выбранном server scope.</p>'
        }
      `;
    }

    function renderAccess() {
      const hostNode = document.getElementById("admin-server-workspace-panel-access");
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      const access = state.workspace?.overview?.access || {};
      const items = Array.isArray(access.items) ? access.items : [];
      const totals = Array.isArray(access.permission_totals) ? access.permission_totals : [];
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Роли / Доступ</span>
            <p class="legal-section__description">Effective permissions per server scope. Глубокое управление ролями остаётся совместимым с existing user admin flows.</p>
          </div>
        </div>
        <div class="legal-subcard">
          <span class="legal-field__label">Permission totals</span>
          ${
            totals.length
              ? `<div class="admin-section-toolbar">${totals.map((item) => `<span class="admin-badge admin-badge--muted">${escapeHtml(String(item.code || ""))}: ${escapeHtml(String(item.count || 0))}</span>`).join("")}</div>`
              : '<p class="legal-section__description">Разрешения для сервера пока не вычислены.</p>'
          }
        </div>
        ${
          items.length
            ? `<table class="legal-table admin-table admin-table--compact"><thead><tr><th>User</th><th>Permissions</th><th>Flags</th></tr></thead><tbody>${items.map((item) => `<tr><td>${escapeHtml(String(item.display_name || item.username || "—"))}</td><td>${escapeHtml(String((item.permissions || []).join(", ") || "—"))}</td><td>${item.is_tester ? "tester " : ""}${item.is_gka ? "gka " : ""}${item.is_blocked ? "blocked" : ""}</td></tr>`).join("")}</tbody></table>`
            : ""
        }
      `;
    }

    function renderAudit() {
      const hostNode = document.getElementById("admin-server-workspace-panel-audit");
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      const items = Array.isArray(state.activity?.items) ? state.activity.items : [];
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Аудит</span>
            <p class="legal-section__description">Unified recent activity feed for this server.</p>
          </div>
        </div>
        ${
          items.length
            ? `<ul class="legal-section__description">${items.map((item) => `<li><strong>${escapeHtml(String(item.title || item.kind || "event"))}</strong> • ${escapeHtml(String(item.created_at || "—"))} • ${escapeHtml(String(item.description || ""))}</li>`).join("")}</ul>`
            : '<p class="legal-section__description">История по серверу пока пуста.</p>'
        }
      `;
    }

    function renderErrors() {
      const hostNode = document.getElementById("admin-server-workspace-panel-errors");
      if (!(hostNode instanceof HTMLElement)) {
        return;
      }
      const issues = state.workspace?.issues || {};
      const items = Array.isArray(issues.items) ? issues.items : [];
      hostNode.innerHTML = `
        <div class="legal-subcard__header">
          <div>
            <span class="legal-field__label">Ошибки / Проблемы</span>
            <p class="legal-section__description">Незакрытые сигналы по законам, целостности, synthetic monitoring и jobs.</p>
          </div>
        </div>
        ${
          items.length
            ? `<table class="legal-table admin-table admin-table--compact"><thead><tr><th>Severity</th><th>Source</th><th>Title</th><th>Detail</th></tr></thead><tbody>${items.map((item) => `<tr><td>${escapeHtml(String(item.severity || "info"))}</td><td>${escapeHtml(String(item.source || "—"))}</td><td>${escapeHtml(String(item.title || "—"))}</td><td>${escapeHtml(String(item.detail || "—"))}</td></tr>`).join("")}</tbody></table>`
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
            <a class="ghost-button button-link" href="/admin/laws">Laws diagnostics</a>
            <a class="ghost-button button-link" href="/admin/dashboard">Ops dashboard</a>
          </div>
        </div>
        <pre class="legal-field__hint">${escapeHtml(JSON.stringify(state.workspace?.health || {}, null, 2))}</pre>
      `;
    }

    function renderPanels() {
      renderSummary();
      renderOverview();
      const features = state.workspace?.overview?.features || {};
      renderContentPanel("admin-server-workspace-panel-features", "Функции", features, "/admin/features");
      const templates = state.workspace?.overview?.templates || {};
      renderContentPanel("admin-server-workspace-panel-templates", "Шаблоны вывода", templates, "/admin/templates");
      renderLaws();
      renderUsers();
      renderAccess();
      renderAudit();
      renderErrors();
      renderDiagnostics();
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
        const [workspaceResponse, activityResponse] = await Promise.all([
          deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/workspace`),
          deps.apiFetch(`/api/admin/runtime-servers/${encodeURIComponent(serverCode)}/activity`),
        ]);
        const workspacePayload = await deps.parsePayload(workspaceResponse);
        const activityPayload = await deps.parsePayload(activityResponse);
        if (!workspaceResponse.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(workspaceResponse, workspacePayload, "Не удалось загрузить server workspace."));
          return;
        }
        if (!activityResponse.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(activityResponse, activityPayload, "Не удалось загрузить activity feed."));
          return;
        }
        state.workspace = workspacePayload;
        state.activity = activityPayload;
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
      if (target.id === "admin-server-workspace-refresh") {
        loadWorkspace();
      }
    });

    applyTabState();
    loadWorkspace();
  },
};
