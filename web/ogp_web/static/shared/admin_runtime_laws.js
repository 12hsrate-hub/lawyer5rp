window.OGPAdminRuntimeLaws = {
  renderWorkflowStep({ title, status, detail, actionHtml = "", tone = "pending" }) {
    const toneClass = tone === "done" ? "admin-workflow-step--done" : tone === "warning" ? "admin-workflow-step--warning" : "";
    const badgeClass = tone === "done" ? "admin-badge--success" : tone === "warning" ? "admin-badge--warning" : "admin-badge--muted";
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    return `
      <article class="admin-workflow-step ${toneClass}">
        <div class="admin-workflow-step__top">
          <strong>${escapeHtml(title)}</strong>
          <span class="admin-badge ${badgeClass}">${escapeHtml(status)}</span>
        </div>
        <p class="legal-section__description">${escapeHtml(detail)}</p>
        ${actionHtml ? `<div class="admin-section-toolbar">${actionHtml}</div>` : ""}
      </article>
    `;
  },

  renderServerSetupWorkflow({
    server,
    activeLawServerCode,
    runtimeServerItems,
    activeLawSet,
    bindingCount,
    runtimeServerHealth,
  }) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    const serverTitle = String(server?.title || activeLawServerCode || "—").trim();
    const runtimeCount = Array.isArray(runtimeServerItems) ? runtimeServerItems.length : 0;
    const summary = runtimeServerHealth?.summary || {};
    const checks = runtimeServerHealth?.checks || {};
    const onboarding = runtimeServerHealth?.onboarding || server?.onboarding || {};
    const readyCount = Number(summary.ready_count || 0);
    const totalCount = Number(summary.total_count || 5);
    const healthOk = Boolean(checks.health?.ok);
    const onboardingState = String(onboarding.highest_completed_state || "not-ready");
    const onboardingSource = String(onboarding.resolution_label || "unknown");
    const healthDetail = healthOk
      ? `Version ${String(checks.health?.active_law_version_id || "-")}, chunks ${String(checks.health?.chunk_count || 0)}.`
      : String(checks.health?.detail || "Run health verification after binding and activation.");

    return `
      <div class="admin-catalog-preview">
        <div class="admin-catalog-preview__header">
          <h4 class="admin-catalog-preview__title">Быстрый сценарий: сервер → законы → активация</h4>
          <span class="admin-badge ${readyCount === totalCount ? "admin-badge--success" : "admin-badge--muted"}">${escapeHtml(`${readyCount}/${totalCount}`)}</span>
        </div>
        <p class="legal-section__description">${escapeHtml(
          server
            ? `Сервер ${serverTitle} (${String(server.code || "").trim().toLowerCase()}) подготовлен на ${readyCount}/${totalCount} health-шагов. Onboarding state: ${onboardingState}. Resolution: ${onboardingSource}.`
            : "Сначала создайте или выберите runtime-сервер, затем пройдите шаги подготовки.",
        )}</p>
        <div class="admin-workflow-grid">
          ${window.OGPAdminRuntimeLaws.renderWorkflowStep({
            title: "1. Сервер",
            status: server ? "выбран" : "не выбран",
            detail: server ? `${serverTitle}. Статус: ${server.is_active ? "active" : "disabled"}. Onboarding: ${onboardingState}. Resolution: ${onboardingSource}.` : "Создайте новый runtime-сервер или выберите существующий в селекторе выше.",
            tone: server ? "done" : "warning",
            actionHtml: `
              <button type="button" id="workflow-create-server" class="primary-button">Создать сервер</button>
              <button type="button" id="workflow-refresh-runtime" class="ghost-button">Обновить список</button>
            `,
          })}
          ${window.OGPAdminRuntimeLaws.renderWorkflowStep({
            title: "2. Набор законов",
            status: activeLawSet ? "готов" : "пусто",
            detail: activeLawSet
              ? `Найден набор "${String(activeLawSet.name || "—")}" (${activeLawSet.is_published ? "published" : "draft"}).`
              : "Создайте хотя бы один набор законов для выбранного сервера.",
            tone: activeLawSet ? "done" : "warning",
            actionHtml: `
              <button type="button" id="workflow-create-law-set" class="primary-button" ${server ? "" : "disabled"}>Создать набор</button>
              <button type="button" id="workflow-refresh-law-sets" class="ghost-button" ${server ? "" : "disabled"}>Обновить наборы</button>
            `,
          })}
          ${window.OGPAdminRuntimeLaws.renderWorkflowStep({
            title: "3. Привязка закона",
            status: bindingCount > 0 ? `${bindingCount} привязок` : "нет привязок",
            detail: bindingCount > 0
              ? "Есть связанные законы для выбранного сервера."
              : "Привяжите хотя бы один закон к серверу через выбор из реестра и наборов.",
            tone: bindingCount > 0 ? "done" : "warning",
            actionHtml: `
              <button type="button" id="workflow-add-binding" class="primary-button" ${server ? "" : "disabled"}>Привязать закон</button>
              <button type="button" id="workflow-refresh-bindings" class="ghost-button" ${server ? "" : "disabled"}>Обновить привязки</button>
            `,
          })}
          ${window.OGPAdminRuntimeLaws.renderWorkflowStep({
            title: "4. Активация",
            status: server?.is_active ? "active" : "disabled",
            detail: server
              ? (server.is_active ? "Сервер активен и может использоваться в runtime." : "После подготовки включите сервер.")
              : "Шаг станет доступен после выбора или создания сервера.",
            tone: server?.is_active ? "done" : "warning",
            actionHtml: `
              <button type="button" id="workflow-activate-server" class="primary-button" ${server ? "" : "disabled"}>${server?.is_active ? "Сервер уже активен" : "Активировать сервер"}</button>
              <button type="button" id="workflow-open-server-panel" class="ghost-button" ${runtimeCount ? "" : "disabled"}>Показать серверы</button>
            `,
          })}
          ${window.OGPAdminRuntimeLaws.renderWorkflowStep({
            title: "5. Health",
            status: healthOk ? "ok" : "pending",
            detail: healthDetail,
            tone: healthOk ? "done" : "warning",
            actionHtml: `
              <button type="button" id="workflow-check-health" class="primary-button" ${server ? "" : "disabled"}>Check health</button>
              <button type="button" id="workflow-refresh-health" class="ghost-button" ${server ? "" : "disabled"}>Refresh health</button>
            `,
          })}
        </div>
        <p class="legal-field__hint">Health verification checks whether the server has an active indexed law version.</p>
      </div>
    `;
  },

  renderLawSetsTable(items) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    return `
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
                <button type="button" class="ghost-button" data-law-set-rollback="${escapeHtml(String(item.id || ""))}">Rollback</button>
              </td>
            </tr>
          `).join("") : '<tr><td colspan="6" class="legal-section__description">Наборы законов пока не созданы.</td></tr>'}
        </tbody>
      </table>
    `;
  },

  renderServerLawBindingsTable(items) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    return `
      <table class="legal-table admin-table admin-table--compact">
        <thead><tr><th>Law set</th><th>Law code</th><th>Source</th><th>Priority</th><th>Effective from</th></tr></thead>
        <tbody>
          ${items.length ? items.map((item) => `
            <tr>
              <td>${escapeHtml(String(item.law_set_name || item.law_set_id || "—"))}</td>
              <td>${escapeHtml(String(item.law_code || "—"))}</td>
              <td>${escapeHtml(String(item.source_name || item.source_url || "—"))}</td>
              <td>${escapeHtml(String(item.priority || 0))}</td>
              <td>${escapeHtml(String(item.effective_from || "—"))}</td>
            </tr>
          `).join("") : '<tr><td colspan="5" class="legal-section__description">Для выбранного сервера пока нет привязанных законов.</td></tr>'}
        </tbody>
      </table>
    `;
  },

  renderRuntimeServersTable(items) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    return `
      <table class="legal-table admin-table admin-table--compact">
        <thead>
          <tr><th>Код</th><th>Название</th><th>Статус</th><th>Onboarding</th><th>Действия</th></tr>
        </thead>
        <tbody>
          ${items.length
            ? items.map((item) => `
              <tr>
                <td>${escapeHtml(String(item.code || "—"))}</td>
                <td>${escapeHtml(String(item.title || "—"))}</td>
                <td>${item.is_active ? "active" : "disabled"}</td>
                <td>${escapeHtml(String(item.onboarding?.highest_completed_state || "not-ready"))}<br><span class="admin-user-cell__secondary">${escapeHtml(String(item.onboarding?.resolution_label || "unknown"))}</span></td>
                <td>
                  <button type="button" class="ghost-button" data-runtime-server-edit="${escapeHtml(String(item.code || ""))}" data-runtime-server-title="${escapeHtml(String(item.title || ""))}">Изменить</button>
                  <button type="button" class="ghost-button" data-runtime-server-toggle="${escapeHtml(String(item.code || ""))}" data-runtime-server-active="${item.is_active ? "1" : "0"}">${item.is_active ? "Деактивировать" : "Активировать"}</button>
                </td>
              </tr>
            `).join("")
            : '<tr><td colspan="5" class="legal-section__description">Серверы не найдены.</td></tr>'}
        </tbody>
      </table>
    `;
  },

  renderSourceSetsTable(items, { selectedKey = "", search = "" } = {}) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    const normalizedSearch = String(search || "").trim().toLowerCase();
    const filtered = items.filter((item) => {
      if (!normalizedSearch) {
        return true;
      }
      const haystack = [item?.source_set_key, item?.title, item?.description]
        .map((value) => String(value || "").toLowerCase())
        .join(" ");
      return haystack.includes(normalizedSearch);
    });
    return `
      <table class="legal-table admin-table admin-table--compact">
        <thead><tr><th>Key</th><th>Title</th><th>Scope</th><th>Updated</th><th>Actions</th></tr></thead>
        <tbody>
          ${filtered.length ? filtered.map((item) => `
            <tr ${String(item?.source_set_key || "") === String(selectedKey || "") ? 'class="is-selected"' : ""}>
              <td><code>${escapeHtml(String(item?.source_set_key || "—"))}</code></td>
              <td>${escapeHtml(String(item?.title || "—"))}<br><span class="admin-user-cell__secondary">${escapeHtml(String(item?.description || ""))}</span></td>
              <td>${escapeHtml(String(item?.scope || "global"))}</td>
              <td>${escapeHtml(String(item?.updated_at || "—"))}</td>
              <td>
                <button type="button" class="ghost-button" data-source-set-select="${escapeHtml(String(item?.source_set_key || ""))}">Открыть</button>
                <button type="button" class="ghost-button" data-source-set-edit="${escapeHtml(String(item?.source_set_key || ""))}">Изменить</button>
              </td>
            </tr>
          `).join("") : '<tr><td colspan="5" class="legal-section__description">Source sets пока не созданы.</td></tr>'}
        </tbody>
      </table>
    `;
  },

  renderSourceSetRevisionsPanel(payload, { selectedRevisionId = 0 } = {}) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    const sourceSet = payload?.source_set || null;
    const items = Array.isArray(payload?.items) ? payload.items : [];
    if (!sourceSet) {
      return '<p class="legal-section__description">Выберите source set, чтобы увидеть revisions и container links.</p>';
    }
    return `
      <div class="admin-catalog-preview">
        <div class="admin-catalog-preview__header">
          <h4 class="admin-catalog-preview__title">${escapeHtml(String(sourceSet.title || sourceSet.source_set_key || "Source set"))}</h4>
          <span class="admin-badge admin-badge--muted">${escapeHtml(String(payload?.count || 0))} revisions</span>
        </div>
        <p class="legal-section__description">${escapeHtml(String(sourceSet.description || "Без описания."))}</p>
        <table class="legal-table admin-table admin-table--compact">
          <thead><tr><th>Revision</th><th>Status</th><th>Container links</th><th>Policy</th><th>Actions</th></tr></thead>
          <tbody>
            ${items.length ? items.map((item) => `
              <tr ${Number(item?.id || 0) === Number(selectedRevisionId || 0) ? 'class="is-selected"' : ""}>
                <td>#${escapeHtml(String(item?.revision || item?.id || "—"))}</td>
                <td>${escapeHtml(String(item?.status || "draft"))}</td>
                <td>${(Array.isArray(item?.container_urls) ? item.container_urls : []).map((url) => `<div class="admin-user-cell__secondary">${escapeHtml(String(url || ""))}</div>`).join("") || "—"}</td>
                <td><pre class="legal-field__hint">${escapeHtml(JSON.stringify(item?.adapter_policy_json || {}, null, 2))}</pre></td>
                <td>
                  <button type="button" class="ghost-button" data-source-set-revision-select="${escapeHtml(String(item?.id || ""))}">Выбрать</button>
                  <button type="button" class="ghost-button" data-source-set-discovery-run="${escapeHtml(String(item?.id || ""))}">Discovery</button>
                </td>
              </tr>
            `).join("") : '<tr><td colspan="5" class="legal-section__description">Revisions пока нет.</td></tr>'}
          </tbody>
        </table>
      </div>
    `;
  },

  renderServerSourceSetBindingsTable(items) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    return `
      <table class="legal-table admin-table admin-table--compact">
        <thead><tr><th>Priority</th><th>Source set</th><th>Status</th><th>Overrides</th><th>Actions</th></tr></thead>
        <tbody>
          ${items.length ? items.map((item) => `
            <tr>
              <td>${escapeHtml(String(item?.priority || 0))}</td>
              <td><code>${escapeHtml(String(item?.source_set_key || "—"))}</code></td>
              <td>${item?.is_active ? "active" : "disabled"}</td>
              <td>
                <div class="admin-user-cell__secondary">include: ${escapeHtml(String((item?.include_law_keys || []).join(", ") || "—"))}</div>
                <div class="admin-user-cell__secondary">exclude: ${escapeHtml(String((item?.exclude_law_keys || []).join(", ") || "—"))}</div>
              </td>
              <td>
                <button type="button" class="ghost-button" data-server-source-set-binding-edit="${escapeHtml(String(item?.id || ""))}">Изменить</button>
                <button type="button" class="ghost-button" data-server-source-set-binding-toggle="${escapeHtml(String(item?.id || ""))}" data-server-source-set-binding-active="${item?.is_active ? "1" : "0"}">${item?.is_active ? "Отключить" : "Включить"}</button>
              </td>
            </tr>
          `).join("") : '<tr><td colspan="5" class="legal-section__description">Для выбранного сервера нет source-set bindings.</td></tr>'}
        </tbody>
      </table>
    `;
  },

  renderCanonicalPipelineMarkup(state = {}) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    const discoveryRuns = Array.isArray(state.discoveryRuns?.items) ? state.discoveryRuns.items : [];
    const links = Array.isArray(state.discoveryLinks?.items) ? state.discoveryLinks.items : [];
    const documents = Array.isArray(state.discoveryDocuments?.items) ? state.discoveryDocuments.items : [];
    const versions = Array.isArray(state.documentVersions?.items) ? state.documentVersions.items : [];
    const projectionRuns = Array.isArray(state.projectionRuns?.items) ? state.projectionRuns.items : [];
    const projectionItems = Array.isArray(state.projectionItems?.items) ? state.projectionItems.items : [];
    const selectedRun = state.selectedDiscoveryRunId ? `run #${state.selectedDiscoveryRunId}` : "не выбран";
    const selectedProjectionRun = state.selectedProjectionRunId ? `run #${state.selectedProjectionRunId}` : "не выбран";
    return `
      <div class="legal-field-grid legal-field-grid--two">
        <div class="legal-subcard">
          <div class="admin-section-toolbar">
            <strong>Discovery runs</strong>
            <span class="admin-badge admin-badge--muted">${escapeHtml(String(discoveryRuns.length))}</span>
          </div>
          <table class="legal-table admin-table admin-table--compact">
            <thead><tr><th>ID</th><th>Status</th><th>Summary</th><th>Actions</th></tr></thead>
            <tbody>
              ${discoveryRuns.length ? discoveryRuns.map((item) => `
                <tr>
                  <td>#${escapeHtml(String(item?.id || "—"))}</td>
                  <td>${escapeHtml(String(item?.status || "—"))}</td>
                  <td>${escapeHtml(String((item?.summary_json || {}).result || (item?.summary_json || {}).summary || "—"))}</td>
                  <td>
                    <button type="button" class="ghost-button" data-discovery-run-select="${escapeHtml(String(item?.id || ""))}">Открыть</button>
                    <button type="button" class="ghost-button" data-discovery-run-ingest-docs="${escapeHtml(String(item?.id || ""))}">Documents</button>
                    <button type="button" class="ghost-button" data-discovery-run-ingest-versions="${escapeHtml(String(item?.id || ""))}">Versions</button>
                    <button type="button" class="ghost-button" data-discovery-run-fetch="${escapeHtml(String(item?.id || ""))}">Fetch</button>
                    <button type="button" class="ghost-button" data-discovery-run-parse="${escapeHtml(String(item?.id || ""))}">Parse</button>
                  </td>
                </tr>
              `).join("") : '<tr><td colspan="4" class="legal-section__description">Discovery runs пока нет.</td></tr>'}
            </tbody>
          </table>
        </div>
        <div class="legal-subcard">
          <strong>Selected discovery</strong>
          <p class="legal-section__description">Текущий selection: ${escapeHtml(selectedRun)}</p>
          <div class="admin-user-cell__secondary">links: ${escapeHtml(String(links.length))}, documents: ${escapeHtml(String(documents.length))}, versions: ${escapeHtml(String(versions.length))}</div>
          <details ${links.length ? "open" : ""}>
            <summary>Discovered links</summary>
            <pre class="legal-field__hint">${escapeHtml(JSON.stringify(links, null, 2))}</pre>
          </details>
          <details ${documents.length ? "open" : ""}>
            <summary>Canonical documents</summary>
            <pre class="legal-field__hint">${escapeHtml(JSON.stringify(documents, null, 2))}</pre>
          </details>
          <details ${versions.length ? "open" : ""}>
            <summary>Document versions</summary>
            <pre class="legal-field__hint">${escapeHtml(JSON.stringify(versions, null, 2))}</pre>
          </details>
        </div>
        <div class="legal-subcard">
          <div class="admin-section-toolbar">
            <strong>Projection runs</strong>
            <span class="admin-badge admin-badge--muted">${escapeHtml(String(projectionRuns.length))}</span>
          </div>
          <table class="legal-table admin-table admin-table--compact">
            <thead><tr><th>ID</th><th>Status</th><th>Decision</th><th>Actions</th></tr></thead>
            <tbody>
              ${projectionRuns.length ? projectionRuns.map((item) => `
                <tr>
                  <td>#${escapeHtml(String(item?.id || "—"))}</td>
                  <td>${escapeHtml(String(item?.status || "—"))}</td>
                  <td>${escapeHtml(String((item?.summary_json || {}).decision_status || "—"))}</td>
                  <td>
                    <button type="button" class="ghost-button" data-projection-run-select="${escapeHtml(String(item?.id || ""))}">Открыть</button>
                    <button type="button" class="ghost-button" data-projection-run-approve="${escapeHtml(String(item?.id || ""))}">Approve</button>
                    <button type="button" class="ghost-button" data-projection-run-hold="${escapeHtml(String(item?.id || ""))}">Hold</button>
                    <button type="button" class="ghost-button" data-projection-run-materialize="${escapeHtml(String(item?.id || ""))}">Materialize</button>
                    <button type="button" class="ghost-button" data-projection-run-activate="${escapeHtml(String(item?.id || ""))}">Activate</button>
                  </td>
                </tr>
              `).join("") : '<tr><td colspan="4" class="legal-section__description">Projection runs пока нет.</td></tr>'}
            </tbody>
          </table>
        </div>
        <div class="legal-subcard">
          <strong>Projection status</strong>
          <p class="legal-section__description">Текущий selection: ${escapeHtml(selectedProjectionRun)}</p>
          <details ${projectionItems.length ? "open" : ""}>
            <summary>Projection items</summary>
            <pre class="legal-field__hint">${escapeHtml(JSON.stringify(projectionItems, null, 2))}</pre>
          </details>
          <details ${state.projectionStatus ? "open" : ""}>
            <summary>Projection status / runtime alignment</summary>
            <pre class="legal-field__hint">${escapeHtml(JSON.stringify(state.projectionStatus || {}, null, 2))}</pre>
          </details>
        </div>
      </div>
    `;
  },
};
