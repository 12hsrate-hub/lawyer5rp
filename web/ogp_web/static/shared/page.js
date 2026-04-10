window.OGPPage = {
  showOptionalText(host, text) {
    if (!text) {
      window.OGPWeb.clearText(host);
      return;
    }
    window.OGPWeb.showText(host, text);
  },

  bindLogout(button, { message = "Вы вышли из аккаунта." } = {}) {
    if (!button) {
      return;
    }
    button.addEventListener("click", async () => {
      await window.OGPWeb.apiFetch("/api/auth/logout", { method: "POST" });
      sessionStorage.setItem("ogp_auth_message", message);
      location.href = "/login";
    });
  },
};
