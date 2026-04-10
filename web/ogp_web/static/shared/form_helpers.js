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
};
