const resetPasswordForm = document.getElementById("reset-password-form");
const resetErrors = document.getElementById("reset-errors");
const { apiFetch, parsePayload, showText, clearText } = window.OGPWeb;

function showResetErrors(lines) {
  showText(resetErrors, lines);
}

function clearResetErrors() {
  clearText(resetErrors);
}

resetPasswordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearResetErrors();

  const data = new FormData(resetPasswordForm);
  const password = data.get("password")?.toString() || "";
  const passwordConfirm = data.get("password_confirm")?.toString() || "";
  if (password !== passwordConfirm) {
    showResetErrors("Пароли не совпадают.");
    return;
  }

  const response = await apiFetch("/api/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({
      token: data.get("token")?.toString() || "",
      password,
    }),
  });

  const payload = await parsePayload(response);
  if (!response.ok) {
    showResetErrors(payload.detail || "Не удалось сохранить новый пароль.");
    return;
  }

  sessionStorage.setItem("ogp_app_message", payload.message || "");
  location.href = "/complaint";
});
