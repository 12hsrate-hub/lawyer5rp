window.OGPAdminActivity = {
  getExamEntryStatus(entry, helpers = {}) {
    const ExamView = helpers.ExamView || window.OGPExamImportView;
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
  },

  formatExamAverage(entry, helpers = {}) {
    const ExamView = helpers.ExamView || window.OGPExamImportView;
    if (ExamView?.formatAverage) {
      return ExamView.formatAverage(entry);
    }
    return entry?.average_score != null ? `${entry.average_score} / 100` : "—";
  },

  renderAdminExamEntriesSectionMarkup({ title, description, entries, emptyText, emphasizeFailed = false }, helpers = {}) {
    const escapeHtml = helpers.escapeHtml || ((value) => String(value ?? ""));
    const renderBadge = helpers.renderBadge || ((text) => String(text ?? ""));
    const getExamEntryStatus = helpers.getExamEntryStatus || ((entry) => this.getExamEntryStatus(entry, helpers));
    const formatExamAverage = helpers.formatExamAverage || ((entry) => this.formatExamAverage(entry, helpers));

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
  },

  renderExamImportMarkup(summary, helpers = {}) {
    const escapeHtml = helpers.escapeHtml || ((value) => String(value ?? ""));
    const renderBadge = helpers.renderBadge || ((text) => String(text ?? ""));
    const describeEventType = helpers.describeEventType || ((value) => String(value ?? ""));
    const renderAdminExamEntriesSectionMarkup =
      helpers.renderAdminExamEntriesSectionMarkup || ((config) => this.renderAdminExamEntriesSectionMarkup(config, helpers));

    if (!summary) {
      return '<p class="legal-section__description">Пока нет данных по импорту экзаменов.</p>';
    }

    const lastSync = summary.last_sync || {};
    const lastScore = summary.last_score || {};
    const recentFailures = [...(summary.recent_failures || []), ...(summary.recent_row_failures || [])];
    const recentEntries = Array.isArray(summary.recent_entries) ? summary.recent_entries : [];
    const failedEntries = Array.isArray(summary.failed_entries) ? summary.failed_entries : [];

    return `
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
      ${renderAdminExamEntriesSectionMarkup({
        title: "Последние ответы и оценки",
        description: "Последние импортированные строки с текущим баллом, статусом и быстрым переходом к детальному разбору.",
        entries: recentEntries,
        emptyText: "Пока нет строк, которые можно показать в админке.",
      })}
      ${renderAdminExamEntriesSectionMarkup({
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
  },

  renderUserStatusesMarkup(user, helpers = {}) {
    const renderBadge = helpers.renderBadge || ((text) => String(text ?? ""));
    const riskLabel = helpers.riskLabel || (() => "");
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
  },

  renderUserActivityMarkup(user, helpers = {}) {
    const escapeHtml = helpers.escapeHtml || ((value) => String(value ?? ""));
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
  },

  renderUsersMarkup(users, options = {}, helpers = {}) {
    const escapeHtml = helpers.escapeHtml || ((value) => String(value ?? ""));
    const renderUserStatusesMarkup = helpers.renderUserStatusesMarkup || ((user) => this.renderUserStatusesMarkup(user, helpers));
    const renderUserActivityMarkup = helpers.renderUserActivityMarkup || ((user) => this.renderUserActivityMarkup(user, helpers));
    const userSort = options.userSort || "complaints";
    const selectedBulkUsers = options.selectedBulkUsers || new Set();

    if (!users.length) {
      return '<p class="legal-section__description">По текущему фильтру пользователи не найдены.</p>';
    }

    return `
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
                    <td>${renderUserStatusesMarkup(user)}</td>
                    <td>${renderUserActivityMarkup(user)}</td>
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
  },

  renderEventsMarkup(events, helpers = {}) {
    const escapeHtml = helpers.escapeHtml || ((value) => String(value ?? ""));
    const renderBadge = helpers.renderBadge || ((text) => String(text ?? ""));
    const describeEventType = helpers.describeEventType || ((value) => String(value ?? ""));
    const describeApiPath = helpers.describeApiPath || ((value) => String(value ?? ""));

    if (!events.length) {
      return '<p class="legal-section__description">Событий по текущему фильтру нет.</p>';
    }

    return `
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
  },

  renderErrorExplorerMarkup(payload, helpers = {}) {
    const escapeHtml = helpers.escapeHtml || ((value) => String(value ?? ""));
    const renderBadge = helpers.renderBadge || ((text) => String(text ?? ""));
    const items = Array.isArray(payload?.items) ? payload.items : [];
    const byType = Array.isArray(payload?.by_event_type) ? payload.by_event_type : [];
    const byPath = Array.isArray(payload?.by_path) ? payload.by_path : [];

    if (!items.length) {
      return '<p class="legal-section__description">Ошибок по текущему фильтру не найдено.</p>';
    }

    const topTypeText = byType.slice(0, 3).map((item) => `${item.event_type}: ${item.count}`).join(" · ");
    const topPathText = byPath.slice(0, 3).map((item) => `${item.path}: ${item.count}`).join(" · ");

    return `
      <div class="admin-section-toolbar">
        <p class="legal-section__description">Ошибок: ${escapeHtml(String(payload?.total || items.length))}</p>
        <p class="legal-section__description">Топ типов: ${escapeHtml(topTypeText || "—")}</p>
        <p class="legal-section__description">Топ endpoint: ${escapeHtml(topPathText || "—")}</p>
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
  },

  renderAdminAuditMarkup(events, helpers = {}) {
    const escapeHtml = helpers.escapeHtml || ((value) => String(value ?? ""));
    const renderBadge = helpers.renderBadge || ((text) => String(text ?? ""));
    const describeEventType = helpers.describeEventType || ((value) => String(value ?? ""));
    const describeApiPath = helpers.describeApiPath || ((value) => String(value ?? ""));
    const adminEvents = events.filter((event) => String(event.event_type || "").startsWith("admin_"));

    if (!adminEvents.length) {
      return '<p class="legal-section__description">Админ-действий по текущему фильтру пока не видно.</p>';
    }

    return `
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
  },
};
