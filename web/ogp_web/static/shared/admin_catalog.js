window.OGPAdminCatalog = {
  formatCatalogPreviewValue(value) {
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
  },

  renderCatalogAuditTrailMarkup(items) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    if (!items.length) {
      return '<p class="legal-section__description">По заданным фильтрам аудита записей нет.</p>';
    }
    return `
      <pre class="legal-field__hint">${escapeHtml(items.slice(0, 12).map((row) => `${row.created_at || "—"} ${row.author || "system"} ${row.action || "—"} ${row.entity_type || ""}#${row.entity_id || ""}\n${row.diff || ""}`).join("\n\n"))}</pre>
    `;
  },

  renderCatalogPreviewSummaryMarkup(entityType, item, effectivePayload) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
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
      .map((entry) => `<div class="admin-catalog-preview__summary-row"><span>${escapeHtml(entry.field)}</span><strong>${escapeHtml(String(entry.value))}</strong></div>`)
      .join("");
  },

  buildCatalogPreviewMetaText(payload, itemId) {
    const item = payload?.item || {};
    const versions = Array.isArray(payload?.versions) ? payload.versions : [];
    const latestChangeRequest = payload?.latest_change_request || (Array.isArray(payload?.change_requests) ? payload.change_requests[0] : null);
    const effectiveVersion = payload?.effective_version || null;
    return JSON.stringify(
      {
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
      },
      null,
      2,
    );
  },

  renderCatalogMarkup({
    entityType,
    items,
    audit,
    activeCatalogAuditEntityType,
    activeCatalogAuditEntityId,
  }) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
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
      validate: "Validate draft",
      submit_for_review: "Отправить на ревью",
      approve: "Одобрить",
      publish: "Опубликовать",
      request_changes: "Запросить доработки",
    };
    const allowedActionsByState = {
      draft: ["validate", "submit_for_review"],
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

    return `
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
          <strong>Основной сценарий</strong>
        </div>
        <p class="legal-section__description">Сначала настройте source set и revision, затем привяжите его к серверу и запустите preview. Технические детали и legacy-совместимость скрыты ниже.</p>
        <div class="admin-section-toolbar">
          <strong>Source Sets</strong>
          <div>
            <button type="button" id="law-source-sets-refresh" class="ghost-button">Обновить</button>
            <button type="button" id="law-source-sets-create" class="primary-button">Добавить source set</button>
          </div>
        </div>
        <label class="legal-field" style="max-width:420px">
          <span class="legal-field__label">Поиск source set</span>
          <input id="law-source-sets-search" type="search" placeholder="source_set_key или title">
        </label>
        <div id="law-source-sets-host"></div>
        <hr>
        <div class="admin-section-toolbar">
          <strong>Revisions</strong>
          <div>
            <button type="button" id="law-source-set-revisions-refresh" class="ghost-button">Обновить</button>
            <button type="button" id="law-source-set-revision-create" class="primary-button">Добавить revision</button>
          </div>
        </div>
        <div id="law-source-set-revisions-host"></div>
        <hr>
        <div class="admin-section-toolbar">
          <strong>Server Bindings</strong>
          <label class="legal-field" style="min-width:260px">
            <span class="legal-field__label">Сервер</span>
            <select id="law-sources-server-select"></select>
          </label>
          <div>
            <button type="button" id="server-source-set-bindings-refresh" class="ghost-button">Обновить</button>
            <button type="button" id="server-source-set-bindings-add" class="primary-button">Привязать source set</button>
          </div>
        </div>
        <div id="server-source-set-bindings-host"></div>
        <hr>
        <div class="admin-section-toolbar">
          <strong>Main Check</strong>
        </div>
        <div id="law-main-check-host"></div>
        <p class="legal-field__hint">Manual canonical law creation/edit is not supported in this slice. Advanced pipeline steps remain available through diagnostics.</p>
        <div id="law-canonical-pipeline-host" hidden></div>
        <details id="law-legacy-runtime-panel" class="legal-subcard">
          <summary>Legacy / Runtime</summary>
          <p class="legal-section__description">Редкие compatibility и runtime-инструменты. Открывайте этот блок только когда нужен legacy path или расширенная диагностика.</p>
          <div class="admin-section-toolbar">
            <strong>Источники законов</strong>
            <div>
              <button type="button" id="law-sources-sync" class="ghost-button">Синхронизировать текущие</button>
              <button type="button" id="law-sources-save" class="ghost-button">Сохранить без пересборки</button>
              <button type="button" id="law-sources-preview" class="ghost-button">Проверить ссылки</button>
              <button type="button" id="law-sources-rebuild-async" class="ghost-button">Пересобрать в фоне</button>
              <button type="button" id="law-sources-rebuild" class="primary-button">Пересобрать законы</button>
            </div>
          </div>
          <p id="law-sources-status" class="legal-section__description">Загружаем источники и активную версию...</p>
          <div id="platform-blueprint-stage" class="legal-subcard"></div>
          <div id="server-setup-workflow-host"></div>
          <p id="law-sources-validation" class="legal-section__description">Перед пересборкой можно проверить ссылки на валидность и дубликаты.</p>
          <p id="law-sources-task-status" class="legal-section__description"></p>
          <label class="legal-field">
            <span class="legal-field__label">Ссылки на законы</span>
            <textarea id="law-sources-textarea" rows="8" placeholder="По одной ссылке на строку"></textarea>
            <span class="legal-field__hint">Compatibility-вход для legacy runtime path. Канонический путь начинается выше с source set и revision.</span>
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
          <hr>
          <div class="admin-section-toolbar">
            <strong>Привязка закона к серверу</strong>
            <div>
              <button type="button" id="server-law-bindings-refresh" class="ghost-button">Обновить привязки</button>
              <button type="button" id="server-law-bindings-add" class="primary-button">Привязать закон к серверу</button>
            </div>
          </div>
          <div id="server-law-bindings-host"></div>
          <hr>
          <div class="admin-section-toolbar">
            <strong>Jobs / Alerts</strong>
            <div>
              <button type="button" id="law-jobs-refresh" class="ghost-button">Обновить jobs</button>
            </div>
          </div>
          <div id="law-jobs-host"></div>
        </details>
      </div>
      ` : ""}
      ${entityType === "laws" ? '<details class="legal-subcard"><summary>Системный каталог</summary>' : ""}
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
                  const author = String(auditRow.author || item.updated_by || item.created_by || "system");
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
                          .map((action) => `<button type="button" class="ghost-button" data-catalog-workflow-item="${escapeHtml(String(item.id || ""))}" data-catalog-workflow-action="${escapeHtml(action)}" data-catalog-workflow-cr-id="${escapeHtml(String(changeRequestId || 0))}">${escapeHtml(workflowActionLabels[action] || action)}</button>`)
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
      <div class="admin-section-toolbar">
        <label class="legal-field"><span class="legal-field__label">entity_type</span><input id="catalog-audit-entity-type" value="${escapeHtml(activeCatalogAuditEntityType)}" placeholder="content_item"></label>
        <label class="legal-field"><span class="legal-field__label">entity_id</span><input id="catalog-audit-entity-id" value="${escapeHtml(activeCatalogAuditEntityId)}" placeholder="42"></label>
        <label class="legal-field"><span class="legal-field__label">limit</span><input id="catalog-audit-limit" type="number" min="1" max="500" value="12"></label>
        <button type="button" id="catalog-audit-refresh" class="ghost-button">Обновить журнал</button>
      </div>
      <div id="catalog-audit-results">
        <pre class="legal-field__hint">${escapeHtml(audit.slice(0, 8).map((row) => `${row.created_at} ${row.author} ${row.action} ${row.workflow_from || ""}->${row.workflow_to || ""}\n${row.diff || ""}`).join("\n\n"))}</pre>
      </div>
      ${entityType === "laws" ? "</details>" : ""}
    `;
  },
};
