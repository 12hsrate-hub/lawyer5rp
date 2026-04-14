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
    const readyCount = Number(summary.ready_count || 0);
    const totalCount = Number(summary.total_count || 5);
    const healthOk = Boolean(checks.health?.ok);
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
            ? `Сервер ${serverTitle} (${String(server.code || "").trim().toLowerCase()}) подготовлен на ${readyCount}/${totalCount} шагов.`
            : "Сначала создайте или выберите runtime-сервер, затем пройдите шаги подготовки.",
        )}</p>
        <div class="admin-workflow-grid">
          ${window.OGPAdminRuntimeLaws.renderWorkflowStep({
            title: "1. Сервер",
            status: server ? "выбран" : "не выбран",
            detail: server ? `${serverTitle}. Статус: ${server.is_active ? "active" : "disabled"}.` : "Создайте новый runtime-сервер или выберите существующий в селекторе выше.",
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
  },
};
