window.OGPExamImportView = {
  getEntryStatus(entry) {
    const average = Number(entry?.average_score);
    if (entry?.average_score == null || Number.isNaN(average)) {
      return { key: "pending", label: "Ожидает проверки", tone: "pending" };
    }
    if (average >= 100) {
      return { key: "ok", label: "Проверен без замечаний", tone: "ok" };
    }
    return { key: "problem", label: "Есть замечания", tone: "problem" };
  },

  getScoreTone(score) {
    const value = Number(score);
    if (!Number.isFinite(value)) {
      return "pending";
    }
    if (value >= 90) {
      return "ok";
    }
    if (value >= 70) {
      return "warn";
    }
    return "problem";
  },

  renderScoreBadge(score, escapeHtml) {
    const tone = this.getScoreTone(score);
    const safeScore = score == null ? "—" : String(score);
    return `<span class="exam-score-badge exam-score-badge--${tone}">${escapeHtml(safeScore)}</span>`;
  },

  formatScoreRange(examScores) {
    if (!Array.isArray(examScores) || !examScores.length) {
      return "F-AD";
    }
    const first = examScores[0]?.column || "F";
    const last = examScores[examScores.length - 1]?.column || "AD";
    return `${first}-${last}`;
  },

  formatAverage(entry) {
    return entry.average_score != null ? `${entry.average_score} / 100` : "—";
  },

  renderRowActions(entry, escapeHtml) {
    const sourceRow = escapeHtml(entry.source_row ?? "");
    const canScore = entry.average_score == null;
    return `
      <div class="legal-inline-actions">
        ${canScore ? `<button type="button" class="ghost-button exam-score-row-btn" data-source-row="${sourceRow}">Проверить</button>` : ""}
        <button type="button" class="ghost-button exam-detail-btn" data-source-row="${sourceRow}">Открыть</button>
      </div>
    `;
  },

  renderEmptyRows() {
    return `
      <tr>
        <td colspan="11" class="legal-table__empty">База пока пустая. Первый импорт создаст записи из Google Sheets.</td>
      </tr>
    `;
  },

  renderRows(host, entries, escapeHtml) {
    if (!host) {
      return;
    }

    if (!entries.length) {
      host.innerHTML = this.renderEmptyRows();
      return;
    }

    host.innerHTML = entries
      .map((entry) => {
        const status = this.getEntryStatus(entry);
        return `
          <tr
            data-source-row="${escapeHtml(entry.source_row ?? "")}" 
            data-row-status="${escapeHtml(status.key)}"
            data-row-name="${escapeHtml(String(entry.full_name ?? "").toLowerCase())}"
            data-row-discord="${escapeHtml(String(entry.discord_tag ?? "").toLowerCase())}"
            data-row-passport="${escapeHtml(String(entry.passport ?? "").toLowerCase())}"
          >
            <td>${escapeHtml(entry.source_row ?? "")}</td>
            <td>${escapeHtml(entry.submitted_at ?? "")}</td>
            <td>${escapeHtml(entry.full_name ?? "")}</td>
            <td>${escapeHtml(entry.discord_tag ?? "")}</td>
            <td>${escapeHtml(entry.passport ?? "")}</td>
            <td>${escapeHtml(entry.exam_format ?? "")}</td>
            <td>${escapeHtml(entry.answer_count ?? 0)}</td>
            <td class="exam-average-cell">${escapeHtml(this.formatAverage(entry))}</td>
            <td><span class="exam-status-badge exam-status-badge--${escapeHtml(status.tone)}">${escapeHtml(status.label)}</span></td>
            <td>${escapeHtml(entry.imported_at ?? "")}</td>
            <td>${this.renderRowActions(entry, escapeHtml)}</td>
          </tr>
        `;
      })
      .join("");
  },

  renderStatusCard(label, value, escapeHtml) {
    return `
      <article class="legal-status-card">
        <span class="legal-status-card__label">${escapeHtml(label)}</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(value)}</strong>
      </article>
    `;
  },

  renderScoreTable(host, examScores, averageText, escapeHtml) {
    if (!host) {
      return;
    }

    if (!examScores.length) {
      host.hidden = true;
      host.innerHTML = "";
      return;
    }

    host.hidden = false;
    const scoreRange = this.formatScoreRange(examScores);
    const scores = examScores.map((item) => Number(item?.score)).filter((value) => Number.isFinite(value));
    const failedCount = scores.filter((value) => value < 100).length;
    const exactCount = scores.filter((value) => value >= 100).length;
    const highRiskCount = scores.filter((value) => value < 70).length;

    host.innerHTML = `
      <div class="legal-section__header">
        <div>
          <p class="legal-section__eyebrow">Проверка ответов</p>
          <h3 class="legal-section__title">Сравнение по ключу ${escapeHtml(scoreRange)}</h3>
          <p class="legal-section__description">Средний балл: <strong>${escapeHtml(averageText)}</strong>. Ниже показано сравнение вопроса, ответа, эталона и логики проверки.</p>
        </div>
      </div>
      <div class="exam-score-summary">
        <article class="legal-status-card">
          <span class="legal-status-card__label">Сравнено полей</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(examScores.length))}</strong>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">Без замечаний</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(exactCount))}</strong>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">С замечаниями</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(failedCount))}</strong>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">Критично (<70)</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(highRiskCount))}</strong>
        </article>
      </div>
      <div class="legal-table-shell exam-detail-shell">
        <table class="legal-table">
          <thead>
            <tr>
              <th>Столбец</th>
              <th>Вопрос</th>
              <th>Ответ пользователя</th>
              <th>Правильный ответ</th>
              <th>Ключевые критерии</th>
              <th>Балл</th>
              <th>Пояснение</th>
            </tr>
          </thead>
          <tbody>
            ${examScores
              .map(
                (item) => `
                  <tr>
                    <td>${escapeHtml(item.column || "")}</td>
                    <td>${escapeHtml(item.header || "")}</td>
                    <td>${escapeHtml(item.user_answer || "—")}</td>
                    <td>${escapeHtml(item.correct_answer || "—")}</td>
                    <td>${escapeHtml(Array.isArray(item.key_points) && item.key_points.length ? item.key_points.join("; ") : "—")}</td>
                    <td>${this.renderScoreBadge(item.score, escapeHtml)}</td>
                    <td>${escapeHtml(item.rationale || "—")}</td>
                  </tr>
                `,
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  },

  renderPayloadTable(host, payload, escapeHtml) {
    if (!host) {
      return;
    }

    const rows = Object.entries(payload || {});
    host.innerHTML = rows.length
      ? rows
          .map(
            ([column, value]) => `
              <tr>
                <td>${escapeHtml(column)}</td>
                <td>${escapeHtml(value || "—")}</td>
              </tr>
            `,
          )
          .join("")
      : `
          <tr>
            <td colspan="2" class="legal-table__empty">По этой строке нет сохраненных столбцов.</td>
          </tr>
        `;
  },
};
