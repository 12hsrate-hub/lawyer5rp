const profileForm = document.getElementById("profile-form");
const profileErrors = document.getElementById("profile-errors");
const profileMessage = document.getElementById("profile-message");
const passwordForm = document.getElementById("password-form");
const passwordErrors = document.getElementById("password-errors");
const passwordMessage = document.getElementById("password-message");
const appMessage = document.getElementById("app-message");
const logoutBtn = document.getElementById("logout-btn");
const profileProgressText = document.getElementById("profile-progress-text");
const profileProgressBar = document.getElementById("profile-progress-bar");
const profileProgressHost = document.getElementById("profile-progress-host");
const profileSubmitButton = profileForm?.querySelector("button[type='submit']");
const passwordSubmitButton = passwordForm?.querySelector("button[type='submit']");
const currentServerCodeField = document.getElementById("current-server-code");
const targetServerCodeField = document.getElementById("target-server-code");
const switchServerBtn = document.getElementById("switch-server-btn");
const serverSwitchKeepHost = document.getElementById("server-switch-preview-keep");
const serverSwitchClearHost = document.getElementById("server-switch-preview-clear");
const serverSwitchAttentionHost = document.getElementById("server-switch-preview-attention");
const serverSwitchConfirmBtn = document.getElementById("server-switch-confirm-btn");
const serverSwitchCancelBtn = document.getElementById("server-switch-cancel-btn");

const { apiFetch, parsePayload, setStateError, setStateIdle, setStateSuccess, redirectIfUnauthorized } = window.OGPWeb;
const { bindLogout } = window.OGPPage;
const bindDigitsOnly = window.OGPForm?.bindDigitsOnly || (() => {});
const setButtonBusy = window.OGPForm?.setButtonBusy || (() => {});
const serverSwitchModal = window.OGPWeb.createModalController({
  modal: document.getElementById("server-switch-modal"),
});
let pendingSwitchDraft = null;
let pendingSwitchServerId = "";

function showProfileErrors(lines) {
  setStateError(profileErrors, Array.isArray(lines) ? lines.join("\n") : String(lines || ""));
}

function clearProfileErrors() {
  setStateIdle(profileErrors);
}

function showProfileMessage(text) {
  if (!text) {
    setStateIdle(profileMessage);
    return;
  }
  setStateSuccess(profileMessage, text);
}

function showPasswordErrors(lines) {
  setStateError(passwordErrors, Array.isArray(lines) ? lines.join("\n") : String(lines || ""));
}

function clearPasswordErrors() {
  setStateIdle(passwordErrors);
}

function showPasswordMessage(text) {
  if (!text) {
    setStateIdle(passwordMessage);
    return;
  }
  setStateSuccess(passwordMessage, text);
}

function showAppMessage(text) {
  if (!text) {
    setStateIdle(appMessage);
    return;
  }
  setStateSuccess(appMessage, text);
}

function fillProfileForm(profile) {
  profileForm.elements.namedItem("name").value = profile.name || "";
  profileForm.elements.namedItem("passport").value = profile.passport || "";
  profileForm.elements.namedItem("address").value = profile.address || "";
  profileForm.elements.namedItem("phone").value = profile.phone || "";
  profileForm.elements.namedItem("discord").value = profile.discord || "";
  profileForm.elements.namedItem("passport_scan_url").value = profile.passport_scan_url || "";
  updateProfileProgress();
}

function collectProfilePayload() {
  const data = new FormData(profileForm);
  return {
    name: data.get("name")?.toString().trim() || "",
    passport: data.get("passport")?.toString().trim() || "",
    address: data.get("address")?.toString().trim() || "",
    phone: data.get("phone")?.toString().trim() || "",
    discord: data.get("discord")?.toString().trim() || "",
    passport_scan_url: data.get("passport_scan_url")?.toString().trim() || "",
  };
}

async function collectDraftSwitchPayload() {
  const serverId = String(targetServerCodeField?.value || "").trim().toLowerCase();
  const draftResponse = await apiFetch("/api/complaint-draft", { method: "GET", headers: {} });
  const draftPayload = await parsePayload(draftResponse);
  if (!draftResponse.ok) {
    throw new Error(Array.isArray(draftPayload?.detail) ? draftPayload.detail.join(", ") : "Не удалось загрузить текущий черновик.");
  }
  return {
    server_id: serverId,
    draft: draftPayload?.draft || {},
  };
}

function renderSwitchPreview(payload) {
  const diff = payload?.diff || {};
  const keeps = Array.isArray(diff.keeps) && diff.keeps.length ? diff.keeps.join(", ") : "нет заполненных полей";
  const clears = Array.isArray(diff.clears) && diff.clears.length ? diff.clears.join(", ") : "ничего";
  const required = Array.isArray(diff.new_required_fields) ? diff.new_required_fields : [];
  const invalid = Array.isArray(diff.invalid_values) ? diff.invalid_values : [];
  const invalidText = invalid.length
    ? invalid.map((item) => `${item.field}: ${item.reason}`).join("; ")
    : "нет невалидных значений";
  const requiredText = required.length ? required.join(", ") : "новых обязательных полей нет";
  serverSwitchKeepHost.textContent = `Сохранится: ${keeps}.`;
  serverSwitchClearHost.textContent = `Очистится: ${clears}.`;
  serverSwitchAttentionHost.textContent = `Потребует внимания: ${requiredText}; ${invalidText}.`;
}

async function previewServerSwitch() {
  try {
    const payload = await collectDraftSwitchPayload();
    const response = await apiFetch("/api/document-builder/preview-switch", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const data = await parsePayload(response);
    if (!response.ok) {
      showProfileErrors(data.detail || "Не удалось получить предпросмотр переключения.");
      redirectIfUnauthorized(response.status);
      return;
    }
    pendingSwitchDraft = data.draft || {};
    pendingSwitchServerId = data.server_id || payload.server_id;
    renderSwitchPreview(data);
    serverSwitchModal.open();
  } catch (error) {
    showProfileErrors(error?.message || "Не удалось подготовить переключение.");
  }
}

async function confirmServerSwitch() {
  if (!pendingSwitchServerId) {
    return;
  }
  const response = await apiFetch("/api/document-builder/confirm-switch", {
    method: "POST",
    body: JSON.stringify({ server_id: pendingSwitchServerId, draft: pendingSwitchDraft || {} }),
  });
  const data = await parsePayload(response);
  if (!response.ok) {
    showProfileErrors(data.detail || "Не удалось переключить сервер.");
    redirectIfUnauthorized(response.status);
    return;
  }
  if (currentServerCodeField) {
    currentServerCodeField.value = data.server_id || pendingSwitchServerId;
  }
  showAppMessage(data.message || "Сервер переключен.");
  serverSwitchModal.close();
}

function updateProfileProgress() {
  if (!profileForm || !profileProgressText || !profileProgressBar || !profileProgressHost) {
    return;
  }
  const trackedFields = [...profileForm.querySelectorAll("[data-profile-track='true']")];
  const total = trackedFields.length;
  if (!total) {
    profileProgressText.textContent = "Профиль: 0/0";
    profileProgressBar.style.width = "0%";
    profileProgressHost.setAttribute("aria-valuenow", "0");
    return;
  }
  const filled = trackedFields.filter((field) => String(field.value || "").trim() !== "").length;
  const percent = Math.round((filled / total) * 100);
  profileProgressText.textContent = `Профиль: ${filled}/${total}`;
  profileProgressBar.style.width = `${percent}%`;
  profileProgressHost.setAttribute("aria-valuenow", String(percent));
}

async function loadProfile() {
  clearProfileErrors();
  showProfileMessage("");

  const response = await apiFetch("/api/profile", { method: "GET", headers: {} });
  if (!response.ok) {
    const payload = await parsePayload(response);
    showProfileErrors(payload.detail || "Не удалось загрузить профиль.");
    redirectIfUnauthorized(response.status);
    return;
  }

  const payload = await parsePayload(response);
  fillProfileForm(payload.representative);
}

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearProfileErrors();
  setButtonBusy(profileSubmitButton, true, { busyLabel: "Сохраняю..." });

  try {
    const response = await apiFetch("/api/profile", {
      method: "PUT",
      body: JSON.stringify(collectProfilePayload()),
    });

    const payload = await parsePayload(response);
    if (!response.ok) {
      showProfileErrors(payload.detail || "Не удалось сохранить профиль.");
      redirectIfUnauthorized(response.status);
      return;
    }

    fillProfileForm(payload.representative);
    showProfileMessage(payload.message || "Профиль сохранен.");
    showAppMessage("Данные представителя обновлены и сразу используются в рабочих формах.");
  } finally {
    setButtonBusy(profileSubmitButton, false);
  }
});

profileForm.addEventListener("input", updateProfileProgress);
profileForm.addEventListener("change", updateProfileProgress);

passwordForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearPasswordErrors();
  showPasswordMessage("");
  setButtonBusy(passwordSubmitButton, true, { busyLabel: "Сохраняю..." });

  try {
    const data = new FormData(passwordForm);
    const currentPassword = data.get("current_password")?.toString() || "";
    const newPassword = data.get("new_password")?.toString() || "";
    const confirmPassword = data.get("confirm_password")?.toString() || "";

    if (newPassword !== confirmPassword) {
      showPasswordErrors("Новый пароль и повтор не совпадают.");
      return;
    }

    const response = await apiFetch("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });

    const payload = await parsePayload(response);
    if (!response.ok) {
      showPasswordErrors(payload.detail || "Не удалось сменить пароль.");
      redirectIfUnauthorized(response.status);
      return;
    }

    passwordForm.reset();
    showPasswordMessage(payload.message || "Пароль обновлен.");
  } finally {
    setButtonBusy(passwordSubmitButton, false);
  }
});

bindLogout(logoutBtn);
bindDigitsOnly(profileForm, "phone", 7);
serverSwitchModal.bind(serverSwitchCancelBtn);
switchServerBtn?.addEventListener("click", previewServerSwitch);
serverSwitchConfirmBtn?.addEventListener("click", confirmServerSwitch);
loadProfile();
updateProfileProgress();
