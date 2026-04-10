const profileForm = document.getElementById("profile-form");
const profileErrors = document.getElementById("profile-errors");
const profileMessage = document.getElementById("profile-message");
const passwordForm = document.getElementById("password-form");
const passwordErrors = document.getElementById("password-errors");
const passwordMessage = document.getElementById("password-message");
const appMessage = document.getElementById("app-message");
const logoutBtn = document.getElementById("logout-btn");

const { apiFetch, parsePayload, showText, clearText, redirectIfUnauthorized } = window.OGPWeb;
const { showOptionalText, bindLogout } = window.OGPPage;
const bindDigitsOnly = window.OGPForm?.bindDigitsOnly || (() => {});

function showProfileErrors(lines) {
  showText(profileErrors, lines);
}

function clearProfileErrors() {
  clearText(profileErrors);
}

function showProfileMessage(text) {
  showOptionalText(profileMessage, text);
}

function showPasswordErrors(lines) {
  showText(passwordErrors, lines);
}

function clearPasswordErrors() {
  clearText(passwordErrors);
}

function showPasswordMessage(text) {
  showOptionalText(passwordMessage, text);
}

function showAppMessage(text) {
  showOptionalText(appMessage, text);
}

function fillProfileForm(profile) {
  profileForm.elements.namedItem("name").value = profile.name || "";
  profileForm.elements.namedItem("passport").value = profile.passport || "";
  profileForm.elements.namedItem("address").value = profile.address || "";
  profileForm.elements.namedItem("phone").value = profile.phone || "";
  profileForm.elements.namedItem("discord").value = profile.discord || "";
  profileForm.elements.namedItem("passport_scan_url").value = profile.passport_scan_url || "";
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
});

passwordForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearPasswordErrors();
  showPasswordMessage("");

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
});

bindLogout(logoutBtn);
bindDigitsOnly(profileForm, "phone", 7);
loadProfile();
