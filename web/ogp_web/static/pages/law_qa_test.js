const form = document.getElementById("law-qa-form");
const messageBox = document.getElementById("law-qa-message");
const errorsBox = document.getElementById("law-qa-errors");
const resultField = document.getElementById("law-qa-result");
const debugHost = document.getElementById("law-qa-debug");
const debugMeta = document.getElementById("law-qa-debug-meta");
const debugList = document.getElementById("law-qa-debug-list");

function setMessage(message) {
  if (!messageBox) return;
  messageBox.textContent = message || "";
  messageBox.hidden = !message;
}

function setErrors(errors) {
  if (!errorsBox) return;
  const list = Array.isArray(errors) ? errors.filter(Boolean) : [];
  errorsBox.textContent = "";
  list.forEach((item) => {
    const row = document.createElement("div");
    row.textContent = String(item);
    errorsBox.appendChild(row);
  });
  errorsBox.hidden = list.length === 0;
}

function clearDebug() {
  if (debugMeta) {
    debugMeta.textContent = "";
  }
  if (debugList) {
    debugList.innerHTML = "";
  }
  if (debugHost) {
    debugHost.hidden = true;
  }
}

function renderDebug(data) {
  const items = Array.isArray(data?.selected_norms) ? data.selected_norms.filter(Boolean) : [];
  if (!debugHost || !debugMeta || !debugList) {
    return;
  }
  if (!items.length) {
    clearDebug();
    return;
  }

  debugMeta.textContent =
    `Профиль: ${data?.retrieval_profile || "-"} · ` +
    `уверенность: ${data?.retrieval_confidence || "-"} · ` +
    `норм выбрано: ${items.length}`;
  debugList.innerHTML = "";

  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "legal-subcard legal-subcard--compact";

    const title = document.createElement("strong");
    title.className = "legal-subcard__title";
    title.textContent = `${item.article_label || "Норма"} · score ${Number(item.score || 0)}`;

    const doc = document.createElement("div");
    doc.className = "legal-subcard__description";
    doc.textContent = item.document_title || "";

    const preview = document.createElement("p");
    preview.className = "legal-subcard__description";
    preview.textContent = item.excerpt_preview || "";

    const link = document.createElement("a");
    link.className = "legal-inline-link";
    link.href = item.source_url || "#";
    link.target = "_blank";
    link.rel = "noreferrer noopener";
    link.textContent = item.source_url || "";

    card.appendChild(title);
    if (doc.textContent) card.appendChild(doc);
    if (preview.textContent) card.appendChild(preview);
    if (item.source_url) card.appendChild(link);
    debugList.appendChild(card);
  });

  debugHost.hidden = false;
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage("");
  setErrors([]);
  clearDebug();
  if (resultField) resultField.value = "";

  const submitButton = form.querySelector("button[type='submit']");
  submitButton?.setAttribute("disabled", "disabled");
  try {
    const payload = {
      server_code: document.getElementById("law-server-code")?.value?.trim() || "",
      model: document.getElementById("law-model")?.value?.trim() || "",
      question: document.getElementById("law-question")?.value?.trim() || "",
      max_answer_chars: Number(document.getElementById("max-answer-chars")?.value || 2200),
    };
    const response = await window.OGPWeb.apiFetch("/api/ai/law-qa-test", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      setErrors(data.detail || ["Не удалось получить ответ."]);
      return;
    }
    const sources = Array.isArray(data.used_sources) && data.used_sources.length
      ? `\n\nИсточники:\n${data.used_sources.join("\n")}`
      : "";
    if (resultField) resultField.value = `${data.text || ""}${sources}`.trim();
    renderDebug(data);
    setMessage(
      `Готово. Проиндексировано документов: ${Number(data.indexed_documents || 0)}. ` +
      `Уверенность retrieval: ${data.retrieval_confidence || "-"}.`
    );
  } catch (error) {
    setErrors([error instanceof Error ? error.message : "Неизвестная ошибка"]);
    clearDebug();
  } finally {
    submitButton?.removeAttribute("disabled");
  }
});
