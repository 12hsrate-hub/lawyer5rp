const form = document.getElementById("complaint-form");
const result = document.getElementById("result");
const errors = document.getElementById("errors");
const copyBtn = document.getElementById("copy-btn");
const generateBbcodeBtn = document.getElementById("generate-bbcode-btn");
const saveDraftBtn = document.getElementById("save-draft-btn");
const resetDraftBtn = document.getElementById("reset-draft-btn");
const template = document.getElementById("url-field-template");
const aiBtn = document.getElementById("ai-btn");
const aiErrors = document.getElementById("ai-errors");
const aiStatus = document.getElementById("ai-status");
const aiStatusText = document.getElementById("ai-status-text");
const bbcodeStatus = document.getElementById("bbcode-status");
const bbcodeStatusText = document.getElementById("bbcode-status-text");
const logoutBtn = document.getElementById("logout-btn");
const appMessage = document.getElementById("app-message");
const presetScript = document.getElementById("complaint-preset");
const complaintOcrFile = document.getElementById("complaint-ocr-file");
const complaintOcrBtn = document.getElementById("complaint-ocr-btn");
const complaintOcrStatus = document.getElementById("complaint-ocr-status");
const complaintOcrProgress = document.getElementById("complaint-ocr-progress");
const complaintOcrProgressText = document.getElementById("complaint-ocr-progress-text");
const complaintOcrFileName = document.getElementById("complaint-ocr-file-name");
const eventDateField = document.getElementById("event-date");
const eventTimeField = document.getElementById("event-time");
const eventDateTimeField = document.getElementById("event-dt");
const complaintBasisField = document.getElementById("complaint-basis");
const mainFocusField = document.getElementById("main-focus");
const aiFocusHint = document.getElementById("ai-focus-hint");
const complaintProgressText = document.getElementById("complaint-progress-text");
const complaintProgressBar = document.getElementById("complaint-progress-bar");
const complaintProgressHost = document.querySelector(".legal-form-progress");

const {
  apiFetch,
  parsePayload,
  setStateError,
  setStateIdle,
  setStateSuccess,
  redirectIfUnauthorized,
  createModalController,
} = window.OGPWeb;
const { wireSingleUsePrincipalOcr, bindFilePickerLabel, createUiResetter } = window.OGPOcr;
const { bindLogout } = window.OGPPage;
const { parseJsonScript, bindDigitsOnly, bindDynamicAddButtons, addDynamicField, setCurrentDate, setFieldValue } =
  window.OGPForm;
const { createPresetState, applyState, collectDraftState, buildPayload } = window.OGPComplaintPayload;

const LEGACY_DRAFT_STORAGE_KEY = "ogp_web_complaint_draft_v1";
const draftOwner = (form?.dataset?.username || "anonymous").trim().toLowerCase();
const DRAFT_STORAGE_KEY = `ogp_web_complaint_draft_v2_${draftOwner || "anonymous"}`;

const OCR_TEXT = {
  emptyFileName: "Файл не выбран",
  readyStatus: "Статус: ожидает изображение.",
  noFileStatus: "Статус: сначала приложите 4-ю страницу договора.",
  noFileError: "Сначала выберите изображение 4-й страницы договора.",
  processingStatus: "Статус: изображение загружено, идет распознавание.",
  busyText: "Распознаю данные доверителя по 4-й странице договора...",
  successStatus: "Статус: данные найдены и подставлены в поля.",
  failureStatus: "Статус: распознавание завершилось с ошибкой.",
  exceptionStatus: "Статус: не удалось обработать изображение.",
  fallbackErrorText: "Не удалось распознать данные доверителя.",
  successModal:
    "Данные доверителя подставлены автоматически. Обязательно проверьте ФИО, паспорт, адрес, телефон и Discord перед отправкой жалобы.",
};

const presetPayload = parseJsonScript(presetScript);
const isDraftEnabled = !presetPayload && Boolean(resetDraftBtn);

let pendingAiText = "";
let draftSaveTimer = 0;
let lastSavedDraft = "";
let remoteDraftSaveTimer = 0;
let lastRemoteDraft = "";
let isApplyingComplaintState = false;

const AI_FOCUS_HINTS = {
  wrongful_article:
    "Укажи, в чем именно спорность квалификации: не та статья, не было оснований, статья не подтверждается фактами.",
  no_materials_by_request:
    "Коротко укажи, какие материалы истребовали и что именно не предоставили по официальному адвокатскому запросу.",
  no_video_or_no_evidence:
    "Коротко укажи, видео отсутствует полностью, не выдано или не подтверждает ключевые обстоятельства.",
};

const aiModal = createModalController({
  modal: document.getElementById("ai-modal"),
  textHost: document.getElementById("ai-modal-text"),
});
const complaintOcrModal = createModalController({
  modal: document.getElementById("complaint-ocr-modal"),
  textHost: document.getElementById("complaint-ocr-modal-text"),
});
const complaintFileErrorModal = createModalController({
  modal: document.getElementById("complaint-file-error-modal"),
  textHost: document.getElementById("complaint-file-error-text"),
});

const complaintFilePicker = bindFilePickerLabel({
  fileInput: complaintOcrFile,
  nameHost: complaintOcrFileName,
  emptyText: OCR_TEXT.emptyFileName,
});

const resetComplaintOcrUi = createUiResetter({
  fileInput: complaintOcrFile,
  progressHost: complaintOcrProgress,
  progressTextHost: complaintOcrProgressText,
  statusHost: complaintOcrStatus,
  readyStatus: OCR_TEXT.readyStatus,
  closeModal: () => {
    complaintOcrModal.close();
    complaintFileErrorModal.close();
  },
  filePicker: complaintFilePicker,
});

function syncComplaintOcrButtonState() {
  if (!complaintOcrBtn || !complaintOcrFile) {
    return;
  }
  const hasFile = Boolean((complaintOcrFile.files || [])[0]);
  complaintOcrBtn.disabled = !hasFile;
}

complaintOcrFile?.addEventListener("change", syncComplaintOcrButtonState);
complaintOcrFile?.addEventListener("click", () => {
  window.setTimeout(syncComplaintOcrButtonState, 0);
});
syncComplaintOcrButtonState();

function showErrors(lines) {
  setStateError(errors, Array.isArray(lines) ? lines.join("\n") : String(lines || ""));
}

function clearErrors() {
  setStateIdle(errors);
}

function showAiErrors(lines) {
  setStateError(aiErrors, Array.isArray(lines) ? lines.join("\n") : String(lines || ""));
}

function clearAiErrors() {
  setStateIdle(aiErrors);
}

function setAiBusy(isBusy, text = "") {
  aiBtn.disabled = isBusy;
  aiStatus.hidden = !isBusy;
  aiStatusText.textContent = isBusy ? text : "";
}

function setBbcodeBusy(isBusy, text = "") {
  if (generateBbcodeBtn) {
    generateBbcodeBtn.disabled = isBusy;
  }
  if (bbcodeStatus) {
    bbcodeStatus.hidden = false;
  }
  if (bbcodeStatusText) {
    bbcodeStatusText.textContent = text || "Статус: готово к формированию BBCode.";
  }
  const spinner = bbcodeStatus?.querySelector(".spinner");
  if (spinner) {
    spinner.hidden = !isBusy;
  }
}

function showAppMessage(text) {
  if (!text) {
    setStateIdle(appMessage);
    return;
  }
  setStateSuccess(appMessage, text);
}

function scrollToErrors() {
  errors?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

function setAiFocusHint() {
  if (!aiFocusHint) {
    return;
  }
  const basis = complaintBasisField?.value || "";
  const fallback = mainFocusField?.value?.trim()
    ? "Акцент понятен. Сохраняй его коротким и привязанным к конкретным фактам."
    : "";
  const hint = AI_FOCUS_HINTS[basis] || fallback;
  aiFocusHint.hidden = !hint;
  aiFocusHint.textContent = hint;
}

function syncDateTimeInputsFromHidden() {
  const value = (eventDateTimeField?.value || "").trim();
  if (!eventDateField || !eventTimeField) {
    return;
  }
  if (!value) {
    eventDateField.value = "";
    eventTimeField.value = "";
    return;
  }
  if (value.includes("T")) {
    const [datePart, timePart = ""] = value.split("T");
    eventDateField.value = datePart;
    eventTimeField.value = timePart.slice(0, 5);
    return;
  }

  const match = value.match(/^(\d{2})\.(\d{2})\.(\d{4}) (\d{2}:\d{2})$/);
  if (!match) {
    eventDateField.value = "";
    eventTimeField.value = "";
    return;
  }

  const [, day, month, year, time] = match;
  eventDateField.value = `${year}-${month}-${day}`;
  eventTimeField.value = time;
}

function syncEventDateTimeField() {
  if (!eventDateTimeField) {
    return;
  }
  const dateValue = eventDateField?.value || "";
  const timeValue = eventTimeField?.value || "";
  eventDateTimeField.value = dateValue && timeValue ? `${dateValue}T${timeValue}` : "";
}

function updateRequiredProgress() {
  if (!form || !complaintProgressText || !complaintProgressBar) {
    return;
  }

  const requiredFields = [...form.querySelectorAll("[required]")]
    .filter((field) => field instanceof HTMLElement)
    .filter((field) => field.type !== "hidden");

  if (!requiredFields.length) {
    complaintProgressText.textContent = "Обязательные поля: 0/0";
    complaintProgressBar.style.width = "0%";
    complaintProgressHost?.setAttribute("aria-valuenow", "0");
    return;
  }

  const filled = requiredFields.filter((field) => {
    if (field instanceof HTMLInputElement && field.type === "checkbox") {
      return field.checked;
    }
    return String(field.value || "").trim() !== "";
  }).length;

  const percent = Math.round((filled / requiredFields.length) * 100);
  complaintProgressText.textContent = `Обязательные поля: ${filled}/${requiredFields.length}`;
  complaintProgressBar.style.width = `${percent}%`;
  complaintProgressHost?.setAttribute("aria-valuenow", String(percent));
}

function persistDraft() {
  if (!isDraftEnabled) {
    return;
  }
  const serialized = JSON.stringify(collectDraftState({ form, resultHost: result }));
  if (serialized === lastSavedDraft) {
    return;
  }
  window.localStorage.setItem(DRAFT_STORAGE_KEY, serialized);
  lastSavedDraft = serialized;
}

function hasMeaningfulDraft(state) {
  if (!state || typeof state !== "object") {
    return false;
  }
  return Object.entries(state).some(([key, value]) => {
    if (key === "today_date" || key === "result") {
      return false;
    }
    if (Array.isArray(value)) {
      return value.some((item) => String(item || "").trim());
    }
    return String(value || "").trim() !== "";
  });
}

function scheduleDraftSave() {
  if (!isDraftEnabled || isApplyingComplaintState) {
    return;
  }
  window.clearTimeout(draftSaveTimer);
  draftSaveTimer = window.setTimeout(() => {
    draftSaveTimer = 0;
    persistDraft();
  }, 180);
}

function scheduleRemoteDraftSave() {
  if (!isDraftEnabled || isApplyingComplaintState) {
    return;
  }
  window.clearTimeout(remoteDraftSaveTimer);
  remoteDraftSaveTimer = window.setTimeout(async () => {
    remoteDraftSaveTimer = 0;
    await saveRemoteDraft(false);
  }, 1200);
}

function loadDraft() {
  if (!isDraftEnabled) {
    return null;
  }
  try {
    let serialized = window.localStorage.getItem(DRAFT_STORAGE_KEY) || "";
    if (!serialized) {
      serialized = window.localStorage.getItem(LEGACY_DRAFT_STORAGE_KEY) || "";
      if (serialized) {
        window.localStorage.setItem(DRAFT_STORAGE_KEY, serialized);
      }
    }
    lastSavedDraft = serialized;
    return JSON.parse(serialized || "null");
  } catch {
    lastSavedDraft = "";
    return null;
  }
}

function clearDraft() {
  if (isDraftEnabled) {
    window.clearTimeout(draftSaveTimer);
    window.clearTimeout(remoteDraftSaveTimer);
    draftSaveTimer = 0;
    remoteDraftSaveTimer = 0;
    lastSavedDraft = "";
    lastRemoteDraft = "";
    window.localStorage.removeItem(DRAFT_STORAGE_KEY);
    window.localStorage.removeItem(LEGACY_DRAFT_STORAGE_KEY);
  }
}

async function saveRemoteDraft(showMessage = true) {
  if (!isDraftEnabled) {
    return;
  }
  const state = collectDraftState({ form, resultHost: result });
  const serialized = JSON.stringify(state);
  if (serialized === lastRemoteDraft) {
    setBbcodeBusy(false, "Статус: черновик уже сохранён, изменений нет.");
    return;
  }
  setBbcodeBusy(true, "Статус: сохраняю жалобу на сервере...");
  const response = await apiFetch("/api/complaint-draft", {
    method: "PUT",
    body: JSON.stringify({ draft: state }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setBbcodeBusy(false, "Статус: не удалось сохранить черновик.");
    showErrors(payload.detail || "Не удалось сохранить жалобу.");
    redirectIfUnauthorized(response.status);
    return;
  }
  lastRemoteDraft = serialized;
  setBbcodeBusy(false, "Статус: черновик жалобы сохранён.");
  if (showMessage) {
    showAppMessage(payload.message || "Жалоба сохранена.");
  }
}

async function loadRemoteDraft() {
  if (!isDraftEnabled) {
    return;
  }
  setBbcodeBusy(true, "Статус: проверяю сохранённый черновик...");
  const response = await apiFetch("/api/complaint-draft", { method: "GET", headers: {} });
  const payload = await parsePayload(response);
  if (!response.ok) {
    setBbcodeBusy(false, "Статус: не удалось загрузить сохранённый черновик.");
    redirectIfUnauthorized(response.status);
    return;
  }
  if (hasMeaningfulDraft(loadDraft())) {
    setBbcodeBusy(false, "Статус: использую локальный черновик из браузера.");
    return;
  }
  if (!hasMeaningfulDraft(payload.draft)) {
    setBbcodeBusy(false, "Статус: сохранённый черновик не найден.");
    return;
  }
  applyComplaintState(payload.draft);
  lastRemoteDraft = JSON.stringify(payload.draft || {});
  setBbcodeBusy(false, "Статус: сохранённый черновик загружен.");
  showAppMessage(payload.message || "Черновик жалобы загружен.");
}

async function clearRemoteDraft() {
  if (!isDraftEnabled) {
    return;
  }
  setBbcodeBusy(true, "Статус: очищаю сохранённый черновик...");
  const response = await apiFetch("/api/complaint-draft", { method: "DELETE", headers: {} });
  if (!response.ok) {
    const payload = await parsePayload(response);
    setBbcodeBusy(false, "Статус: не удалось очистить сохранённый черновик.");
    showErrors(payload.detail || "Не удалось очистить сохранённую жалобу.");
    redirectIfUnauthorized(response.status);
    return;
  }
  setBbcodeBusy(false, "Статус: сохранённый черновик очищен.");
}

function applyComplaintState(state) {
  isApplyingComplaintState = true;
  try {
    applyState({
      form,
      resultHost: result,
      template,
      state,
      onChange: handleFormChange,
    });
    syncDateTimeInputsFromHidden();
    setAiFocusHint();
  } finally {
    isApplyingComplaintState = false;
  }
}

function applyComplaintOcrResult(payload) {
  setFieldValue(form, "victim_name", payload.principal_name || "");
  setFieldValue(form, "victim_passport", payload.principal_passport || "");
  setFieldValue(form, "victim_phone", payload.principal_phone || "");
  setFieldValue(form, "victim_discord", payload.principal_discord || "");
  setFieldValue(form, "victim_address", payload.principal_address || "-");
  handleFormChange();
}

function handleFormChange() {
  syncEventDateTimeField();
  setAiFocusHint();
  updateRequiredProgress();
  scheduleDraftSave();
  scheduleRemoteDraftSave();
}

function scrollToResult() {
  document.getElementById("complaint-result-card")?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

async function generateBbcode(event) {
  event?.preventDefault?.();
  clearErrors();
  syncEventDateTimeField();
  setBbcodeBusy(true, "Статус: собираю данные жалобы и формирую BBCode...");

  try {
    const response = await apiFetch("/api/generate", {
      method: "POST",
      body: JSON.stringify(buildPayload({ form, presetPayload })),
    });

    if (!response.ok) {
      const payload = await parsePayload(response);
      const details = Array.isArray(payload.detail) ? [...payload.detail] : [payload.detail || "Не удалось сгенерировать BBCode."];
      if (details.some((line) => String(line).includes("Профиль:"))) {
        details.push("Откройте личный кабинет и заполните данные представителя, затем повторите генерацию.");
      }
      setBbcodeBusy(false, "Статус: BBCode не сформирован, проверьте ошибки выше.");
      showErrors(details);
      showAppMessage("BBCode не сформирован: проверьте сообщение об ошибке выше.");
      scrollToErrors();
      redirectIfUnauthorized(response.status);
      return;
    }

    const payload = await parsePayload(response);
    result.value = payload.bbcode || "";
    persistDraft();
    setBbcodeBusy(true, "Статус: BBCode сформирован, сохраняю актуальный черновик...");
    await saveRemoteDraft(false);
    setBbcodeBusy(false, "Статус: BBCode готов, можно копировать результат.");
    scrollToResult();
    showAppMessage("BBCode сформирован. Проверьте документ и при необходимости скопируйте результат.");
  } catch (error) {
    setBbcodeBusy(false, "Статус: генерация BBCode прервана из-за ошибки.");
    showErrors(error?.message || "Не удалось выполнить генерацию BBCode.");
    showAppMessage("Генерация BBCode прервана из-за ошибки на странице.");
    scrollToErrors();
  }
}

async function copyResult() {
  if (!result.value.trim()) {
    setBbcodeBusy(false, "Статус: сначала сформируйте BBCode.");
    showErrors("Сначала сформируйте BBCode.");
    return;
  }
  await navigator.clipboard.writeText(result.value);
  setBbcodeBusy(false, "Статус: результат скопирован в буфер обмена.");
  showAppMessage("Результат скопирован в буфер обмена.");
}

function resetDraft() {
  clearErrors();
  clearAiErrors();
  clearDraft();
  clearRemoteDraft();
  applyComplaintState(createPresetState(presetPayload) || {});
  setCurrentDate(form);
  resetComplaintOcrUi();
  syncComplaintOcrButtonState();
  setBbcodeBusy(false, "Статус: черновик очищен, форма готова к новой жалобе.");
  showAppMessage("Черновик жалобы очищен.");
}

async function requestAiSuggestion() {
  clearErrors();
  clearAiErrors();
  setAiBusy(true, "Подготавливаю нейтральную формулировку...");

  const payload = buildPayload({ form, presetPayload });
  const complaintBasis = complaintBasisField?.value?.trim() || "";
  const mainFocus = mainFocusField?.value?.trim() || "";

  try {
    const response = await apiFetch("/api/ai/suggest", {
      method: "POST",
      body: JSON.stringify({
        victim_name: payload.victim.name,
        org: payload.org,
        subject: payload.subject_names,
        event_dt: payload.event_dt,
        raw_desc: payload.situation_description,
        complaint_basis: complaintBasis,
        main_focus: mainFocus,
      }),
    });

    if (!response.ok) {
      const data = await parsePayload(response);
      showAiErrors(data.detail || "Не удалось получить AI-вариант.");
      redirectIfUnauthorized(response.status);
      return;
    }

    const data = await parsePayload(response);
    pendingAiText = data.text || "";
    aiModal.open(pendingAiText);
  } finally {
    setAiBusy(false);
  }
}

function applyAiText() {
  const desc = form.elements.namedItem("situation_description");
  if (!desc || !pendingAiText.trim()) {
    return;
  }
  desc.value = pendingAiText;
  handleFormChange();
  aiModal.close();
  showAppMessage("AI-вариант подставлен в описание нарушения.");
}

function bindEscToModals(...controllers) {
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    controllers.forEach((controller) => controller.close());
  });
}

form.addEventListener("submit", generateBbcode);
form.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    const target = event.target;
    if (target instanceof HTMLTextAreaElement) {
      event.preventDefault();
      generateBbcode();
    }
  }
});
generateBbcodeBtn?.addEventListener("click", generateBbcode);
copyBtn.addEventListener("click", copyResult);
aiBtn.addEventListener("click", requestAiSuggestion);
saveDraftBtn?.addEventListener("click", async () => {
  clearErrors();
  await saveRemoteDraft(true);
});

if (resetDraftBtn) {
  resetDraftBtn.addEventListener("click", resetDraft);
}

document.getElementById("ai-modal-apply")?.addEventListener("click", applyAiText);

aiModal.bind(
  document.getElementById("ai-modal-close"),
  document.getElementById("ai-modal-cancel"),
);
complaintOcrModal.bind(
  document.getElementById("complaint-ocr-modal-close"),
  document.getElementById("complaint-ocr-modal-ok"),
);
complaintFileErrorModal.bind(
  document.getElementById("complaint-file-error-close"),
  document.getElementById("complaint-file-error-ok"),
);
bindEscToModals(aiModal, complaintOcrModal, complaintFileErrorModal);

bindLogout(logoutBtn);
bindDynamicAddButtons({
  onChange: handleFormChange,
  addDynamicField: (targetId) => addDynamicField({ template, targetId, onChange: handleFormChange }),
});
bindDigitsOnly(form, "victim_phone", 7);
bindDigitsOnly(form, "appeal_no", 4);

(async () => {
  applyComplaintState(createPresetState(presetPayload) || {});
  applyComplaintState(loadDraft() || {});
  await loadRemoteDraft();
  setCurrentDate(form);
  resetComplaintOcrUi();
  syncComplaintOcrButtonState();
  setAiFocusHint();
  updateRequiredProgress();
})();

wireSingleUsePrincipalOcr({
  attemptStorageKey: "ogp_web_complaint_ocr_used",
  fileInput: complaintOcrFile,
  triggerButton: complaintOcrBtn,
  statusHost: complaintOcrStatus,
  progressHost: complaintOcrProgress,
  progressTextHost: complaintOcrProgressText,
  clearErrors,
  showErrors: (text) => complaintFileErrorModal.open(text),
  applyResult: applyComplaintOcrResult,
  onSuccess: () => complaintOcrModal.open(OCR_TEXT.successModal),
  readyStatus: OCR_TEXT.readyStatus,
  noFileStatus: OCR_TEXT.noFileStatus,
  noFileError: OCR_TEXT.noFileError,
  processingStatus: OCR_TEXT.processingStatus,
  busyText: OCR_TEXT.busyText,
  successStatus: OCR_TEXT.successStatus,
  failureStatus: OCR_TEXT.failureStatus,
  exceptionStatus: OCR_TEXT.exceptionStatus,
  fallbackErrorText: OCR_TEXT.fallbackErrorText,
});

const startupMessage = sessionStorage.getItem("ogp_app_message");
if (startupMessage) {
  showAppMessage(startupMessage);
  sessionStorage.removeItem("ogp_app_message");
}

form.addEventListener("input", handleFormChange);
form.addEventListener("change", handleFormChange);

clearAiErrors();
setAiBusy(false);
setBbcodeBusy(false, "Статус: готово к формированию BBCode.");
