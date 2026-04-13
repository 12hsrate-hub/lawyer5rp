window.OGPExamImportView = {
  normalizePayloadText(value) {
    if (value == null) {
      return "";
    }
    const technicalEmpty = /^(?:null|undefined|none|nan|n\/a|#n\/a|—|-)?$/i;
    return String(value)
      .replace(/\r/g, "")
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line && !technicalEmpty.test(line))
      .join(" ");
  },

  getEntryStatus(entry) {
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

  getScoreTone(score) {
    const value = Number(score);
    if (!Number.isFinite(value)) {
      return "pending";
    }
    if (value >= 73) {
      return "ok";
    }
    if (value > 55) {
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
    const goodCount = scores.filter((value) => value >= 73).length;
    const mediumCount = scores.filter((value) => value > 55 && value < 73).length;
    const poorCount = scores.filter((value) => value <= 55).length;

    host.innerHTML = `
      <div class="legal-section__header">
        <div>
          <p class="legal-section__eyebrow">Проверка ответов</p>
          <h3 class="legal-section__title">Сравнение по ключу ${escapeHtml(scoreRange)}</h3>
          <p class="legal-section__description">Средний балл: <strong>${escapeHtml(averageText)}</strong>. Ниже собраны вопрос, ответ кандидата, эталон и пояснение по оценке.</p>
        </div>
      </div>
      <div class="exam-score-summary">
        <article class="legal-status-card">
          <span class="legal-status-card__label">Сравнено полей</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(examScores.length))}</strong>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">Хороший уровень</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(goodCount))}</strong>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">Средний уровень</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(mediumCount))}</strong>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">Слабый уровень</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(poorCount))}</strong>
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

    const rows = Object.entries(payload || {})
      .map(([column, value]) => ({
        column: String(column || "").trim(),
        value: this.normalizePayloadText(value),
      }))
      .filter((item) => item.column && item.value);
    host.innerHTML = rows.length
      ? rows
          .map(
            ({ column, value }) => `
              <tr>
                <td>${escapeHtml(column)}</td>
                <td>${escapeHtml(value)}</td>
              </tr>
            `,
          )
          .join("")
      : `
          <tr>
            <td colspan="2" class="legal-table__empty">Нет полезных данных для отображения.</td>
          </tr>
        `;
  },
};
