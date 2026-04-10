const importButton = document.getElementById("exam-import-btn");
const scoreButton = document.getElementById("exam-score-btn");
const rescoreFailedButton = document.getElementById("exam-rescore-failed-btn");
const progressBox = document.getElementById("exam-import-progress");
const progressText = document.getElementById("exam-import-progress-text");
const progressHint = document.getElementById("exam-import-progress-hint");
const messageBox = document.getElementById("exam-import-message");
const errorBox = document.getElementById("exam-import-errors");
const totalRowsValue = document.getElementById("exam-total-rows");
const dbCountValue = document.getElementById("exam-db-count");
const lastImportedValue = document.getElementById("exam-last-imported");
const lastDeltaValue = document.getElementById("exam-last-delta");
const lastScoredValue = document.getElementById("exam-last-scored");
const rowsHost = document.getElementById("exam-import-rows");
const logoutBtn = document.getElementById("logout-btn");
const detailMeta = document.getElementById("exam-detail-meta");
const detailBody = document.getElementById("exam-detail-body");
const detailScore = document.getElementById("exam-detail-score");

const {
  apiFetch,
  parsePayload,
  showText,
  clearText,
  createModalController,
  escapeHtml,
  redirectIfUnauthorized,
} = window.OGPWeb;
const { showOptionalText, bindLogout } = window.OGPPage;
const ExamView = window.OGPExamImportView;

const detailModal = createModalController({
  modal: document.getElementById("exam-detail-modal"),
});

const ACTIVE_TASK_STORAGE_KEY = "ogp_exam_import_active_task";

let progressHintTimer = null;
let progressElapsedTimer = null;
let progressStartedAt = 0;
let progressBaseText = "";

function showErrors(lines) {
  showText(errorBox, lines);
}

function clearErrors() {
  clearText(errorBox);
}

function showMessage(text) {
  showOptionalText(messageBox, text);
}

function saveActiveTask(task) {
  try {
    if (!task?.task_id) {
      window.localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(
      ACTIVE_TASK_STORAGE_KEY,
      JSON.stringify({
        task_id: String(task.task_id),
        task_type: String(task.task_type || ""),
        source_row: task.source_row ?? null,
      }),
    );
  } catch {
    // Ignore storage failures.
  }
}

function loadActiveTask() {
  try {
    const raw = window.localStorage.getItem(ACTIVE_TASK_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed?.task_id) {
      window.localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    window.localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
    return null;
  }
}

function clearActiveTask() {
  try {
    window.localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
  } catch {
    // Ignore storage failures.
  }
}

function formatElapsedLabel(startedAt) {
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  if (elapsedSeconds < 60) {
    return `${elapsedSeconds} сек`;
  }
  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = elapsedSeconds % 60;
  return `${minutes} мин ${seconds.toString().padStart(2, "0")} сек`;
}

function updateProgressText() {
  if (!progressText) {
    return;
  }
  if (!progressStartedAt || !progressBaseText) {
    progressText.textContent = progressBaseText || "";
    return;
  }
  progressText.textContent = `${progressBaseText} (${formatElapsedLabel(progressStartedAt)})`;
}

function updateBusyText(text) {
  progressBaseText = text || "";
  updateProgressText();
}

function formatErrorMessage(error, fallbackText) {
  const raw = String(error?.message || fallbackText || "").trim();
  const lowered = raw.toLowerCase();
  if (!raw) {
    return fallbackText;
  }
  if (lowered.includes("failed to fetch")) {
    return "Сервер не ответил. Проверьте подключение и попробуйте еще раз.";
  }
  if (lowered.includes("gateway timeout") || lowered.includes("504") || lowered.includes("timed out")) {
    return "Проверка заняла слишком много времени. Сервер работает, попробуйте повторить запрос еще раз.";
  }
  if (lowered.includes("403") && lowered.includes("openai")) {
    return "OpenAI временно отклонил запрос. Попробуйте повторить проверку чуть позже.";
  }
  if (lowered.includes("api key")) {
    return "На сервере возникла проблема с настройкой OpenAI API key.";
  }
  return raw;
}

function setBusy(isBusy, text = "", options = {}) {
  const { longRunning = false } = options;
  [importButton, scoreButton, rescoreFailedButton].filter(Boolean).forEach((button) => {
    button.disabled = isBusy;
  });

  if (progressBox) {
    progressBox.hidden = !isBusy;
  }

  if (progressText) {
    progressBaseText = isBusy ? text : "";
    progressStartedAt = isBusy ? Date.now() : 0;
    updateProgressText();
  }

  if (progressElapsedTimer) {
    window.clearInterval(progressElapsedTimer);
    progressElapsedTimer = null;
  }
  if (isBusy) {
    progressElapsedTimer = window.setInterval(updateProgressText, 1000);
  }

  if (progressHintTimer) {
    window.clearTimeout(progressHintTimer);
    progressHintTimer = null;
  }

  if (progressHint) {
    progressHint.hidden = true;
  }

  if (isBusy && longRunning && progressHint) {
    progressHintTimer = window.setTimeout(() => {
      progressHint.hidden = false;
    }, 2500);
  }
}

function renderRows(entries) {
  ExamView.renderRows(rowsHost, entries, escapeHtml);
}

function applySummary(payload) {
  const totalRows = String(payload.total_rows ?? 0);
  if (totalRowsValue) {
    totalRowsValue.textContent = totalRows;
  }
  if (dbCountValue) {
    dbCountValue.textContent = totalRows;
  }
  if (lastImportedValue) {
    lastImportedValue.textContent = String(payload.imported_count ?? 0);
  }
  if (lastDeltaValue) {
    lastDeltaValue.textContent = `${payload.inserted_count ?? 0} / ${payload.skipped_count ?? 0}`;
  }
  if (lastScoredValue) {
    lastScoredValue.textContent = String(payload.scored_count ?? 0);
  }
  renderRows(payload.latest_entries || []);
}

function renderDetail(entry) {
  if (!detailMeta || !detailBody || !detailScore) {
    return;
  }

  detailMeta.innerHTML = [
    ExamView.renderStatusCard("Строка", entry.source_row ?? "", escapeHtml),
    ExamView.renderStatusCard("Имя", entry.full_name ?? "", escapeHtml),
    ExamView.renderStatusCard("Формат", entry.exam_format ?? "", escapeHtml),
    ExamView.renderStatusCard("Средний балл", ExamView.formatAverage(entry), escapeHtml),
  ].join("");

  ExamView.renderScoreTable(detailScore, entry.exam_scores || [], ExamView.formatAverage(entry), escapeHtml);
  ExamView.renderPayloadTable(detailBody, entry.payload || {}, escapeHtml);
}

function updateRowAverage(sourceRow, averageText) {
  const row = rowsHost?.querySelector(`tr[data-source-row="${sourceRow}"]`);
  const averageCell = row?.querySelector(".exam-average-cell");
  if (averageCell) {
    averageCell.textContent = averageText;
  }
  const actionsCell = row?.lastElementChild;
  if (actionsCell) {
    actionsCell.innerHTML = `
      <div class="legal-inline-actions">
        <button type="button" class="ghost-button exam-detail-btn" data-source-row="${escapeHtml(sourceRow)}">Открыть</button>
      </div>
    `;
  }
}

async function requestJson(url, errorText, options = { method: "GET" }) {
  const response = await apiFetch(url, options);
  const payload = await parsePayload(response);
  if (!response.ok) {
    redirectIfUnauthorized(response.status);
    throw new Error(payload.detail || errorText);
  }
  return payload;
}

function describeTaskStatus(task) {
  const progress = task?.progress || null;
  const progressLine = progress && Number.isFinite(Number(progress.total_count))
    ? `Обработано ${Number(progress.processed_count || 0)} из ${Number(progress.total_count || 0)}, осталось ${Number(progress.remaining_count || 0)}`
    : "";

  if (task?.status === "queued") {
    return "Задача поставлена в очередь, начинаю AI-проверку...";
  }
  if (task?.task_type === "row_score" && task?.source_row) {
    return `Проверяю строку ${task.source_row}. AI-оценка может занять до нескольких минут...`;
  }
  if (task?.task_type === "bulk_rescore_failed") {
    return progressLine
      ? `Перепроверяю строки с некорректными результатами. ${progressLine}.`
      : "Перепроверяю только строки с некорректными результатами. Некорректная запись здесь означает строку с непроверенными полями или запись, помеченную как требующую повторной проверки.";
  }
  return progressLine
    ? `Проверяю строки без финальной оценки. ${progressLine}.`
    : "Проверяю только те тесты, у которых еще нет финальной оценки. Для некорректных записей используйте отдельную кнопку перепроверки.";
}

async function pollTaskUntilFinished(taskId, errorText) {
  while (true) {
    const task = await requestJson(`/api/exam-import/tasks/${encodeURIComponent(taskId)}`, errorText);
    updateBusyText(describeTaskStatus(task));
    if (task.status === "completed") {
      clearActiveTask();
      return task.result || {};
    }
    if (task.status === "failed") {
      clearActiveTask();
      throw new Error(task.error || errorText);
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
  }
}

async function openDetail(sourceRow) {
  const normalizedSourceRow = Number(sourceRow);
  if (!Number.isFinite(normalizedSourceRow) || normalizedSourceRow <= 0) {
    showErrors("Не удалось определить строку для просмотра.");
    return;
  }

  clearErrors();
  try {
    const payload = await requestJson(`/api/exam-import/rows/${sourceRow}`, "Не удалось загрузить данные строки.");
    renderDetail(payload);
    detailModal.open();
  } catch (error) {
    showErrors(error?.message || "Не удалось загрузить данные строки.");
  }
}

async function runRowScoring(sourceRow) {
  clearErrors();
  showMessage("");
  setBusy(true, `Проверяю строку ${sourceRow}. AI-оценка может занять до нескольких минут...`, {
    longRunning: true,
  });

  try {
    const task = await requestJson(
      `/api/exam-import/rows/${sourceRow}/score/tasks`,
      "Не удалось проверить выбранную строку.",
      { method: "POST", body: JSON.stringify({}) },
    );
    saveActiveTask(task);
    const payload = await pollTaskUntilFinished(task.task_id, "Не удалось проверить выбранную строку.");
    updateRowAverage(sourceRow, ExamView.formatAverage(payload));
    renderDetail(payload);
    detailModal.open();
    const failedCount = Array.isArray(payload.failed_fields) ? payload.failed_fields.length : 0;
    showMessage(
      failedCount
        ? `Строка ${sourceRow} проверена. Полей, не прошедших проверку: ${failedCount}.`
        : `Строка ${sourceRow} проверена.`,
    );
  } catch (error) {
    clearActiveTask();
    showErrors(formatErrorMessage(error, "Не удалось проверить выбранную строку."));
  } finally {
    setBusy(false);
  }
}

async function runImport() {
  clearErrors();
  showMessage("");
  setBusy(true, "Читаю Google Sheets и добавляю только новые строки...");

  try {
    const payload = await requestJson(
      "/api/exam-import/sync",
      "Не удалось импортировать ответы из Google Sheets.",
      { method: "POST", body: JSON.stringify({}) },
    );
    applySummary(payload);
    showMessage(
      `Импорт завершен: добавлено ${payload.inserted_count ?? 0}, пропущено как уже существующие ${payload.skipped_count ?? 0}, всего прочитано ${payload.imported_count ?? 0} строк.`,
    );
  } catch (error) {
    showErrors(formatErrorMessage(error, "Не удалось импортировать ответы из Google Sheets."));
  } finally {
    setBusy(false);
  }
}

async function runScoring() {
  clearErrors();
  showMessage("");
  setBusy(true, "Проверяю только те тесты, у которых еще нет оценок. Это может занять до нескольких минут...", {
    longRunning: true,
  });

  try {
    const task = await requestJson(
      "/api/exam-import/score/tasks",
      "Не удалось проверить тесты.",
      { method: "POST", body: JSON.stringify({}) },
    );
    saveActiveTask(task);
    const payload = await pollTaskUntilFinished(task.task_id, "Не удалось проверить тесты.");
    applySummary(payload);
    const failedFieldCount = Number(payload.failed_field_count ?? 0);
    const failedRowCount = Array.isArray(payload.failed_rows) ? payload.failed_rows.length : 0;
    showMessage(
      failedFieldCount
        ? `Проверка завершена: оценено ${payload.scored_count ?? 0} тестов. Строк с непроверенными полями: ${failedRowCount}, всего таких полей: ${failedFieldCount}.`
        : `Проверка завершена: оценено ${payload.scored_count ?? 0} тестов.`,
    );
  } catch (error) {
    clearActiveTask();
    showErrors(formatErrorMessage(error, "Не удалось проверить тесты."));
  } finally {
    setBusy(false);
  }
}

async function runRescoreFailed() {
  clearErrors();
  showMessage("");
  setBusy(true, "Перепроверяю строки с непроверенными полями. Старые оценки будут проигнорированы, и запросы уйдут на повторную AI-проверку...", {
    longRunning: true,
  });

  try {
    const task = await requestJson(
      "/api/exam-import/rescore-failed/tasks",
      "Не удалось запустить перепроверку некорректных ответов.",
      { method: "POST", body: JSON.stringify({}) },
    );
    saveActiveTask(task);
    const payload = await pollTaskUntilFinished(task.task_id, "Не удалось перепроверить некорректные ответы.");
    applySummary(payload);
    const failedFieldCount = Number(payload.failed_field_count ?? 0);
    const failedRowCount = Array.isArray(payload.failed_rows) ? payload.failed_rows.length : 0;
    showMessage(
      failedFieldCount
        ? `Перепроверка завершена: переоценено ${payload.rescored_failed_count ?? payload.scored_count ?? 0} строк. Строк с непроверенными полями осталось: ${failedRowCount}, всего таких полей: ${failedFieldCount}.`
        : "Перепроверка завершена: некорректных полей больше нет.",
    );
  } catch (error) {
    clearActiveTask();
    showErrors(formatErrorMessage(error, "Не удалось перепроверить некорректные ответы."));
  } finally {
    setBusy(false);
  }
}

async function resumeActiveTask() {
  const activeTask = loadActiveTask();
  if (!activeTask?.task_id) {
    return;
  }

  clearErrors();
  showMessage("");
  setBusy(true, describeTaskStatus(activeTask), { longRunning: true });

  try {
    const payload = await pollTaskUntilFinished(activeTask.task_id, "Не удалось завершить фоновую проверку.");
    applySummary(payload);

    if (activeTask.task_type === "row_score" && activeTask.source_row) {
      updateRowAverage(activeTask.source_row, ExamView.formatAverage(payload));
      renderDetail(payload);
      detailModal.open();
      const failedCount = Array.isArray(payload.failed_fields) ? payload.failed_fields.length : 0;
      showMessage(
        failedCount
          ? `Строка ${activeTask.source_row} проверена. Полей, не прошедших проверку: ${failedCount}.`
          : `Строка ${activeTask.source_row} проверена.`,
      );
      return;
    }

    if (activeTask.task_type === "bulk_rescore_failed") {
      const failedFieldCount = Number(payload.failed_field_count ?? 0);
      const failedRowCount = Array.isArray(payload.failed_rows) ? payload.failed_rows.length : 0;
      showMessage(
        failedFieldCount
          ? `Перепроверка завершена: переоценено ${payload.rescored_failed_count ?? payload.scored_count ?? 0} строк. Строк с непроверенными полями осталось: ${failedRowCount}, всего таких полей: ${failedFieldCount}.`
          : "Перепроверка завершена: некорректных полей больше нет.",
      );
      return;
    }

    const failedFieldCount = Number(payload.failed_field_count ?? 0);
    const failedRowCount = Array.isArray(payload.failed_rows) ? payload.failed_rows.length : 0;
    showMessage(
      failedFieldCount
        ? `Проверка завершена: оценено ${payload.scored_count ?? 0} тестов. Строк с непроверенными полями: ${failedRowCount}, всего таких полей: ${failedFieldCount}.`
        : `Проверка завершена: оценено ${payload.scored_count ?? 0} тестов.`,
    );
  } catch (error) {
    clearActiveTask();
    showErrors(formatErrorMessage(error, "Не удалось завершить фоновую проверку."));
  } finally {
    setBusy(false);
  }
}

importButton?.addEventListener("click", runImport);
scoreButton?.addEventListener("click", runScoring);
rescoreFailedButton?.addEventListener("click", runRescoreFailed);

rowsHost?.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) {
    return;
  }

  const rowScoreButton = target.closest(".exam-score-row-btn");
  if (rowScoreButton) {
    runRowScoring(rowScoreButton.dataset.sourceRow);
    return;
  }

  const detailButton = target.closest(".exam-detail-btn");
  if (detailButton) {
    openDetail(detailButton.dataset.sourceRow);
  }
});

detailModal.bind(document.getElementById("exam-detail-close"), document.getElementById("exam-detail-ok"));

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    detailModal.close();
  }
});

bindLogout(logoutBtn);
resumeActiveTask();
