window.OGPAdmin = {
  normalizeCode(value) {
    return String(value || "").trim().toLowerCase();
  },

  catalogEndpoint(entityType, itemId = "") {
    const suffix = itemId ? `/${encodeURIComponent(itemId)}` : "";
    return `/api/admin/catalog/${encodeURIComponent(entityType)}${suffix}`;
  },

  withQuery(path, name, value) {
    const normalizedName = String(name || "").trim();
    const normalizedValue = String(value || "").trim();
    if (!normalizedName || !normalizedValue) {
      return path;
    }
    const separator = path.includes("?") ? "&" : "?";
    return `${path}${separator}${encodeURIComponent(normalizedName)}=${encodeURIComponent(normalizedValue)}`;
  },

  buildScopedStorageKey(baseKey, scope) {
    const normalizedBase = String(baseKey || "").trim();
    const normalizedScope = window.OGPAdmin.normalizeCode(scope);
    return normalizedScope ? `${normalizedBase}:${normalizedScope}` : normalizedBase;
  },

  extractErrorMessage(payload, fallback) {
    const detail = payload?.detail;
    if (Array.isArray(detail) && detail.length) {
      return detail.map((item) => String(item || "").trim()).filter(Boolean).join(" ");
    }
    if (typeof detail === "string" && detail.trim()) {
      return detail.trim();
    }
    if (typeof payload?.message === "string" && payload.message.trim()) {
      return payload.message.trim();
    }
    return String(fallback || "").trim();
  },

  formatHttpError(response, payload, fallback) {
    const status = Number(response?.status || 0);
    if (window.OGPWeb?.redirectIfUnauthorized?.(status)) {
      return "Требуется повторный вход в систему.";
    }

    const details = window.OGPAdmin.extractErrorMessage(payload, fallback);
    const requestId = String(response?.headers?.get?.("x-request-id") || "").trim();

    let prefix = "";
    if (status === 403) {
      prefix = "Доступ запрещён.";
    } else if (status === 429) {
      prefix = "Превышен лимит запросов.";
    } else if (status >= 500) {
      prefix = "Ошибка сервера.";
    } else if (status >= 400) {
      prefix = "Ошибка запроса.";
    }

    const parts = [];
    if (prefix) {
      parts.push(prefix);
    }
    if (details) {
      parts.push(details);
    }
    if (status > 0) {
      parts.push(`(HTTP ${status})`);
    }
    if (requestId) {
      parts.push(`[request_id: ${requestId}]`);
    }
    return parts.join(" ").trim();
  },
};
