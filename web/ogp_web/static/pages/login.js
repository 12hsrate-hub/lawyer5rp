const loginForm = document.getElementById("login-form");
const registerForm = document.getElementById("register-form");
const resendForm = document.getElementById("resend-form");
const resendToggle = document.getElementById("resend-toggle");
const resendToggleSide = document.getElementById("resend-toggle-side");
const resendCancel = document.getElementById("resend-cancel");
const forgotPasswordForm = document.getElementById("forgot-password-form");
const forgotPasswordToggle = document.getElementById("forgot-password-toggle");
const forgotPasswordToggleSide = document.getElementById("forgot-password-toggle-side");
const forgotPasswordCancel = document.getElementById("forgot-password-cancel");
const successModal = document.getElementById("success-modal");
const successModalText = document.getElementById("success-modal-text");
const successModalClose = document.getElementById("success-modal-close");
const successModalOk = document.getElementById("success-modal-ok");
const errorModal = document.getElementById("error-modal");
const errorModalText = document.getElementById("error-modal-text");
const errorModalClose = document.getElementById("error-modal-close");
const errorModalOk = document.getElementById("error-modal-ok");
const activeSessionCard = document.getElementById("active-session-card");
const activeSessionUsername = document.getElementById("active-session-username");
const activeSessionLogout = document.getElementById("active-session-logout");
const { apiFetch, parsePayload, showText, clearText, setBodyScrollLock } = window.OGPWeb;

function showAuthErrors(lines) {
  showText(errorModalText, lines);
  errorModal.hidden = false;
  setBodyScrollLock(true);
}

function clearAuthErrors() {
  errorModal.hidden = true;
  clearText(errorModalText);
  if (successModal.hidden) {
    setBodyScrollLock(false);
  }
}

function buildSuccessLines(payload, fallback) {
  const lines = [payload.message || fallback];
  if (payload.verification_url) {
    lines.push(`Ссылка: ${payload.verification_url}`);
  }
  return lines;
}

function closeSuccessModal() {
  successModal.hidden = true;
  clearText(successModalText);
  if (errorModal.hidden) {
    setBodyScrollLock(false);
  }
}

function showAuthSuccess(lines) {
  showText(successModalText, lines);
  successModal.hidden = false;
  setBodyScrollLock(true);
}

function setAuthFormsDisabled(disabled) {
  [loginForm, registerForm, resendForm, forgotPasswordForm].forEach((form) => {
    if (!form) {
      return;
    }
    [...form.elements].forEach((element) => {
      element.disabled = disabled;
    });
  });
}

function showActiveSession(username) {
  if (!activeSessionCard || !activeSessionUsername) {
    return;
  }
  activeSessionUsername.textContent = username || "Неизвестный пользователь";
  activeSessionCard.hidden = false;
  setAuthFormsDisabled(true);
}

function hideActiveSession() {
  if (!activeSessionCard || !activeSessionUsername) {
    return;
  }
  activeSessionCard.hidden = true;
  activeSessionUsername.textContent = "";
  setAuthFormsDisabled(false);
}

function hideSupportForms() {
  if (resendForm) {
    resendForm.hidden = true;
  }
  if (forgotPasswordForm) {
    forgotPasswordForm.hidden = true;
  }
}

function openResendForm() {
  hideSupportForms();
  resendForm.hidden = false;
  resendForm.scrollIntoView({ behavior: "smooth", block: "center" });
}

function openForgotPasswordForm() {
  hideSupportForms();
  forgotPasswordForm.hidden = false;
  forgotPasswordForm.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function handleAuthSubmit(event, endpoint) {
  event.preventDefault();
  clearAuthErrors();

  const data = new FormData(event.currentTarget);
  const body = {
    username: data.get("username")?.toString().trim() || "",
    email: data.get("email")?.toString().trim() || "",
    password: data.get("password")?.toString() || "",
  };

  const response = await apiFetch(endpoint, {
    method: "POST",
    body: JSON.stringify(body),
  });

  const payload = await parsePayload(response);
  if (!response.ok) {
    if (endpoint.endsWith("/login")) {
      showAuthErrors(payload.detail || "Вход не выполнен. Проверьте логин или пароль.");
    } else if (endpoint.endsWith("/forgot-password")) {
      showAuthErrors(payload.detail || "Не удалось отправить ссылку для сброса пароля.");
    } else {
      showAuthErrors(payload.detail || "Не удалось зарегистрировать пользователя.");
    }
    return;
  }

  if (endpoint.endsWith("/login")) {
    sessionStorage.setItem("ogp_app_message", payload.message || "");
    location.href = "/complaint";
    return;
  }

  showAuthSuccess(buildSuccessLines(payload, "Проверьте email для завершения действия."));
  event.currentTarget.reset();
}

async function handleResendSubmit(event) {
  event.preventDefault();
  clearAuthErrors();

  const data = new FormData(event.currentTarget);
  const response = await apiFetch("/api/auth/resend-verification", {
    method: "POST",
    body: JSON.stringify({
      email: data.get("email")?.toString().trim() || "",
    }),
  });

  const payload = await parsePayload(response);
  if (!response.ok) {
    showAuthErrors(payload.detail || "Не удалось отправить письмо повторно.");
    return;
  }

  showAuthSuccess(buildSuccessLines(payload, "Письмо с подтверждением отправлено."));
  event.currentTarget.reset();
  resendForm.hidden = true;
}

async function handleForgotPasswordSubmit(event) {
  event.preventDefault();
  clearAuthErrors();

  const data = new FormData(event.currentTarget);
  const response = await apiFetch("/api/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({
      email: data.get("email")?.toString().trim() || "",
    }),
  });

  const payload = await parsePayload(response);
  if (!response.ok) {
    showAuthErrors(payload.detail || "Не удалось отправить ссылку для сброса пароля.");
    return;
  }

  showAuthSuccess(buildSuccessLines(payload, "Инструкция по сбросу пароля отправлена."));
  event.currentTarget.reset();
  forgotPasswordForm.hidden = true;
}

async function bootstrapSession() {
  try {
    const response = await apiFetch("/api/auth/me", { method: "GET", headers: {} });
    if (response.ok) {
      const payload = await parsePayload(response);
      showActiveSession(payload.username || "");
      return;
    }
  } catch {
    // noop
  }

  const remembered = sessionStorage.getItem("ogp_auth_message");
  if (remembered) {
    showAuthSuccess(remembered);
    sessionStorage.removeItem("ogp_auth_message");
  }
}

loginForm.addEventListener("submit", (event) => handleAuthSubmit(event, "/api/auth/login"));
registerForm.addEventListener("submit", (event) => handleAuthSubmit(event, "/api/auth/register"));
resendForm.addEventListener("submit", handleResendSubmit);
forgotPasswordForm.addEventListener("submit", handleForgotPasswordSubmit);

activeSessionLogout?.addEventListener("click", async () => {
  const response = await apiFetch("/api/auth/logout", { method: "POST" });
  if (!response.ok) {
    const payload = await parsePayload(response);
    showAuthErrors(payload.detail || "Не удалось завершить текущую сессию.");
    return;
  }
  hideActiveSession();
});

forgotPasswordToggle?.addEventListener("click", openForgotPasswordForm);
forgotPasswordToggleSide?.addEventListener("click", openForgotPasswordForm);
resendToggle?.addEventListener("click", openResendForm);
resendToggleSide?.addEventListener("click", openResendForm);
forgotPasswordCancel?.addEventListener("click", hideSupportForms);
resendCancel?.addEventListener("click", hideSupportForms);

successModalClose.addEventListener("click", closeSuccessModal);
successModalOk.addEventListener("click", closeSuccessModal);
successModal.addEventListener("click", (event) => {
  if (event.target === successModal) {
    closeSuccessModal();
  }
});

errorModalClose.addEventListener("click", clearAuthErrors);
errorModalOk.addEventListener("click", clearAuthErrors);
errorModal.addEventListener("click", (event) => {
  if (event.target === errorModal) {
    clearAuthErrors();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !successModal.hidden) {
    closeSuccessModal();
  }
  if (event.key === "Escape" && !errorModal.hidden) {
    clearAuthErrors();
  }
});

bootstrapSession();
