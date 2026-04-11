const form = document.getElementById("law-qa-form");
const messageBox = document.getElementById("law-qa-message");
const errorsBox = document.getElementById("law-qa-errors");
const resultField = document.getElementById("law-qa-result");
const sourceList = document.getElementById("law-source-list");

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

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage("");
  setErrors([]);
  if (resultField) resultField.value = "";

  const submitButton = form.querySelector("button[type='submit']");
  submitButton?.setAttribute("disabled", "disabled");
  try {
    const payload = {
      server_code: document.getElementById("law-server-code")?.value?.trim() || "blackberry",
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
    setMessage(`Готово. Проиндексировано документов: ${Number(data.indexed_documents || 0)}.`);
  } catch (error) {
    setErrors([error instanceof Error ? error.message : "Неизвестная ошибка"]);
  } finally {
    submitButton?.removeAttribute("disabled");
  }
});

if (sourceList) {
  const initialSources = Array.isArray(window.OGP_LAW_QA_SOURCES) ? window.OGP_LAW_QA_SOURCES : [];
  sourceList.innerHTML = "";
  initialSources.forEach((item) => {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = String(item.url || "");
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = String(item.title || item.url || "");
    li.appendChild(a);
    sourceList.appendChild(li);
  });
}
