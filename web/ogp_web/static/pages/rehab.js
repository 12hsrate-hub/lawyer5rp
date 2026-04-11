const form = document.getElementById("rehab-form");
const result = document.getElementById("result");
const errors = document.getElementById("errors");
const copyBtn = document.getElementById("copy-btn");
const logoutBtn = document.getElementById("logout-btn");
const appMessage = document.getElementById("app-message");
const rehabOcrFile = document.getElementById("rehab-ocr-file");
const rehabOcrBtn = document.getElementById("rehab-ocr-btn");
const rehabOcrStatus = document.getElementById("rehab-ocr-status");
const rehabOcrProgress = document.getElementById("rehab-ocr-progress");
const rehabOcrProgressText = document.getElementById("rehab-ocr-progress-text");
const rehabOcrFileName = document.getElementById("rehab-ocr-file-name");

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

const OCR_TEXT = {
  emptyFileName: "Файл не выбран",
  readyStatus: "Статус: ожидает изображение.",
  noFileStatus: "Статус: сначала приложите 4-ю страницу договора.",
  noFileError: "Сначала выберите изображение 4-й страницы договора.",
  processingStatus: "Статус: изображение загружено, идет распознавание.",
  busyText: "Пытаюсь распознать данные доверителя по 4-й странице договора...",
  successStatus: "Статус: данные найдены и подставлены в поля.",
  failureStatus: "Статус: распознавание завершилось с ошибкой.",
  exceptionStatus: "Статус: не удалось обработать изображение.",
  fallbackErrorText: "Не удалось распознать данные доверителя.",
  successModal:
    "Данные доверителя подставлены автоматически. Обязательно проверьте ФИО и паспорт перед отправкой заявления.",
};

const rehabOcrModal = createModalController({
  modal: document.getElementById("rehab-ocr-modal"),
  textHost: document.getElementById("rehab-ocr-modal-text"),
});

const rehabFilePicker = bindFilePickerLabel({
  fileInput: rehabOcrFile,
  nameHost: rehabOcrFileName,
  emptyText: OCR_TEXT.emptyFileName,
});

const resetRehabOcrUi = createUiResetter({
  fileInput: rehabOcrFile,
  progressHost: rehabOcrProgress,
  progressTextHost: rehabOcrProgressText,
  statusHost: rehabOcrStatus,
  readyStatus: OCR_TEXT.readyStatus,
  closeModal: rehabOcrModal.close,
  filePicker: rehabFilePicker,
});

function showErrors(lines) {
  setStateError(errors, Array.isArray(lines) ? lines.join("\n") : String(lines || ""));
}

function clearErrors() {
  setStateIdle(errors);
}

function showAppMessage(text) {
  if (!text) {
    setStateIdle(appMessage);
    return;
  }
  setStateSuccess(appMessage, text);
}

function buildPayload() {
  const data = new FormData(form);
  return {
    principal_name: data.get("principal_name")?.toString().trim() || "",
    principal_passport: data.get("principal_passport")?.toString().trim() || "",
    principal_passport_scan_url: data.get("principal_passport_scan_url")?.toString().trim() || "",
    served_seven_days: (data.get("served_seven_days")?.toString().trim() || "false") === "true",
    contract_url: data.get("contract_url")?.toString().trim() || "",
  };
}

function bindDigitsOnly(fieldName, maxLength) {
  const field = form.elements.namedItem(fieldName);
  if (!field) {
    return;
  }
  field.addEventListener("input", () => {
    field.value = field.value.replace(/\D/g, "").slice(0, maxLength);
  });
}

async function generateBbcode(event) {
  event.preventDefault();
  clearErrors();

  try {
    const response = await apiFetch("/api/generate-rehab", {
      method: "POST",
      body: JSON.stringify(buildPayload()),
    });

    if (!response.ok) {
      const payload = await parsePayload(response);
      showErrors(payload.detail || "Не удалось сгенерировать BBCode.");
      redirectIfUnauthorized(response.status);
      return;
    }

    const payload = await parsePayload(response);
    result.value = payload.bbcode || "";
    showAppMessage("BBCode сформирован. Проверьте документ и скопируйте результат.");
  } catch (error) {
    showErrors(error?.message || "Не удалось выполнить генерацию BBCode.");
  }
}

async function copyResult() {
  if (!result.value.trim()) {
    showErrors("Сначала сгенерируйте BBCode.");
    return;
  }
  await navigator.clipboard.writeText(result.value);
  showAppMessage("Результат скопирован в буфер обмена.");
}

function bindEscapeToModal(controller) {
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      controller.close();
    }
  });
}

form.addEventListener("submit", generateBbcode);
copyBtn.addEventListener("click", copyResult);

wireSingleUsePrincipalOcr({
  attemptStorageKey: "ogp_web_rehab_ocr_used",
  fileInput: rehabOcrFile,
  triggerButton: rehabOcrBtn,
  statusHost: rehabOcrStatus,
  progressHost: rehabOcrProgress,
  progressTextHost: rehabOcrProgressText,
  clearErrors,
  showErrors,
  applyResult: (payload) => {
    form.elements.namedItem("principal_name").value = payload.principal_name || "";
    form.elements.namedItem("principal_passport").value = payload.principal_passport || "";
  },
  onSuccess: () => rehabOcrModal.open(OCR_TEXT.successModal),
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

rehabOcrModal.bind(
  document.getElementById("rehab-ocr-modal-close"),
  document.getElementById("rehab-ocr-modal-ok"),
);
bindEscapeToModal(rehabOcrModal);

bindLogout(logoutBtn);
bindDigitsOnly("principal_passport", 6);
resetRehabOcrUi();
