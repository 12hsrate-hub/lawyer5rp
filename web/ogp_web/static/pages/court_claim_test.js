const form = document.getElementById("court-claim-form");
const resultField = document.getElementById("court-claim-result");
const buildButton = document.getElementById("court-claim-build-btn");
const copyButton = document.getElementById("court-claim-copy-btn");
const clearButton = document.getElementById("court-claim-clear-btn");
const courtTypeField = document.getElementById("court-type");
const claimKindDescriptionHost = document.getElementById("court-claim-kind-description");
const inDevelopmentCard = document.getElementById("court-claim-in-development");
const inDevelopmentText = document.getElementById("court-claim-in-development-text");
const claimKindField = document.getElementById("court-claim-kind");
const situationHintHost = document.getElementById("court-claim-situation-hint");
const evidenceHintHost = document.getElementById("court-claim-evidence-hint");
const fieldsHost = document.getElementById("court-claim-fields");
const previousDecisionCard = document.getElementById("court-previous-decision-card");
const plaintiffCard = document.getElementById("court-claim-plaintiff-card");
const defendantNameField = document.getElementById("court-claim-defendant-name-field");
const defendantAddressField = document.getElementById("court-claim-defendant-address-field");
const defendantPhoneField = document.getElementById("court-claim-defendant-phone-field");
const defendantPassportField = document.getElementById("court-claim-defendant-passport-field");
const defendantEmailField = document.getElementById("court-claim-defendant-email-field");
const defendantRepresentativeNameField = document.getElementById("court-claim-defendant-representative-name-field");
const defendantRepresentativeAddressField = document.getElementById("court-claim-defendant-representative-address-field");
const defendantRepresentativePhoneField = document.getElementById("court-claim-defendant-representative-phone-field");
const defendantRepresentativePassportField = document.getElementById("court-claim-defendant-representative-passport-field");
const defendantRepresentativeEmailField = document.getElementById("court-claim-defendant-representative-email-field");
const messageHost = document.getElementById("court-claim-message");
const errorsHost = document.getElementById("court-claim-errors");

const evidenceList = document.getElementById("court-claim-evidence-list");
const evidenceAddBtn = document.getElementById("court-claim-evidence-add");

const plaintiffOcrFile = document.getElementById("court-claim-plaintiff-ocr-file");
const plaintiffOcrButton = document.getElementById("court-claim-plaintiff-ocr-btn");
const plaintiffOcrStatus = document.getElementById("court-claim-plaintiff-ocr-status");
const plaintiffOcrProgress = document.getElementById("court-claim-plaintiff-ocr-progress");
const plaintiffOcrProgressText = document.getElementById("court-claim-plaintiff-ocr-progress-text");
const plaintiffOcrFileName = document.getElementById("court-claim-plaintiff-ocr-file-name");

const { apiFetch, parsePayload, setStateSuccess, setStateError, setStateIdle, redirectIfUnauthorized } = window.OGPWeb;
const { wireSingleUsePrincipalOcr, bindFilePickerLabel, createUiResetter } = window.OGPOcr;
const bindDigitsOnly = window.OGPForm?.bindDigitsOnly || (() => {});
const draftOwner = (form?.dataset?.username || "anonymous").trim().toLowerCase();
const DRAFT_STORAGE_KEY_PREFIX = `ogp_web_court_claim_draft_v2_${draftOwner || "anonymous"}`;

const OCR_TEXT = {
  emptyFileName: "Файл не выбран",
  readyStatus: "Статус: ожидает изображение.",
  noFileStatus: "Статус: сначала приложите 4-ю страницу договора.",
  noFileError: "Сначала выберите изображение 4-й страницы договора.",
  processingStatus: "Статус: изображение загружено, идет распознавание.",
  busyText: "Распознаю данные истца по 4-й странице договора...",
  successStatus: "Статус: данные найдены и подставлены в поля.",
  failureStatus: "Статус: распознавание завершилось с ошибкой.",
  exceptionStatus: "Статус: не удалось обработать изображение.",
  fallbackErrorText: "Не удалось распознать данные истца.",
};

let representativeProfile = null;
let draftSaveTimer = 0;
let activeDraftCourtType = "";
let activeDraftClaimKind = "";

const COURT_CLAIM_KIND_OPTIONS = {
  supreme: [
    {
      value: "supreme_admin_civil_with_representative",
      label: "Административно-гражданское исковое заявление с участием представителя",
      title: "Административно-гражданское исковое заявление с участием представителя",
      description: "Шаблон обращения в Верховный суд, подготовленный для ситуации, когда документ подается представителем в интересах доверителя.",
      ready: true,
    },
    {
      value: "supreme_admin_civil",
      label: "Административно-гражданское исковое заявление",
      title: "Административно-гражданское исковое заявление",
      description: "Шаблон административно-гражданского искового заявления для подачи в Верховный суд.",
      ready: true,
    },
    {
      value: "supreme_cassation",
      label: "Кассационная жалоба",
      title: "Кассационная жалоба",
      description: "Шаблон кассационной жалобы для обжалования вступившего в силу судебного акта.",
      ready: true,
    },
    {
      value: "supreme_interpretation",
      label: "Заявление о толковании и разъяснении правовых норм",
      title: "Толкование и разъяснение правовых норм",
      description: "Шаблон заявления о толковании и официальном разъяснении применимых правовых норм.",
      ready: true,
    },
    {
      value: "supreme_ai_warrant",
      label: "Заявление о получении ордера AI",
      title: "Получение ордера AI",
      description: "Шаблон заявления о выдаче ордера AI в пределах компетенции Верховного суда.",
      ready: true,
    },
  ],
  appeal: [
    {
      value: "appeal_admin_civil_with_representative",
      label: "Административно-гражданское исковое заявление с участием представителя",
      title: "Административно-гражданское исковое заявление с участием представителя",
      description: "Базовый шаблон обращения в Апелляционный суд с участием представителя.",
      ready: false,
    },
  ],
  federal: [
    {
      value: "federal_admin_civil_with_representative",
      label: "Административно-гражданское исковое заявление с участием представителя",
      title: "Административно-гражданское исковое заявление с участием представителя",
      description: "Базовый шаблон обращения в Федеральный суд с участием представителя.",
      ready: false,
    },
  ],
};

function readValue(name) {
  const field = form?.elements?.namedItem(name);
  if (!field) return "";
  return String(field.value || "").trim();
}

function setFieldValue(name, value) {
  const field = form?.elements?.namedItem(name);
  if (field) {
    field.value = value || "";
  }
}

function escapeBbcode(value) {
  return String(value || "")
    .replace(/\[/g, "&#91;")
    .replace(/\]/g, "&#93;");
}

function createEvidenceItem(label = "", url = "") {
  const item = document.createElement("div");
  item.className = "court-evidence-item legal-field-grid legal-field-grid--two";
  const labelInput = document.createElement("input");
  labelInput.type = "text";
  labelInput.className = "evidence-label";
  labelInput.placeholder = "Название документа";
  labelInput.value = label;
  const urlInput = document.createElement("input");
  urlInput.type = "url";
  urlInput.className = "evidence-url";
  urlInput.placeholder = "Ссылка (необязательно)";
  urlInput.value = url;
  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "ghost-button evidence-remove";
  removeBtn.textContent = "Удалить";
  removeBtn.addEventListener("click", () => {
    item.remove();
    scheduleDraftSave();
  });
  labelInput.addEventListener("input", scheduleDraftSave);
  urlInput.addEventListener("input", scheduleDraftSave);
  item.appendChild(labelInput);
  item.appendChild(urlInput);
  item.appendChild(removeBtn);
  return item;
}

function addEvidenceItem(label = "", url = "") {
  if (!evidenceList) return;
  evidenceList.appendChild(createEvidenceItem(label, url));
}

function collectEvidenceItems() {
  if (!evidenceList) return [];
  return Array.from(evidenceList.querySelectorAll(".court-evidence-item")).map((item) => ({
    label: item.querySelector(".evidence-label")?.value?.trim() || "",
    url: item.querySelector(".evidence-url")?.value?.trim() || "",
  }));
}

function buildEvidenceBbcode() {
  const items = collectEvidenceItems();
  const lines = [];
  for (const item of items) {
    if (!item.label && !item.url) continue;
    if (item.label) lines.push(escapeBbcode(item.label));
    if (item.url) {
      const safeUrl = item.url.replace(/'/g, "").replace(/[\[\]]/g, "");
      lines.push(`[URL='${safeUrl}']ссылка[/URL]`);
    }
  }
  return lines.join("\n");
}

function normalizeDiscordToEmail(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  if (raw.includes("@")) {
    return raw;
  }
  return `${raw}@sa.com`;
}

function formatPhone(value) {
  const digits = String(value || "").replace(/\D/g, "");
  if (digits.length === 7) {
    return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5)}`;
  }
  return String(value || "").trim();
}

function getMoscowDate() {
  const formatter = new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Europe/Moscow",
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
  return formatter.format(new Date());
}

function getSignatureText() {
  const fullName = String(representativeProfile?.name || "").trim();
  if (!fullName) {
    return "";
  }
  const parts = fullName.split(/\s+/).filter(Boolean);
  const initials = parts.map((part) => `${part.charAt(0).toUpperCase()}.`).join(" ");
  return initials ? `${fullName}, ${initials}` : fullName;
}

function setMessage(text) {
  if (!text) {
    setStateIdle(messageHost);
    return;
  }
  setStateSuccess(messageHost, text);
}

function setErrors(text) {
  if (!text) {
    setStateIdle(errorsHost);
    return;
  }
  setStateError(errorsHost, text);
}

function getClaimKindOptions(courtType) {
  return COURT_CLAIM_KIND_OPTIONS[courtType] || [];
}

function getActiveClaimKindOption() {
  const courtType = readValue("court_type");
  const claimKind = readValue("claim_kind");
  return getClaimKindOptions(courtType).find((option) => option.value === claimKind) || null;
}

function getDraftStorageKey(courtType, claimKind = readValue("claim_kind")) {
  const normalizedCourtType = String(courtType || "").trim();
  const normalizedClaimKind = String(claimKind || "").trim();
  if (!normalizedCourtType || !normalizedClaimKind) {
    return "";
  }
  return `${DRAFT_STORAGE_KEY_PREFIX}_${normalizedCourtType}_${normalizedClaimKind}`;
}

function collectDraftState() {
  const fields = {};
  form?.querySelectorAll("input[name], textarea[name], select[name]").forEach((field) => {
    fields[field.name] = field.value || "";
  });
  return {
    fields,
    evidence: collectEvidenceItems(),
    result: resultField?.value || "",
  };
}

function applyDraftState(state) {
  const fields = state?.fields || {};
  Object.entries(fields).forEach(([name, value]) => {
    setFieldValue(name, value);
  });
  if (evidenceList) {
    evidenceList.innerHTML = "";
  }
  const evidenceItems = state?.evidence || [];
  evidenceItems.forEach(({ label, url }) => addEvidenceItem(label, url));
  if (evidenceItems.length === 0) {
    addEvidenceItem();
  }
  if (resultField) {
    resultField.value = state?.result || "";
  }
  updateCourtSpecificUi();
}

function saveDraft(courtType = readValue("court_type"), claimKind = readValue("claim_kind")) {
  const storageKey = getDraftStorageKey(courtType, claimKind);
  if (!storageKey) {
    return;
  }
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(collectDraftState()));
  } catch {}
}

function scheduleDraftSave() {
  window.clearTimeout(draftSaveTimer);
  draftSaveTimer = window.setTimeout(() => {
    draftSaveTimer = 0;
    saveDraft();
  }, 180);
}

function loadDraft(courtType = readValue("court_type"), claimKind = readValue("claim_kind")) {
  const storageKey = getDraftStorageKey(courtType, claimKind);
  if (!storageKey) {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(storageKey) || "";
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function clearDraft(courtType = readValue("court_type"), claimKind = readValue("claim_kind")) {
  window.clearTimeout(draftSaveTimer);
  draftSaveTimer = 0;
  const storageKey = getDraftStorageKey(courtType, claimKind);
  if (!storageKey) {
    return;
  }
  try {
    window.localStorage.removeItem(storageKey);
  } catch {}
}

function resetCourtSpecificState({ preserveCourtType = false } = {}) {
  const currentCourtType = readValue("court_type");
  const currentClaimKind = readValue("claim_kind");
  form?.reset();
  if (preserveCourtType) {
    setFieldValue("court_type", currentCourtType);
    setFieldValue("claim_kind", currentClaimKind);
  }
  if (evidenceList) {
    evidenceList.innerHTML = "";
    addEvidenceItem();
  }
  if (resultField) {
    resultField.value = "";
  }
  resetPlaintiffOcrUi();
  updateCourtSpecificUi();
}

function renderClaimKindTabs(courtType) {
  const options = getClaimKindOptions(courtType);
  const selectedClaimKind = readValue("claim_kind");
  if (!claimKindField) {
    return;
  }
  claimKindField.innerHTML = "";
  claimKindField.disabled = !courtType;
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = courtType ? "Выберите вид обращения" : "Сначала выберите судебную инстанцию";
  claimKindField.appendChild(placeholder);
  options.forEach((option) => {
    const optionElement = document.createElement("option");
    optionElement.value = option.value;
    optionElement.textContent = option.label;
    claimKindField.appendChild(optionElement);
  });
  const hasSelectedOption = options.some((option) => option.value === selectedClaimKind);
  claimKindField.value = hasSelectedOption ? selectedClaimKind : "";
  const activeOption = getActiveClaimKindOption();
  if (claimKindDescriptionHost) {
    claimKindDescriptionHost.textContent = activeOption?.description || "Выберите судебную инстанцию и соответствующий вид обращения.";
  }
}

function updateCourtSpecificUi() {
  const courtType = readValue("court_type");
  const claimKind = readValue("claim_kind");
  const hasCourtType = Boolean(courtType);
  const hasClaimKind = Boolean(claimKind);
  const activeOption = getActiveClaimKindOption();
  const isReady = Boolean(activeOption?.ready);
  const isInterpretation = claimKind === "supreme_interpretation";
  const isCassation = claimKind === "supreme_cassation";
  const isProfilePlaintiff = claimKind === "supreme_admin_civil";
  renderClaimKindTabs(courtType);
  if (inDevelopmentCard) {
    inDevelopmentCard.hidden = !hasCourtType || !hasClaimKind || isReady;
  }
  if (inDevelopmentText) {
    inDevelopmentText.textContent = activeOption
      ? `Для шаблона "${activeOption.title}" форма еще в разработке.`
      : "Для выбранной комбинации суда и сути заявления шаблон еще не собран.";
  }
  if (fieldsHost) {
    fieldsHost.hidden = !hasCourtType || !hasClaimKind || !isReady;
  }
  if (plaintiffCard) {
    plaintiffCard.hidden = isInterpretation || isProfilePlaintiff;
  }
  [defendantNameField, defendantAddressField, defendantPhoneField, defendantPassportField, defendantEmailField].forEach((field) => {
    if (field) {
      field.hidden = isInterpretation;
    }
  });
  [
    defendantRepresentativeNameField,
    defendantRepresentativeAddressField,
    defendantRepresentativePhoneField,
    defendantRepresentativePassportField,
    defendantRepresentativeEmailField,
  ].forEach((field) => {
    if (field) {
      field.hidden = !isCassation;
    }
  });
  if (claimKind === "supreme_ai_warrant") {
    if (situationHintHost) {
      situationHintHost.textContent =
        "Пример: 23.12.2024 ответчик применил силу к доверителю и, по мнению стороны истца, превысил служебные полномочия. Для установления полной картины событий необходимо истребовать видеофиксацию ответчика, что возможно после выдачи ордера AI.";
    }
    if (evidenceHintHost) {
      evidenceHintHost.textContent =
        "Пример: запись в ls.gov, договор об оказании юридических услуг, регистрационные сведения по обращению, служебные материалы и иные документы, подтверждающие необходимость получения ордера AI.";
    }
  } else if (isInterpretation) {
    if (situationHintHost) {
      situationHintHost.textContent =
        "Пример: подробно опишите правовую неопределенность, укажите норму, которая допускает неоднозначное применение, и объясните, почему заявителю необходимо официальное толкование или разъяснение суда.";
    }
    if (evidenceHintHost) {
      evidenceHintHost.textContent =
        "Пример: приложите выдержки из нормативных актов, судебные решения, служебные документы, переписку, ответы ведомств и иные материалы, подтверждающие наличие спора в толковании нормы.";
    }
  } else if (isCassation) {
    if (situationHintHost) {
      situationHintHost.textContent =
        "Пример: 23.12.2024 Федеральный суд штата Сан-Андреас вынес решение по исковому заявлению FC-123. На указанное решение была подана апелляционная жалоба CA-456. 30.12.2024 Апелляционный суд вынес решение по жалобе. Сторона истца считает данные судебные акты незаконными и просит их отменить либо изменить, подробно изложив основания кассационного пересмотра.";
    }
    if (evidenceHintHost) {
      evidenceHintHost.textContent =
        "Пример: приложите решение Федерального суда, решение Апелляционного суда, копии жалоб, процессуальные документы, переписку, материалы дела и иные доказательства, подтверждающие доводы кассационной жалобы.";
    }
  } else if (isProfilePlaintiff) {
    if (situationHintHost) {
      situationHintHost.textContent =
        "Пример: подробно опишите обстоятельства спора, укажите, в чем именно выражается нарушение ваших прав, приведите правовую квалификацию и аргументы, по которым Верховный суд должен принять заявление к рассмотрению.";
    }
    if (evidenceHintHost) {
      evidenceHintHost.textContent =
        "Пример: приложите договоры, переписку, процессуальные документы, видеозаписи, выписки, судебные акты и иные материалы, которыми вы подтверждаете изложенные доводы.";
    }
  } else {
    if (situationHintHost) {
      situationHintHost.textContent =
        "Укажите дату и последовательность событий, действия ответчика, суть нарушения, правовую квалификацию и причину, по которой требуется судебное вмешательство.";
    }
    if (evidenceHintHost) {
      evidenceHintHost.textContent =
        "Перечислите документы, реестры, договоры, записи, переписку, видео, запросы и иные материалы, на которые ссылается сторона обращения.";
    }
  }
  const needsPreviousDecision = (courtType === "appeal" || courtType === "supreme") && !isInterpretation;
  if (previousDecisionCard) {
    previousDecisionCard.hidden = !hasCourtType || !hasClaimKind || !isReady || !needsPreviousDecision;
  }
}

function buildRepresentativeLine() {
  const profile = representativeProfile || {};
  return `[b]ПРЕДСТАВИТЕЛЬ ИСТЦА[/b] - ${escapeBbcode(profile.name)}, ${escapeBbcode(profile.address || "без места проживания")},\nномер мобильного телефона ${escapeBbcode(formatPhone(profile.phone))}, номер паспорта ${escapeBbcode(profile.passport)}\nАдрес электронной почты: ${escapeBbcode(normalizeDiscordToEmail(profile.discord))}`;
}

function buildPlaintiffLine() {
  const plaintiffEmail = readValue("plaintiff_email") || normalizeDiscordToEmail("");
  return `[b]ИСТЕЦ[/b] - ${escapeBbcode(readValue("plaintiff_name"))}, ${escapeBbcode(readValue("plaintiff_address"))},\nномер мобильного телефона ${escapeBbcode(formatPhone(readValue("plaintiff_phone")))}, номер паспорта ${escapeBbcode(readValue("plaintiff_passport"))}\nАдрес электронной почты: ${escapeBbcode(plaintiffEmail)}`;
}

function buildDefendantLine() {
  const defendantEmail = readValue("defendant_email");
  const emailLine = defendantEmail ? `\nАдрес электронной почты: ${escapeBbcode(defendantEmail)}` : "";
  return `[b]ОТВЕТЧИК[/b] - ${escapeBbcode(readValue("defendant_name"))}, ${escapeBbcode(readValue("defendant_address"))},\nномер мобильного телефона ${escapeBbcode(formatPhone(readValue("defendant_phone")))}, номер паспорта ${escapeBbcode(readValue("defendant_passport"))}${emailLine}`;
}

function buildDefendantRepresentativeLine() {
  const representativeName = readValue("defendant_representative_name");
  if (!representativeName) {
    return "";
  }
  const representativeEmail = readValue("defendant_representative_email");
  const emailLine = representativeEmail ? `\nАдрес электронной почты: ${escapeBbcode(representativeEmail)}` : "";
  return `[b]ПРЕДСТАВИТЕЛЬ ОТВЕТЧИКА[/b] - ${escapeBbcode(representativeName)}, ${escapeBbcode(readValue("defendant_representative_address") || "без места проживания")},\nномер мобильного телефона ${escapeBbcode(formatPhone(readValue("defendant_representative_phone")))}, номер паспорта ${escapeBbcode(readValue("defendant_representative_passport"))}${emailLine}`;
}

function buildApplicantLine() {
  const profile = representativeProfile || {};
  return `[b]ЗАЯВИТЕЛЬ[/b] - ${escapeBbcode(profile.name)}, ${escapeBbcode(profile.address || "без места проживания")},\nномер мобильного телефона ${escapeBbcode(formatPhone(profile.phone))}, номер паспорта ${escapeBbcode(profile.passport)}\nАдрес электронной почты: ${escapeBbcode(normalizeDiscordToEmail(profile.discord))}`;
}

function buildProfilePlaintiffLine() {
  const profile = representativeProfile || {};
  return `[b]ИСТЕЦ[/b] - ${escapeBbcode(profile.name)}, ${escapeBbcode(profile.address || "без места проживания")},\nномер мобильного телефона ${escapeBbcode(formatPhone(profile.phone))}, номер паспорта ${escapeBbcode(profile.passport)}\nАдрес электронной почты: ${escapeBbcode(normalizeDiscordToEmail(profile.discord))}`;
}

function buildStructuredSupremeBbcode() {
  return [
    `[b]РАЗДЕЛ I. ИНФОРМАЦИЯ О ФИГУРАНТАХ[/b]`,
    "",
    buildRepresentativeLine(),
    "",
    buildPlaintiffLine(),
    "",
    buildDefendantLine(),
    "",
    `[b]РАЗДЕЛ II. ОПИСАТЕЛЬНАЯ ЧАСТЬ[/b]`,
    "",
    escapeBbcode(readValue("situation_description")),
    "",
    `[b]РАЗДЕЛ III. ДОКАЗАТЕЛЬСТВА[/b]`,
    "",
    buildEvidenceBbcode(),
    "",
    `[b]РАЗДЕЛ IV. ЗАКЛЮЧИТЕЛЬНАЯ ЧАСТЬ[/b]`,
    "",
    escapeBbcode(readValue("closing_request")),
    "",
    `[right]${escapeBbcode(getMoscowDate())}[/right]`,
    `[right]${escapeBbcode(getSignatureText())}[/right]`,
  ].join("\n");
}

function buildSupremeCourtBbcode() {
  return buildStructuredSupremeBbcode();
}

function buildSupremeAiWarrantBbcode() {
  return buildStructuredSupremeBbcode();
}

function buildSupremeInterpretationBbcode() {
  return [
    `[b]РАЗДЕЛ I. ИНФОРМАЦИЯ О ФИГУРАНТАХ[/b]`,
    "",
    buildApplicantLine(),
    "",
    `[b]РАЗДЕЛ II. ОПИСАТЕЛЬНАЯ ЧАСТЬ[/b]`,
    "",
    escapeBbcode(readValue("situation_description")),
    "",
    `[b]РАЗДЕЛ III. ДОКАЗАТЕЛЬСТВА[/b]`,
    "",
    buildEvidenceBbcode(),
    "",
    `[b]РАЗДЕЛ IV. ЗАКЛЮЧИТЕЛЬНАЯ ЧАСТЬ[/b]`,
    "",
    escapeBbcode(readValue("closing_request")),
    "",
    `[right]${escapeBbcode(getMoscowDate())}[/right]`,
    `[right]${escapeBbcode(getSignatureText())}[/right]`,
  ].join("\n");
}

function buildSupremeCassationBbcode() {
  const defendantRepresentativeLine = buildDefendantRepresentativeLine();
  return [
    `[b]РАЗДЕЛ I. ИНФОРМАЦИЯ О ФИГУРАНТАХ[/b]`,
    "",
    buildPlaintiffLine(),
    "",
    buildDefendantLine(),
    defendantRepresentativeLine ? "" : null,
    defendantRepresentativeLine || null,
    "",
    `[b]РАЗДЕЛ II. ОПИСАТЕЛЬНАЯ ЧАСТЬ[/b]`,
    "",
    escapeBbcode(readValue("situation_description")),
    "",
    `[b]РАЗДЕЛ III. ДОКАЗАТЕЛЬСТВА[/b]`,
    "",
    buildEvidenceBbcode(),
    "",
    `[b]РАЗДЕЛ IV. ЗАКЛЮЧИТЕЛЬНАЯ ЧАСТЬ[/b]`,
    "",
    escapeBbcode(readValue("closing_request")),
    "",
    `[right]${escapeBbcode(getMoscowDate())}[/right]`,
    `[right]${escapeBbcode(getSignatureText())}[/right]`,
  ]
    .filter((line) => line !== null)
    .join("\n");
}

function buildSupremeAdminCivilProfileBbcode() {
  return [
    `[b]РАЗДЕЛ I. ИНФОРМАЦИЯ О ФИГУРАНТАХ[/b]`,
    "",
    buildProfilePlaintiffLine(),
    "",
    buildDefendantLine(),
    "",
    `[b]РАЗДЕЛ II. ОПИСАТЕЛЬНАЯ ЧАСТЬ[/b]`,
    "",
    escapeBbcode(readValue("situation_description")),
    "",
    `[b]РАЗДЕЛ III. ДОКАЗАТЕЛЬСТВА[/b]`,
    "",
    buildEvidenceBbcode(),
    "",
    `[b]РАЗДЕЛ IV. ЗАКЛЮЧИТЕЛЬНАЯ ЧАСТЬ[/b]`,
    "",
    escapeBbcode(readValue("closing_request")),
    "",
    `[right]${escapeBbcode(getMoscowDate())}[/right]`,
    `[right]${escapeBbcode(getSignatureText())}[/right]`,
  ].join("\n");
}

function buildAppealOrFederalPlaceholderBbcode() {
  const courtType = readValue("court_type");
  const activeOption = getActiveClaimKindOption();
  const courtLabel = courtType === "appeal" ? "Апелляционный суд" : "Федеральный суд";
  const previousInfo = readValue("previous_court_name")
    ? `\n\n[b]Данные предыдущего решения[/b]\nСуд: ${escapeBbcode(readValue("previous_court_name"))}\nНомер дела: ${escapeBbcode(readValue("previous_case_number"))}\nДата решения: ${escapeBbcode(readValue("previous_decision_date"))}\nПредмет обжалования: ${escapeBbcode(readValue("previous_decision_subject"))}`
    : "";

  return [
    `[center]${courtLabel}[/center]`,
    activeOption ? `[center][b]${escapeBbcode(activeOption.title)}[/b][/center]` : "",
    "",
    `[b]Шаблон для выбранного суда пока собирается по образцу.[/b]`,
    "",
    `[b]Фигуранты[/b]`,
    `Представитель истца: ${escapeBbcode(representativeProfile?.name || "")}`,
    `Истец: ${escapeBbcode(readValue("plaintiff_name"))}`,
    `Ответчик: ${escapeBbcode(readValue("defendant_name"))}`,
    previousInfo,
    "",
    `[b]Описательная часть[/b]`,
    escapeBbcode(readValue("situation_description")),
    "",
    `[b]Доказательства[/b]`,
    buildEvidenceBbcode(),
    "",
    `[b]Просительная часть[/b]`,
    escapeBbcode(readValue("closing_request")),
    "",
    `[right]${escapeBbcode(getMoscowDate())}[/right]`,
    `[right]${escapeBbcode(getSignatureText())}[/right]`,
  ].join("\n");
}

function buildBbcode() {
  const courtType = readValue("court_type");
  const claimKind = readValue("claim_kind");
  if (courtType === "supreme" && claimKind === "supreme_admin_civil_with_representative") {
    return buildSupremeCourtBbcode();
  }
  if (courtType === "supreme" && claimKind === "supreme_admin_civil") {
    return buildSupremeAdminCivilProfileBbcode();
  }
  if (courtType === "supreme" && claimKind === "supreme_ai_warrant") {
    return buildSupremeAiWarrantBbcode();
  }
  if (courtType === "supreme" && claimKind === "supreme_cassation") {
    return buildSupremeCassationBbcode();
  }
  if (courtType === "supreme" && claimKind === "supreme_interpretation") {
    return buildSupremeInterpretationBbcode();
  }
  return buildAppealOrFederalPlaceholderBbcode();
}

function hasRepresentativeProfile() {
  const profile = representativeProfile || {};
  return Boolean(profile.name && profile.phone && profile.passport);
}

function scrollToErrors() {
  errorsHost?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function handleBuild() {
  setErrors("");
  setMessage("");
  const courtType = readValue("court_type");
  const claimKind = readValue("claim_kind");

  if (!courtType) {
    setErrors("Сначала выберите суд, куда подается заявление.");
    scrollToErrors();
    return;
  }

  if (!claimKind) {
    setErrors("Сначала выберите суть заявления для выбранного суда.");
    scrollToErrors();
    return;
  }

  if (!getActiveClaimKindOption()?.ready) {
    setErrors("Для выбранной комбинации суда и сути заявления форма еще в разработке.");
    scrollToErrors();
    return;
  }

  if (!hasRepresentativeProfile()) {
    setErrors("Сначала заполните данные представителя в личном кабинете. Для шаблона нужны минимум ФИО, телефон и паспорт.");
    scrollToErrors();
    return;
  }

  const requiredFields =
    claimKind === "supreme_interpretation"
      ? ["situation_description", "closing_request"]
      : claimKind === "supreme_admin_civil"
      ? ["defendant_name", "situation_description", "closing_request"]
      : ["plaintiff_name", "defendant_name", "situation_description", "closing_request"];
  const missing = requiredFields.filter((name) => !readValue(name));
  if (missing.length) {
    setErrors(
      claimKind === "supreme_interpretation"
        ? "Заполни минимум: описательную часть и заключительную часть."
        : claimKind === "supreme_admin_civil"
        ? "Заполни минимум: ответчика, описательную часть и заключительную часть."
        : "Заполни минимум: истец, ответчик, описательная часть и заключительная часть."
    );
    scrollToErrors();
    return;
  }

  resultField.value = buildBbcode();
  saveDraft();
  setMessage("BBCode шаблон обновлен.");
  resultField.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function handleCopy() {
  if (!resultField.value.trim()) {
    handleBuild();
  }
  if (!resultField.value.trim()) {
    return;
  }
  await navigator.clipboard.writeText(resultField.value);
  setErrors("");
  setMessage("BBCode скопирован в буфер обмена.");
}

function resetForm() {
  const currentCourtType = readValue("court_type");
  const currentClaimKind = readValue("claim_kind");
  clearDraft(currentCourtType, currentClaimKind);
  resetCourtSpecificState();
  activeDraftCourtType = "";
  activeDraftClaimKind = "";
  setErrors("");
  setMessage("Черновик очищен.");
}

function applyPlaintiffOcrResult(payload) {
  setFieldValue("plaintiff_name", payload.principal_name || "");
  setFieldValue("plaintiff_passport", payload.principal_passport || "");
  setFieldValue("plaintiff_phone", payload.principal_phone || "");
  setFieldValue("plaintiff_address", payload.principal_address || "без места проживания");
  if (!readValue("plaintiff_email")) {
    setFieldValue("plaintiff_email", normalizeDiscordToEmail(payload.principal_discord || ""));
  }
  saveDraft();
  setMessage("Данные истца подставлены из договора. Проверьте их перед сборкой BBCode.");
}

async function loadRepresentativeProfile() {
  const response = await apiFetch("/api/profile", { method: "GET", headers: {} });
  if (!response.ok) {
    const payload = await parsePayload(response);
    representativeProfile = {};
    setErrors(payload.detail || "Не удалось загрузить профиль представителя.");
    redirectIfUnauthorized(response.status);
    return;
  }

  const payload = await parsePayload(response);
  representativeProfile = payload.representative || {};
}

function handleCourtTypeChange() {
  const nextCourtType = readValue("court_type");
  if (activeDraftCourtType && activeDraftClaimKind) {
    saveDraft(activeDraftCourtType, activeDraftClaimKind);
  }
  resetCourtSpecificState({ preserveCourtType: true });
  const defaultClaimKind = getClaimKindOptions(nextCourtType)[0]?.value || "";
  setFieldValue("claim_kind", defaultClaimKind);
  const draft = loadDraft(nextCourtType, defaultClaimKind);
  applyDraftState(draft);
  activeDraftCourtType = nextCourtType;
  activeDraftClaimKind = defaultClaimKind;
  setErrors("");
  if (!nextCourtType) {
    setFieldValue("claim_kind", "");
    renderClaimKindTabs("");
    setMessage("");
    return;
  }
  setMessage(draft ? "Загружен черновик для выбранной судебной инстанции." : "");
}

function handleClaimKindChange(nextClaimKind) {
  const currentCourtType = readValue("court_type");
  if (!currentCourtType) {
    return;
  }
  if (activeDraftCourtType && activeDraftClaimKind) {
    saveDraft(activeDraftCourtType, activeDraftClaimKind);
  }
  resetCourtSpecificState({ preserveCourtType: true });
  setFieldValue("claim_kind", nextClaimKind);
  const draft = loadDraft(currentCourtType, nextClaimKind);
  applyDraftState(draft);
  activeDraftCourtType = currentCourtType;
  activeDraftClaimKind = nextClaimKind;
  setErrors("");
  setMessage(draft ? "Загружен черновик для выбранного вида обращения." : "");
}

courtTypeField?.addEventListener("change", handleCourtTypeChange);
claimKindField?.addEventListener("change", () => handleClaimKindChange(readValue("claim_kind")));
buildButton?.addEventListener("click", handleBuild);
copyButton?.addEventListener("click", () => {
  handleCopy().catch(() => setErrors("Не удалось скопировать BBCode в буфер обмена."));
});
clearButton?.addEventListener("click", resetForm);

bindDigitsOnly(form, "plaintiff_phone", 7);
bindDigitsOnly(form, "defendant_phone", 7);
bindDigitsOnly(form, "plaintiff_passport", 6);
bindDigitsOnly(form, "defendant_passport", 6);
bindDigitsOnly(form, "defendant_representative_phone", 7);
bindDigitsOnly(form, "defendant_representative_passport", 6);

const plaintiffFilePicker = bindFilePickerLabel({
  fileInput: plaintiffOcrFile,
  nameHost: plaintiffOcrFileName,
  emptyText: OCR_TEXT.emptyFileName,
});

const resetPlaintiffOcrUi = createUiResetter({
  fileInput: plaintiffOcrFile,
  progressHost: plaintiffOcrProgress,
  progressTextHost: plaintiffOcrProgressText,
  statusHost: plaintiffOcrStatus,
  readyStatus: OCR_TEXT.readyStatus,
  filePicker: plaintiffFilePicker,
});

wireSingleUsePrincipalOcr({
  fileInput: plaintiffOcrFile,
  triggerButton: plaintiffOcrButton,
  statusHost: plaintiffOcrStatus,
  progressHost: plaintiffOcrProgress,
  progressTextHost: plaintiffOcrProgressText,
  clearErrors: () => setErrors(""),
  showErrors: (text) => setErrors(text),
  applyResult: applyPlaintiffOcrResult,
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

evidenceAddBtn?.addEventListener("click", () => {
  addEvidenceItem();
  scheduleDraftSave();
});

updateCourtSpecificUi();
resetPlaintiffOcrUi();
activeDraftCourtType = readValue("court_type");
activeDraftClaimKind = readValue("claim_kind");
applyDraftState(loadDraft(activeDraftCourtType, activeDraftClaimKind));
loadRepresentativeProfile().catch((error) => {
  representativeProfile = {};
  setErrors(error?.message || "Не удалось загрузить профиль представителя.");
});
form?.addEventListener("input", scheduleDraftSave);
form?.addEventListener("change", scheduleDraftSave);
