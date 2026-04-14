window.OGPAdminUserDetails = {
  renderUserModalMarkup(user, helpers = {}) {
    const escapeHtml = helpers.escapeHtml || ((value) => String(value ?? ""));
    const renderUserStatuses = helpers.renderUserStatuses || (() => "");

    return `
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
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(user.last_seen_at || "-")}</strong>
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
          <div><span class="legal-field__label">Создан</span><div class="admin-user-detail-text">${escapeHtml(user.created_at || "-")}</div></div>
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
  },
};
