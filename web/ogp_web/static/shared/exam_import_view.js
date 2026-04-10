window.OGPExamImportView = {
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
        <td colspan="10" class="legal-table__empty">База пока пустая. Первый импорт создаст записи из Google Sheets.</td>
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
      .map(
        (entry) => `
          <tr data-source-row="${escapeHtml(entry.source_row ?? "")}">
            <td>${escapeHtml(entry.source_row ?? "")}</td>
            <td>${escapeHtml(entry.submitted_at ?? "")}</td>
            <td>${escapeHtml(entry.full_name ?? "")}</td>
            <td>${escapeHtml(entry.discord_tag ?? "")}</td>
            <td>${escapeHtml(entry.passport ?? "")}</td>
            <td>${escapeHtml(entry.exam_format ?? "")}</td>
            <td>${escapeHtml(entry.answer_count ?? 0)}</td>
            <td class="exam-average-cell">${escapeHtml(this.formatAverage(entry))}</td>
            <td>${escapeHtml(entry.imported_at ?? "")}</td>
            <td>${this.renderRowActions(entry, escapeHtml)}</td>
          </tr>
        `,
      )
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
    host.innerHTML = `
      <div class="legal-section__header">
        <div>
          <p class="legal-section__eyebrow">Проверка ответов</p>
          <h3 class="legal-section__title">Сравнение по ключу F–AC</h3>
          <p class="legal-section__description">Средний балл: <strong>${escapeHtml(averageText)}</strong>. Ниже показаны ответы пользователя, правильные ответы и оценка по смысловому совпадению.</p>
        </div>
      </div>
      <div class="legal-table-shell exam-detail-shell">
        <table class="legal-table">
          <thead>
            <tr>
              <th>Столбец</th>
              <th>Вопрос</th>
              <th>Ответ пользователя</th>
              <th>Правильный ответ</th>
              <th>Балл</th>
              <th>Пояснение</th>
            </tr>
          </thead>
          <tbody>
            ${examScores
              .map(
                (item) => `
                  <tr>
                    <td>${escapeHtml(item.column)}</td>
                    <td>${escapeHtml(item.header)}</td>
                    <td>${escapeHtml(item.user_answer || "—")}</td>
                    <td>${escapeHtml(item.correct_answer || "—")}</td>
                    <td>${escapeHtml(item.score ?? "—")}</td>
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
