window.OGPWeb = {
  async apiFetch(url, options = {}) {
    return fetch(url, {
      credentials: "same-origin",
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
  },

  async parsePayload(response) {
    return response.json().catch(() => ({}));
  },

  showText(host, lines) {
    host.hidden = false;
    host.textContent = Array.isArray(lines) ? lines.join("\n") : String(lines);
  },

  clearText(host) {
    host.hidden = true;
    host.textContent = "";
  },

  escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  },

  setBodyScrollLock(locked) {
    document.body.classList.toggle("modal-open", Boolean(locked));
  },

  redirectIfUnauthorized(statusCode) {
    if (statusCode === 401) {
      location.href = "/login";
      return true;
    }
    return false;
  },

  createModalController({ modal, textHost }) {
    if (!modal) {
      return {
        open() {},
        close() {},
        bind() {},
      };
    }

    const close = () => {
      modal.hidden = true;
      if (textHost) {
        window.OGPWeb.clearText(textHost);
      }
      window.OGPWeb.setBodyScrollLock(false);
    };

    const open = (text = "") => {
      if (textHost) {
        window.OGPWeb.showText(textHost, text);
      }
      modal.hidden = false;
      window.OGPWeb.setBodyScrollLock(true);
    };

    const bind = (...elements) => {
      elements.filter(Boolean).forEach((element) => {
        element.addEventListener("click", close);
      });
      modal.addEventListener("click", (event) => {
        if (event.target === modal) {
          close();
        }
      });
    };

    return { open, close, bind };
  },
};

window.OGPOcr = {
  fileToDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("Не удалось прочитать изображение."));
      reader.readAsDataURL(file);
    });
  },

  wireSingleUsePrincipalOcr(config) {
    const {
      fileInput,
      triggerButton,
      statusHost,
      progressHost,
      progressTextHost,
      clearErrors,
      showErrors,
      applyResult,
      onSuccess,
      readyStatus,
      noFileStatus,
      noFileError,
      processingStatus,
      busyText,
      failureStatus,
      fallbackErrorText,
    } = config;

    if (!fileInput || !triggerButton || !statusHost || !progressHost || !progressTextHost) {
      return { setReady() {} };
    }

    const setStatus = (text) => {
      statusHost.textContent = text;
    };

    const setBusy = (isBusy, text = "") => {
      triggerButton.disabled = isBusy;
      progressHost.hidden = !isBusy;
      progressTextHost.textContent = isBusy ? text : "";
    };

    const run = async () => {
      clearErrors?.();

      const [file] = fileInput.files || [];
      if (!file) {
        setStatus(noFileStatus);
        showErrors?.(noFileError);
        return;
      }

      try {
        setStatus(processingStatus);
        setBusy(true, busyText);
        const imageDataUrl = await window.OGPOcr.fileToDataUrl(file);

        const response = await window.OGPWeb.apiFetch("/api/ai/extract-principal", {
          method: "POST",
          body: JSON.stringify({ image_data_url: imageDataUrl }),
        });

        if (!response.ok) {
          const payload = await window.OGPWeb.parsePayload(response);
          setStatus(failureStatus);
          showErrors?.(payload.detail || fallbackErrorText);
          window.OGPWeb.redirectIfUnauthorized(response.status);
          return;
        }

        const payload = await window.OGPWeb.parsePayload(response);
        applyResult?.(payload);
        setStatus(config.successStatus);
        onSuccess?.(payload);
      } catch (error) {
        setStatus(config.exceptionStatus || failureStatus);
        showErrors?.(error?.message || fallbackErrorText);
      } finally {
        setBusy(false);
      }
    };

    triggerButton.addEventListener("click", run);
    setBusy(false);
    setStatus(readyStatus);

    return {
      setReady() {
        setBusy(false);
        setStatus(readyStatus);
      },
    };
  },

  bindFilePickerLabel({ fileInput, nameHost, emptyText }) {
    if (!fileInput || !nameHost) {
      return {
        refresh() {},
        clear() {},
      };
    }

    const refresh = () => {
      const [file] = fileInput.files || [];
      nameHost.textContent = file?.name || emptyText;
      nameHost.classList.toggle("is-empty", !file);
    };

    const clear = () => {
      fileInput.value = "";
      refresh();
    };

    fileInput.addEventListener("change", refresh);
    fileInput.addEventListener("click", () => {
      fileInput.value = "";
    });

    refresh();
    return { refresh, clear };
  },

  createUiResetter({
    fileInput,
    progressHost,
    progressTextHost,
    statusHost,
    readyStatus,
    closeModal,
    filePicker,
  }) {
    return () => {
      if (fileInput) {
        fileInput.value = "";
      }
      if (progressHost) {
        progressHost.hidden = true;
      }
      if (progressTextHost) {
        progressTextHost.textContent = "";
      }
      if (statusHost) {
        statusHost.textContent = readyStatus;
      }
      closeModal?.();
      filePicker?.refresh?.();
    };
  },
};
