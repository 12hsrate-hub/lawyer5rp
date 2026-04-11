window.OGPForm = {
  addDynamicField({ template, targetId, value = "", onChange }) {
    const host = document.getElementById(targetId);
    const node = template.content.firstElementChild.cloneNode(true);
    const input = node.querySelector("input");
    input.value = value;
    input.dataset.group = targetId;
    node.querySelector(".remove-field").addEventListener("click", () => {
      node.remove();
      onChange?.();
    });
    host.appendChild(node);
  },

  bindDynamicAddButtons({ onChange, addDynamicField }) {
    document.querySelectorAll("[data-add]").forEach((button) => {
      button.addEventListener("click", () => {
        addDynamicField(button.dataset.add || "");
        onChange?.();
      });
    });
  },

  collectGroup(groupName) {
    return Array.from(document.querySelectorAll(`input[data-group="${groupName}"]`))
      .map((input) => input.value.trim())
      .filter(Boolean);
  },

  setFieldValue(form, name, value) {
    const field = form.elements.namedItem(name);
    if (field) {
      field.value = value || "";
    }
  },

  bindDigitsOnly(form, fieldName, maxLength) {
    const field = form.elements.namedItem(fieldName);
    if (!field) {
      return;
    }
    field.addEventListener("input", () => {
      field.value = field.value.replace(/\D/g, "").slice(0, maxLength);
    });
  },

  setGroupValues({ template, targetId, values, onChange }) {
    const host = document.getElementById(targetId);
    host.innerHTML = "";
    const rows = Array.isArray(values) && values.length ? values : [""];
    rows.forEach((value) => {
      window.OGPForm.addDynamicField({ template, targetId, value, onChange });
    });
  },

  formatTodayDate() {
    const now = new Date();
    const day = String(now.getDate()).padStart(2, "0");
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const year = String(now.getFullYear());
    return `${day}.${month}.${year}`;
  },

  setCurrentDate(form) {
    const todayField = form.elements.namedItem("today_date");
    if (!todayField || todayField.value.trim()) {
      return;
    }
    todayField.value = window.OGPForm.formatTodayDate();
  },

  toServerDateTime(value) {
    const raw = (value || "").trim();
    if (!raw) {
      return "";
    }
    const [datePart, timePart] = raw.split("T");
    if (!datePart || !timePart) {
      return raw;
    }
    const [year, month, day] = datePart.split("-");
    return `${day}.${month}.${year} ${timePart}`;
  },

  toInputDateTime(value) {
    const raw = (value || "").trim();
    if (!raw) {
      return "";
    }
    if (raw.includes("T")) {
      return raw.slice(0, 16);
    }
    const match = raw.match(/^(\d{2})\.(\d{2})\.(\d{4}) (\d{2}:\d{2})$/);
    if (!match) {
      return raw;
    }
    const [, day, month, year, time] = match;
    return `${year}-${month}-${day}T${time}`;
  },

  parseJsonScript(scriptElement) {
    if (!scriptElement) {
      return null;
    }
    try {
      return JSON.parse(scriptElement.textContent || "{}");
    } catch {
      return null;
    }
  },

  updateFieldValidationState(field) {
    if (
      !field ||
      !(field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement || field instanceof HTMLSelectElement)
    ) {
      return;
    }
    const touched = field.dataset.ogpTouched === "true";
    const value = String(field.value || "").trim();
    const hasValue = value !== "";
    const isRequired = field.required;
    const isValid = field.checkValidity();
    const shouldShowInvalid = touched && !isValid;

    field.classList.toggle("is-dirty", touched || hasValue);
    field.classList.toggle("is-valid", (touched || hasValue) && isValid);
    field.classList.toggle("is-invalid", shouldShowInvalid);
    field.setAttribute("aria-invalid", shouldShowInvalid ? "true" : "false");

    const host = field.closest(".legal-field, label, .inline-field");
    if (host instanceof HTMLElement) {
      host.classList.toggle("has-invalid", shouldShowInvalid);
      host.classList.toggle("has-valid", (touched || hasValue) && isValid);
    }
  },

  bindValidationState(form) {
    if (!(form instanceof HTMLFormElement)) {
      return;
    }

    const fields = [...form.querySelectorAll("input, textarea, select")];
    fields.forEach((field) => {
      if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement || field instanceof HTMLSelectElement) {
        if (field.disabled || field.type === "hidden") {
          return;
        }
        window.OGPForm.updateFieldValidationState(field);
      }
    });

    form.addEventListener("focusout", (event) => {
      const field = event.target;
      if (!(field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement || field instanceof HTMLSelectElement)) {
        return;
      }
      if (field.disabled || field.type === "hidden") {
        return;
      }
      field.dataset.ogpTouched = "true";
      window.OGPForm.updateFieldValidationState(field);
    });

    form.addEventListener("input", (event) => {
      const field = event.target;
      if (!(field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement || field instanceof HTMLSelectElement)) {
        return;
      }
      if (field.disabled || field.type === "hidden") {
        return;
      }
      window.OGPForm.updateFieldValidationState(field);
    });

    form.addEventListener("change", (event) => {
      const field = event.target;
      if (!(field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement || field instanceof HTMLSelectElement)) {
        return;
      }
      if (field.disabled || field.type === "hidden") {
        return;
      }
      field.dataset.ogpTouched = "true";
      window.OGPForm.updateFieldValidationState(field);
    });
  },

  setButtonBusy(button, busy, options = {}) {
    if (!(button instanceof HTMLButtonElement || button instanceof HTMLAnchorElement)) {
      return;
    }
    const busyLabel = options.busyLabel || "Подождите...";
    const defaultLabel = options.defaultLabel || button.dataset.ogpDefaultLabel || button.textContent || "";

    if (!button.dataset.ogpDefaultLabel) {
      button.dataset.ogpDefaultLabel = String(defaultLabel).trim();
    }

    const shouldDisable = button instanceof HTMLButtonElement;
    button.classList.toggle("is-loading", Boolean(busy));
    button.setAttribute("aria-busy", busy ? "true" : "false");
    if (shouldDisable) {
      button.disabled = Boolean(busy);
    }
    button.textContent = busy ? String(busyLabel) : button.dataset.ogpDefaultLabel;
  },
};

document.querySelectorAll("form").forEach((form) => {
  window.OGPForm.bindValidationState(form);
});
