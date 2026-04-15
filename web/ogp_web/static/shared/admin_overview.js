function normalizeUtf8MojibakeText(value) {
  const text = String(value ?? "");
  if (!text) {
    return "";
  }
  if (!/[^\x00-\x7f]/.test(text)) {
    return text;
  }
  try {
    const decoded = decodeURIComponent(escape(text));
    if (decoded && decoded !== text) {
      return decoded;
    }
  } catch {
    // keep original when value is already valid UTF-8.
  }
  return text;
}

function createAdminSafeEscaper(escapeHtml) {
  const safeEscapeHtml =
    typeof escapeHtml === "function" ? escapeHtml : (value) => String(value ?? "");

  return (value) => safeEscapeHtml(normalizeUtf8MojibakeText(value));
}

window.OGPAdminOverview = {
  renderTotalsMarkup(totals, helpers = {}) {
    const escapeHtml = createAdminSafeEscaper(helpers.escapeHtml);
    const formatNumber = helpers.formatNumber || ((value) => String(Number(value || 0)));
    const formatUsd = helpers.formatUsd || ((value) => String(Number(value || 0)));
    const items = [
      ["Пользователи", totals.users_total, "Всего аккаунтов в системе"],
      ["API-запросы", totals.api_requests_total, "Накопленная активность API"],
      ["Жалобы", totals.complaints_total, "Сгенерированные жалобы"],
      ["Реабилитации", totals.rehabs_total, "Сгенерированные реабилитации"],
      ["AI suggest", totals.ai_suggest_total, "Текстовые AI-операции"],
      ["AI OCR", totals.ai_ocr_total, "Распознавание документов"],
      ["AI-проверки экзаменов", totals.ai_exam_scoring_total || 0, "Сколько раз запускалась AI-проверка экзаменов"],
      ["Строки экзамена", totals.ai_exam_scoring_rows || 0, "Сколько строк экзамена реально проверено"],
      ["Ответы экзамена", totals.ai_exam_scoring_answers || 0, "Сколько ответов прошло через оценивание"],
      ["Без LLM", totals.ai_exam_heuristic_total || 0, "Ответы, закрытые без обращения к модели"],
      ["Попадания в кэш", totals.ai_exam_cache_total || 0, "Ответы, взятые из кэша"],
      ["Ответы через LLM", totals.ai_exam_llm_total || 0, "Ответы, реально ушедшие в модель"],
      ["Вызовы LLM", totals.ai_exam_llm_calls_total || 0, "Сколько batch-вызовов сделали к модели"],
      ["Ошибки экзамена", totals.ai_exam_failure_total || 0, "Ошибки оценивания экзаменов и импорта"],
      ["Входящий трафик", `${formatNumber(totals.request_bytes_total)} B`, "Суммарный размер запросов"],
      ["Исходящий трафик", `${formatNumber(totals.response_bytes_total)} B`, "Суммарный размер ответов"],
      ["Ресурсные единицы", formatNumber(totals.resource_units_total), "Условная нагрузка"],
      ["AI cost (USD)", `$${formatUsd(totals.ai_estimated_cost_total_usd || 0)}`, `Оценка по ${formatNumber(totals.ai_estimated_cost_samples || 0)} вызовам`],
      ["AI токены (in/out/total)", `${formatNumber(totals.ai_input_tokens_total || 0)} / ${formatNumber(totals.ai_output_tokens_total || 0)} / ${formatNumber(totals.ai_total_tokens_total || 0)}`, `Сумма по ${formatNumber(totals.ai_generation_total || 0)} генерациям`],
      ["Средний API ответ", `${formatNumber(totals.avg_api_duration_ms)} ms`, "Средняя длительность API"],
      ["События за 24 часа", totals.events_last_24h, "Последняя суточная активность"],
    ];

    return items
      .map(
        ([label, value, hint]) => `
          <article class="legal-subcard admin-total-card">
            <div class="legal-field__label">${escapeHtml(label)}</div>
            <div class="legal-section__title">${escapeHtml(String(value))}</div>
            <p class="legal-section__description">${escapeHtml(hint)}</p>
          </article>
        `,
      )
      .join("");
  },

  renderPerformanceMarkup(payload, helpers = {}) {
    const escapeHtml = createAdminSafeEscaper(helpers.escapeHtml);
    const renderBadge = helpers.renderBadge || ((text) => String(text ?? ""));
    const isCached = Boolean(payload?.cached);
    const totals = {
      ...(payload?.totals || {}),
      total_requests: (payload?.totals || {}).total_requests ?? payload?.total_api_requests ?? 0,
      failed_requests: (payload?.totals || {}).failed_requests ?? payload?.error_count ?? 0,
    };
    const latency = {
      ...(payload?.latency || {}),
      p95_ms: (payload?.latency || {}).p95_ms ?? payload?.p95_ms ?? "-",
      p50_ms: (payload?.latency || {}).p50_ms ?? payload?.p50_ms ?? "-",
    };
    const rates = {
      ...(payload?.rates || {}),
      requests_per_second: (payload?.rates || {}).requests_per_second ?? payload?.throughput_rps ?? "-",
    };
    const top = Array.isArray(payload?.top_endpoints)
      ? payload.top_endpoints
      : Array.isArray(payload?.endpoint_overview)
        ? payload.endpoint_overview
        : [];
    const snapshotAt = String(payload?.snapshot_at || payload?.generated_at || "-");

    return `
      <article class="legal-status-card">
        <span class="legal-status-card__label">Снимок</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(snapshotAt)}</strong>
        <span class="admin-user-cell__secondary">${renderBadge(isCached ? "cache" : "live", isCached ? "muted" : "success-soft")}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">p95 / p50 (ms)</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(latency.p95_ms ?? "-"))} / ${escapeHtml(String(latency.p50_ms ?? "-"))}</strong>
        <span class="admin-user-cell__secondary">Ошибок: ${escapeHtml(String(totals.failed_requests ?? 0))} из ${escapeHtml(String(totals.total_requests ?? 0))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">RPS</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(rates.requests_per_second ?? "-"))}</strong>
        <span class="admin-user-cell__secondary">Окно: ${escapeHtml(String(payload?.window_minutes ?? "-"))} мин</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">Топ endpoint</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(top[0]?.path || "-"))}</strong>
        <span class="admin-user-cell__secondary">Запросов: ${escapeHtml(String(top[0]?.count || 0))}</span>
      </article>
    `;
  },

  renderAsyncJobsMarkup(payload, helpers = {}) {
    const escapeHtml = createAdminSafeEscaper(helpers.escapeHtml);
    const renderAsyncJobActions = helpers.renderAsyncJobActions || (() => "");
    const summary = payload?.summary || {};
    const problemJobs = Array.isArray(payload?.problem_jobs) ? payload.problem_jobs : [];
    const byJobType = Array.isArray(payload?.by_job_type) ? payload.by_job_type : [];

    const cards = [
      ["Всего jobs", summary.total_jobs || 0, "Последние server/global async jobs для текущего сервера."],
      ["Проблемные", summary.problem_jobs || 0, "Сумма failed и retry_scheduled jobs."],
      ["Failed", summary.failed_jobs || 0, "Требуют внимания оператора или ручного retry."],
      ["Retry scheduled", summary.retry_scheduled_jobs || 0, "Ожидают автоматической повторной попытки."],
    ];

    const cardsHtml = cards
      .map(
        ([label, value, hint]) => `
          <article class="legal-status-card">
            <span class="legal-status-card__label">${escapeHtml(label)}</span>
            <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(value))}</strong>
            <span class="admin-user-cell__secondary">${escapeHtml(hint)}</span>
          </article>
        `,
      )
      .join("");

    const byTypeHtml = byJobType.length
      ? `<div class="admin-section-toolbar"><span class="admin-user-cell__secondary admin-ops-wrap">By type: ${escapeHtml(byJobType.map((item) => `${item.job_type} (${item.count})`).join(", "))}</span></div>`
      : "";

    const tableHtml = problemJobs.length
      ? `
        <div class="legal-table-shell">
          <table class="legal-table admin-table admin-table--compact">
            <thead><tr><th>ID</th><th>Type</th><th>Status</th><th>Raw</th><th>Next run</th><th>Error</th><th>Actions</th></tr></thead>
            <tbody>
              ${problemJobs
                .map(
                  (item) => `
                    <tr>
                      <td>${escapeHtml(String(item.id || "-"))}</td>
                      <td>${escapeHtml(String(item.job_type || "-"))}</td>
                      <td>${escapeHtml(String(item.canonical_status || "-"))}</td>
                      <td>${escapeHtml(String(item.raw_status || item.status || "-"))}</td>
                      <td>${escapeHtml(String(item.next_run_at || "-"))}</td>
                      <td>${escapeHtml(String(item.last_error_code || item.last_error_message || "-"))}</td>
                      <td>${renderAsyncJobActions(item)}</td>
                    </tr>
                  `,
                )
                .join("")}
            </tbody>
          </table>
        </div>
      `
      : '<p class="legal-section__description">Проблемных async jobs сейчас нет.</p>';

    return `
      <div class="admin-performance-grid">${cardsHtml}</div>
      ${byTypeHtml}
      ${tableHtml}
    `;
  },

  renderLawJobsMarkup(payload, helpers = {}) {
    const escapeHtml = createAdminSafeEscaper(helpers.escapeHtml);
    const summary = payload?.summary || {};
    const alerts = Array.isArray(payload?.alerts) ? payload.alerts : [];
    const running = Array.isArray(payload?.running) ? payload.running : [];

    const cards = [
      ["Всего rebuild tasks", summary.total_tasks || 0, "Все фоновые law rebuild tasks для текущего admin surface."],
      ["Running", summary.running_tasks || 0, "Очередь и активные rebuild tasks."],
      ["Failed", summary.failed_tasks || 0, "Требуют ручной проверки law runtime."],
      ["Alerts", summary.alerts_count || 0, "Сигналы по упавшим rebuild tasks."],
    ];

    const cardsHtml = cards
      .map(
        ([label, value, hint]) => `
          <article class="legal-status-card">
            <span class="legal-status-card__label">${escapeHtml(label)}</span>
            <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(value))}</strong>
            <span class="admin-user-cell__secondary">${escapeHtml(hint)}</span>
          </article>
        `,
      )
      .join("");

    const alertsHtml = alerts.length
      ? `
        <div class="legal-table-shell">
          <table class="legal-table admin-table admin-table--compact">
            <thead><tr><th>Task</th><th>Server</th><th>Error</th></tr></thead>
            <tbody>
              ${alerts
                .map(
                  (item) => `
                    <tr>
                      <td>${escapeHtml(String(item.task_id || "-"))}</td>
                      <td>${escapeHtml(String(item.server_code || "-"))}</td>
                      <td>${escapeHtml(String(item.error || "-"))}</td>
                    </tr>
                  `,
                )
                .join("")}
            </tbody>
          </table>
        </div>
      `
      : '<p class="legal-section__description">Упавших law rebuild tasks сейчас нет.</p>';

    const runningHtml = running.length
      ? `<div class="admin-section-toolbar"><span class="admin-user-cell__secondary admin-ops-wrap">Running: ${escapeHtml(running.map((item) => `${item.task_id} (${item.server_code || "-"})`).join(", "))}</span></div>`
      : "";

    return `
      <div class="admin-performance-grid">${cardsHtml}</div>
      ${runningHtml}
      ${alertsHtml}
    `;
  },

  renderExamImportOpsMarkup(payload, helpers = {}) {
    const escapeHtml = createAdminSafeEscaper(helpers.escapeHtml);
    const summary = payload?.summary || {};
    const failedEntries = Array.isArray(payload?.failed_entries) ? payload.failed_entries : [];
    const recentFailures = Array.isArray(payload?.recent_failures) ? payload.recent_failures : [];
    const recentRowFailures = Array.isArray(payload?.recent_row_failures) ? payload.recent_row_failures : [];

    const cards = [
      ["Pending scores", summary.pending_scores || 0, "Строки, которые ещё ждут scoring."],
      ["Failed entries", summary.failed_entries || 0, "Записи с неуспешной проверкой ответов."],
      ["Import failures", summary.recent_failures || 0, "Недавние ошибки массового импорта или scoring."],
      ["Problem signals", summary.problem_signals || 0, "Суммарный операторский сигнал по exam import."],
    ];

    const cardsHtml = cards
      .map(
        ([label, value, hint]) => `
          <article class="legal-status-card">
            <span class="legal-status-card__label">${escapeHtml(label)}</span>
            <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(value))}</strong>
            <span class="admin-user-cell__secondary">${escapeHtml(hint)}</span>
          </article>
        `,
      )
      .join("");

    const failedEntriesHtml = failedEntries.length
      ? `
        <div class="legal-table-shell">
          <table class="legal-table admin-table admin-table--compact">
            <thead><tr><th>Row</th><th>Name</th><th>Format</th><th>Reason</th></tr></thead>
            <tbody>
              ${failedEntries
                .map(
                  (item) => `
                    <tr>
                      <td>${escapeHtml(String(item.source_row || "-"))}</td>
                      <td>${escapeHtml(String(item.full_name || "-"))}</td>
                      <td>${escapeHtml(String(item.exam_format || "-"))}</td>
                      <td>${escapeHtml(String(item.score_error || item.question_g_rationale || "-"))}</td>
                    </tr>
                  `,
                )
                .join("")}
            </tbody>
          </table>
        </div>
      `
      : '<p class="legal-section__description">Записей с failed scoring сейчас нет.</p>';

    const failureNotes = [...recentFailures, ...recentRowFailures]
      .slice(0, 5)
      .map((item) => {
        if (typeof item === "string") {
          return { source: "raw", kind: "message", detail: item };
        }
        if (item && typeof item === "object") {
          return {
            source: String(item.event_type || item.source || "event"),
            kind: String(item.error_type || item.kind || item.status_code || "signal"),
            detail: String(item.message || item.error || item.detail || item.meta?.error || JSON.stringify(item)),
          };
        }
        return { source: "raw", kind: "message", detail: String(item || "") };
      })
      .filter((item) => item.detail);

    const failureNotesHtml = failureNotes.length
      ? `
        <div class="legal-table-shell">
          <table class="legal-table admin-table admin-table--compact">
            <thead><tr><th>Source</th><th>Kind</th><th>Detail</th></tr></thead>
            <tbody>
              ${failureNotes
                .map(
                  (item) => `
                    <tr>
                      <td>${escapeHtml(String(item.source || "-"))}</td>
                      <td>${escapeHtml(String(item.kind || "-"))}</td>
                      <td>${escapeHtml(String(item.detail || "-"))}</td>
                    </tr>
                  `,
                )
                .join("")}
            </tbody>
          </table>
        </div>
      `
      : "";

    return `
      <div class="admin-performance-grid">${cardsHtml}</div>
      ${failureNotesHtml}
      ${failedEntriesHtml}
    `;
  },

  renderSyntheticMarkup(summary, helpers = {}) {
    const escapeHtml = createAdminSafeEscaper(helpers.escapeHtml);
    const renderBadge = helpers.renderBadge || ((text) => String(text ?? ""));
    const activeSyntheticSuite = String(helpers.activeSyntheticSuite || "");
    const bySuite = summary?.by_suite || {};
    const suites = ["smoke", "nightly", "load", "fault"];
    const suiteDescriptions = {
      smoke: "Быстрая проверка основных сценариев генерации, снапшотов, цитат и публикации.",
      nightly: "Расширенный регрессионный прогон полного workflow, вложений, артефактов и rollback.",
      load: "Нагрузочная проверка burst/sustained сценариев генерации, экспорта и content workflow.",
      fault: "Проверка отказоустойчивости: retry, DLQ, idempotency, isolation и policy gates.",
    };
    const cards = suites.map((suite) => {
      const row = bySuite[suite] || {};
      const latest = String(row.latest_status || "unknown");
      const tone = latest === "pass" ? "success-soft" : latest === "fail" ? "danger-soft" : "muted";
      const isRunning = activeSyntheticSuite === suite;
      return `
        <article class="legal-status-card admin-synthetic-card">
          <span class="legal-status-card__label">${escapeHtml(suite)}</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${renderBadge(latest, tone)}</strong>
          <span class="admin-user-cell__secondary">runs: ${escapeHtml(String(row.runs_total || 0))}, failed: ${escapeHtml(String(row.failed_total || 0))}</span>
          <span class="admin-user-cell__secondary admin-synthetic-card__description">${escapeHtml(suiteDescriptions[suite] || "")}</span>
          <button type="button" class="ghost-button" data-synthetic-run="${suite}" ${isRunning ? "disabled" : ""}>${isRunning ? "Запуск..." : "Запустить"}</button>
        </article>
      `;
    });
    const failedRuns = Array.isArray(summary?.runs)
      ? summary.runs.filter((item) => String(item?.status || "") !== "pass").slice(0, 5)
      : [];
    const failedHtml = failedRuns.length
      ? `<div class="legal-table-wrap"><table class="legal-table"><thead><tr><th>Suite</th><th>Run</th><th>Status</th><th>When</th></tr></thead><tbody>
        ${failedRuns
          .map(
            (item) => `<tr><td>${escapeHtml(String(item.suite || "-"))}</td><td>${escapeHtml(String(item.run_id || "-"))}</td><td>${escapeHtml(String(item.status || "-"))}</td><td>${escapeHtml(String(item.created_at || "-"))}</td></tr>`,
          )
          .join("")}
      </tbody></table></div>`
      : '<p class="legal-section__description">Падений synthetic suite не обнаружено.</p>';

    return `
      <div class="admin-performance-grid admin-synthetic-grid">${cards.join("")}</div>
      ${failedHtml}
    `;
  },

  renderCostSummaryMarkup(totals, helpers = {}) {
    const escapeHtml = createAdminSafeEscaper(helpers.escapeHtml);
    const formatNumber = helpers.formatNumber || ((value) => String(Number(value || 0)));
    const formatUsd = helpers.formatUsd || ((value) => String(Number(value || 0)));
    const samples = Number(totals?.ai_estimated_cost_samples || 0);

    return `
      <article class="legal-status-card">
        <span class="legal-status-card__label">AI cost (USD)</span>
        <strong class="legal-status-card__value legal-status-card__value--small">$${escapeHtml(formatUsd(totals?.ai_estimated_cost_total_usd || 0))}</strong>
        <span class="admin-user-cell__secondary">Сэмплов: ${escapeHtml(String(samples))}</span>
      </article>
      <article class="legal-status-card">
        <span class="legal-status-card__label">AI токены (in/out/total)</span>
        <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatNumber(totals?.ai_input_tokens_total || 0))} / ${escapeHtml(formatNumber(totals?.ai_output_tokens_total || 0))} / ${escapeHtml(formatNumber(totals?.ai_total_tokens_total || 0))}</strong>
        <span class="admin-user-cell__secondary">Генераций: ${escapeHtml(String(totals?.ai_generation_total || 0))}</span>
      </article>
    `;
  },

  renderAiPipelineMarkup(payload, helpers = {}) {
    const escapeHtml = createAdminSafeEscaper(helpers.escapeHtml);
    const renderBandBadge = helpers.renderBandBadge || ((value) => String(value ?? ""));
    const formatUsd = helpers.formatUsd || ((value) => String(Number(value || 0)));
    const formatNumber = helpers.formatNumber || ((value) => String(Number(value || 0)));
    const summary = payload?.summary || {};
    const models = Object.entries(summary?.models || {});
    const feedback = Array.isArray(payload?.feedback) ? payload.feedback.slice(0, 8) : [];
    const quality = payload?.quality_summary || {};
    const flowSummaries = payload?.flow_summaries || {};
    const costTables = payload?.cost_tables || {};
    const topInaccurate = Array.isArray(payload?.top_inaccurate_generations) ? payload.top_inaccurate_generations : [];
    const policyActions = Array.isArray(payload?.policy_actions) ? payload.policy_actions : [];
    const modelCostRows = Array.isArray(costTables?.by_model) ? costTables.by_model : [];
    const flowCostRows = Array.isArray(costTables?.by_flow) ? costTables.by_flow : [];
    const issueCounts = quality?.issue_counts || {};
    const lawQaP95 = flowSummaries?.law_qa?.latency_ms_p95;
    const suggestP95 = flowSummaries?.suggest?.latency_ms_p95;
    const partialErrors = Array.isArray(payload?.partial_errors) ? payload.partial_errors : [];
    const partialErrorsSummary = partialErrors
      .slice(0, 3)
      .map((item) => {
        const source = String(item?.source || "unknown").trim();
        const message = String(item?.message || "Неизвестная ошибка").trim();
        return `${source}: ${message}`;
      })
      .join("; ");
    const formatQualityRate = (value, sampleLabel) => {
      if (value === null || value === undefined) {
        return `n/a (no ${sampleLabel} samples)%`;
      }
      return `${String(value)}%`;
    };

    return `
      ${
        partialErrors.length
          ? `<div class="legal-alert legal-alert--warning">AI Pipeline загружен частично (${escapeHtml(String(partialErrors.length))}). ${escapeHtml(partialErrorsSummary || "Подробности доступны в server logs.")}</div>`
          : ""
      }
      <div class="admin-performance-grid">
        <article class="legal-status-card">
          <span class="legal-status-card__label">Recent generations</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(summary?.total_generations || 0))}</strong>
          <span class="admin-user-cell__secondary">24h sample: ${escapeHtml(String(quality?.generation_samples || 0))}</span>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">Estimated cost</span>
          <strong class="legal-status-card__value legal-status-card__value--small">$${escapeHtml(formatUsd(summary?.estimated_cost_total_usd || 0))}</strong>
          <span class="admin-user-cell__secondary">Samples: ${escapeHtml(String(summary?.estimated_cost_samples || 0))}</span>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">p95 latency</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(String(summary?.latency_ms_p95 ?? "-"))} ms</strong>
          <span class="admin-user-cell__secondary">law_qa: ${escapeHtml(String(lawQaP95 ?? "-"))} / suggest: ${escapeHtml(String(suggestP95 ?? "-"))}</span>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">Fallback rate</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.fallback_rate, "generation"))}</strong>
          <span class="admin-user-cell__secondary">Budget warnings: ${escapeHtml(String(summary?.budget_warning_count || 0))}</span>
        </article>
      </div>
      <div class="admin-performance-grid">
        <article class="legal-status-card">
          <span class="legal-status-card__label">guard_fail_rate</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.guard_fail_rate, "generation"))}</strong>
          <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.guard_fail_rate)}</span>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">guard_warn_rate</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.guard_warn_rate, "generation"))}</strong>
          <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.guard_warn_rate)}</span>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">wrong_law_rate</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.wrong_law_rate, "feedback"))}</strong>
          <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.wrong_law_rate)}</span>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">hallucination_rate</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.hallucination_rate, "feedback"))}</strong>
          <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.hallucination_rate)}</span>
        </article>
      </div>
      <div class="admin-performance-grid">
        <article class="legal-status-card">
          <span class="legal-status-card__label">wrong_fact_rate</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.wrong_fact_rate, "feedback"))}</strong>
          <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.wrong_fact_rate)}</span>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">unclear_answer_rate</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.unclear_answer_rate, "feedback"))}</strong>
          <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.unclear_answer_rate)}</span>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">validation_retry_rate</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.validation_retry_rate, "generation"))}</strong>
          <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.validation_retry_rate)}</span>
        </article>
      </div>
      <div class="admin-performance-grid">
        <article class="legal-status-card">
          <span class="legal-status-card__label">new_fact_validation_rate</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.new_fact_validation_rate, "generation"))}</strong>
          <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.new_fact_validation_rate)}</span>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">unsupported_article_rate</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.unsupported_article_rate, "generation"))}</strong>
          <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.unsupported_article_rate)}</span>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">format_violation_rate</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.format_violation_rate, "generation"))}</strong>
          <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.format_violation_rate)}</span>
        </article>
        <article class="legal-status-card">
          <span class="legal-status-card__label">safe_fallback_rate</span>
          <strong class="legal-status-card__value legal-status-card__value--small">${escapeHtml(formatQualityRate(quality?.safe_fallback_rate, "generation"))}</strong>
          <span class="admin-user-cell__secondary">${renderBandBadge(quality?.bands?.safe_fallback_rate)}</span>
        </article>
      </div>
      <div class="admin-section-toolbar">
        <span class="admin-user-cell__secondary">Models: ${escapeHtml(models.map(([name, count]) => `${name} (${count})`).join(", ") || "no data")}</span>
      </div>
      <div class="legal-field-grid legal-field-grid--two">
        <article class="legal-subcard">
          <div class="legal-field__label">Accuracy taxonomy</div>
          <ul class="legal-list">
            <li>wrong_law: ${escapeHtml(String(issueCounts.wrong_law || 0))}</li>
            <li>wrong_fact: ${escapeHtml(String(issueCounts.wrong_fact || 0))}</li>
            <li>hallucination: ${escapeHtml(String(issueCounts.hallucination || 0))}</li>
            <li>unclear_answer: ${escapeHtml(String(issueCounts.unclear_answer || 0))}</li>
            <li>new_fact_detected: ${escapeHtml(String(issueCounts.new_fact_detected || 0))}</li>
            <li>unsupported_article_reference: ${escapeHtml(String(issueCounts.unsupported_article_reference || 0))}</li>
            <li>format_violation: ${escapeHtml(String(issueCounts.format_violation || 0))}</li>
          </ul>
        </article>
        <article class="legal-subcard">
          <div class="legal-field__label">Policy actions</div>
          <ul class="legal-list">
            ${policyActions.map((item) => `<li>${renderBandBadge(item.severity)} <strong>${escapeHtml(String(item.title || "-"))}</strong>: ${escapeHtml(String(item.reason || "-"))}</li>`).join("")}
          </ul>
        </article>
      </div>
      ${
        modelCostRows.length
          ? `
        <div class="legal-table-shell">
          <table class="legal-table admin-table admin-table--compact">
            <thead><tr><th>Model</th><th>Requests</th><th>Total cost</th><th>Avg cost</th><th>Total tokens</th></tr></thead>
            <tbody>
              ${modelCostRows.map((row) => `
                  <tr>
                    <td>${escapeHtml(String(row.model || "-"))}</td>
                    <td>${escapeHtml(String(row.requests || 0))}</td>
                    <td>$${escapeHtml(formatUsd(row.estimated_cost_total_usd || 0))}</td>
                    <td>$${escapeHtml(formatUsd(row.avg_cost_per_request_usd || 0))}</td>
                    <td>${escapeHtml(formatNumber(row.total_tokens || 0))}</td>
                  </tr>
                `).join("")}
            </tbody>
          </table>
        </div>`
          : ""
      }
      ${
        flowCostRows.length
          ? `
        <div class="legal-table-shell">
          <table class="legal-table admin-table admin-table--compact">
            <thead><tr><th>Flow</th><th>Requests</th><th>Total cost</th><th>Avg cost</th><th>Total tokens</th></tr></thead>
            <tbody>
              ${flowCostRows.map((row) => `
                  <tr>
                    <td>${escapeHtml(String(row.flow || "-"))}</td>
                    <td>${escapeHtml(String(row.requests || 0))}</td>
                    <td>$${escapeHtml(formatUsd(row.estimated_cost_total_usd || 0))}</td>
                    <td>$${escapeHtml(formatUsd(row.avg_cost_per_request_usd || 0))}</td>
                    <td>${escapeHtml(formatNumber(row.total_tokens || 0))}</td>
                  </tr>
                `).join("")}
            </tbody>
          </table>
        </div>`
          : ""
      }
      ${
        topInaccurate.length
          ? `
        <div class="legal-table-shell">
          <table class="legal-table admin-table admin-table--compact">
            <thead><tr><th>generation_id</th><th>Flow</th><th>Issues</th><th>Preview</th><th>Guard</th><th>Note</th></tr></thead>
            <tbody>
              ${topInaccurate.map((row) => `
                  <tr>
                    <td>${escapeHtml(String(row.generation_id || "-"))}</td>
                    <td>${escapeHtml(String(row.flow || "-"))}</td>
                    <td>${escapeHtml(String((row.issues || []).join(", ") || "-"))}</td>
                    <td>${escapeHtml(String(row.output_preview || "-"))}</td>
                    <td>${escapeHtml(String(row.guard_status || "-"))}</td>
                    <td>${escapeHtml(String(row.note || "-"))}</td>
                  </tr>
                `).join("")}
            </tbody>
          </table>
        </div>`
          : '<p class="legal-section__description">No inaccurate generations in the recent sample.</p>'
      }
      ${
        feedback.length
          ? `
        <div class="legal-table-shell">
          <table class="legal-table admin-table admin-table--compact">
            <thead><tr><th>When</th><th>Flow</th><th>Issues</th><th>Comment</th></tr></thead>
            <tbody>
              ${feedback.map((row) => `
                  <tr>
                    <td>${escapeHtml(String(row.created_at || "-"))}</td>
                    <td>${escapeHtml(String((row.meta || {}).flow || "-"))}</td>
                    <td>${escapeHtml(String(((row.meta || {}).issues || []).join(", ") || "-"))}</td>
                    <td>${escapeHtml(String((row.meta || {}).note || "-"))}</td>
                  </tr>
                `).join("")}
            </tbody>
          </table>
        </div>`
          : '<p class="legal-section__description">No feedback items in the recent sample.</p>'
      }
    `;
  },

  renderRoleHistoryMarkup(payload, helpers = {}) {
    const escapeHtml = createAdminSafeEscaper(helpers.escapeHtml);
    const items = Array.isArray(payload?.items) ? payload.items : [];
    if (!items.length) {
      return '<p class="legal-section__description">Изменений ролей пока нет.</p>';
    }

    return `
      <div class="legal-table-shell">
        <table class="legal-table admin-table admin-table--compact">
          <thead><tr><th>Когда</th><th>Админ</th><th>Действие</th><th>Пользователь</th></tr></thead>
          <tbody>
            ${items
              .slice(0, 20)
              .map(
                (item) => `
                <tr>
                  <td>${escapeHtml(String(item.created_at || "-"))}</td>
                  <td>${escapeHtml(String(item.username || "-"))}</td>
                  <td>${escapeHtml(String(item.event_type || "-"))}</td>
                  <td>${escapeHtml(String((item.meta || {}).target_username || "-"))}</td>
                </tr>
              `,
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  },

  renderTopEndpointsMarkup(items, helpers = {}) {
    const escapeHtml = createAdminSafeEscaper(helpers.escapeHtml);
    const describeApiPath = helpers.describeApiPath || ((path) => String(path ?? ""));
    if (!items.length) {
      return '<p class="legal-section__description">Пока нет данных по API-запросам.</p>';
    }

    return `
      <div class="legal-table-shell">
        <table class="legal-table admin-table admin-table--compact">
          <thead><tr><th>Эндпоинт</th><th>Что делает</th><th>Запросов</th></tr></thead>
          <tbody>
            ${items
              .map(
                (item) => `
                  <tr>
                    <td class="admin-table__path" title="${escapeHtml(item.path || "-")}">${escapeHtml(item.path || "-")}</td>
                    <td>${escapeHtml(describeApiPath(item.path || ""))}</td>
                    <td>${escapeHtml(String(item.count || 0))}</td>
                  </tr>
                `,
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  },
};
