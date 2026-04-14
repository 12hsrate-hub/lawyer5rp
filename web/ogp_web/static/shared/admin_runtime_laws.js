window.OGPAdminRuntimeLaws = {
  renderWorkflowStep({ title, status, detail, actionHtml = "", tone = "pending" }) {
    const toneClass = tone === "done" ? "admin-workflow-step--done" : tone === "warning" ? "admin-workflow-step--warning" : "";
    const badgeClass = tone === "done" ? "admin-badge--success" : tone === "warning" ? "admin-badge--warning" : "admin-badge--muted";
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    return `
      <article class="admin-workflow-step ${toneClass}">
        <div class="admin-workflow-step__top">
          <strong>${escapeHtml(title)}</strong>
          <span class="admin-badge ${badgeClass}">${escapeHtml(status)}</span>
        </div>
        <p class="legal-section__description">${escapeHtml(detail)}</p>
        ${actionHtml ? `<div class="admin-section-toolbar">${actionHtml}</div>` : ""}
      </article>
    `;
  },

  renderServerSetupWorkflow({
    server,
    activeLawServerCode,
    runtimeServerItems,
    activeLawSet,
    bindingCount,
    runtimeServerHealth,
  }) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    const serverTitle = String(server?.title || activeLawServerCode || "вЂ”").trim();
    const runtimeCount = Array.isArray(runtimeServerItems) ? runtimeServerItems.length : 0;
    const summary = runtimeServerHealth?.summary || {};
    const checks = runtimeServerHealth?.checks || {};
    const readyCount = Number(summary.ready_count || 0);
    const totalCount = Number(summary.total_count || 5);
    const healthOk = Boolean(checks.health?.ok);
    const healthDetail = healthOk
      ? `Version ${String(checks.health?.active_law_version_id || "-")}, chunks ${String(checks.health?.chunk_count || 0)}.`
      : String(checks.health?.detail || "Run health verification after binding and activation.");

    return `
      <div class="admin-catalog-preview">
        <div class="admin-catalog-preview__header">
          <h4 class="admin-catalog-preview__title">Р‘С‹СЃС‚СЂС‹Р№ СЃС†РµРЅР°СЂРёР№: СЃРµСЂРІРµСЂ в†’ Р·Р°РєРѕРЅС‹ в†’ Р°РєС‚РёРІР°С†РёСЏ</h4>
          <span class="admin-badge ${readyCount === totalCount ? "admin-badge--success" : "admin-badge--muted"}">${escapeHtml(`${readyCount}/${totalCount}`)}</span>
        </div>
        <p class="legal-section__description">${escapeHtml(
          server
            ? `РЎРµСЂРІРµСЂ ${serverTitle} (${String(server.code || "").trim().toLowerCase()}) РїРѕРґРіРѕС‚РѕРІР»РµРЅ РЅР° ${readyCount}/${totalCount} С€Р°РіРѕРІ.`
            : "РЎРЅР°С‡Р°Р»Р° СЃРѕР·РґР°Р№С‚Рµ РёР»Рё РІС‹Р±РµСЂРёС‚Рµ runtime-СЃРµСЂРІРµСЂ, Р·Р°С‚РµРј РїСЂРѕР№РґРёС‚Рµ С€Р°РіРё РїРѕРґРіРѕС‚РѕРІРєРё.",
        )}</p>
        <div class="admin-workflow-grid">
          ${window.OGPAdminRuntimeLaws.renderWorkflowStep({
            title: "1. РЎРµСЂРІРµСЂ",
            status: server ? "РІС‹Р±СЂР°РЅ" : "РЅРµ РІС‹Р±СЂР°РЅ",
            detail: server ? `${serverTitle}. РЎС‚Р°С‚СѓСЃ: ${server.is_active ? "active" : "disabled"}.` : "РЎРѕР·РґР°Р№С‚Рµ РЅРѕРІС‹Р№ runtime-СЃРµСЂРІРµСЂ РёР»Рё РІС‹Р±РµСЂРёС‚Рµ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёР№ РІ СЃРµР»РµРєС‚РѕСЂРµ РІС‹С€Рµ.",
            tone: server ? "done" : "warning",
            actionHtml: `
              <button type="button" id="workflow-create-server" class="primary-button">РЎРѕР·РґР°С‚СЊ СЃРµСЂРІРµСЂ</button>
              <button type="button" id="workflow-refresh-runtime" class="ghost-button">РћР±РЅРѕРІРёС‚СЊ СЃРїРёСЃРѕРє</button>
            `,
          })}
          ${window.OGPAdminRuntimeLaws.renderWorkflowStep({
            title: "2. РќР°Р±РѕСЂ Р·Р°РєРѕРЅРѕРІ",
            status: activeLawSet ? "РіРѕС‚РѕРІ" : "РїСѓСЃС‚Рѕ",
            detail: activeLawSet
              ? `РќР°Р№РґРµРЅ РЅР°Р±РѕСЂ "${String(activeLawSet.name || "вЂ”")}" (${activeLawSet.is_published ? "published" : "draft"}).`
              : "РЎРѕР·РґР°Р№С‚Рµ С…РѕС‚СЏ Р±С‹ РѕРґРёРЅ РЅР°Р±РѕСЂ Р·Р°РєРѕРЅРѕРІ РґР»СЏ РІС‹Р±СЂР°РЅРЅРѕРіРѕ СЃРµСЂРІРµСЂР°.",
            tone: activeLawSet ? "done" : "warning",
            actionHtml: `
              <button type="button" id="workflow-create-law-set" class="primary-button" ${server ? "" : "disabled"}>РЎРѕР·РґР°С‚СЊ РЅР°Р±РѕСЂ</button>
              <button type="button" id="workflow-refresh-law-sets" class="ghost-button" ${server ? "" : "disabled"}>РћР±РЅРѕРІРёС‚СЊ РЅР°Р±РѕСЂС‹</button>
            `,
          })}
          ${window.OGPAdminRuntimeLaws.renderWorkflowStep({
            title: "3. РџСЂРёРІСЏР·РєР° Р·Р°РєРѕРЅР°",
            status: bindingCount > 0 ? `${bindingCount} РїСЂРёРІСЏР·РѕРє` : "РЅРµС‚ РїСЂРёРІСЏР·РѕРє",
            detail: bindingCount > 0
              ? "Р•СЃС‚СЊ СЃРІСЏР·Р°РЅРЅС‹Рµ Р·Р°РєРѕРЅС‹ РґР»СЏ РІС‹Р±СЂР°РЅРЅРѕРіРѕ СЃРµСЂРІРµСЂР°."
              : "РџСЂРёРІСЏР¶РёС‚Рµ С…РѕС‚СЏ Р±С‹ РѕРґРёРЅ Р·Р°РєРѕРЅ Рє СЃРµСЂРІРµСЂСѓ С‡РµСЂРµР· РІС‹Р±РѕСЂ РёР· СЂРµРµСЃС‚СЂР° Рё РЅР°Р±РѕСЂРѕРІ.",
            tone: bindingCount > 0 ? "done" : "warning",
            actionHtml: `
              <button type="button" id="workflow-add-binding" class="primary-button" ${server ? "" : "disabled"}>РџСЂРёРІСЏР·Р°С‚СЊ Р·Р°РєРѕРЅ</button>
              <button type="button" id="workflow-refresh-bindings" class="ghost-button" ${server ? "" : "disabled"}>РћР±РЅРѕРІРёС‚СЊ РїСЂРёРІСЏР·РєРё</button>
            `,
          })}
          ${window.OGPAdminRuntimeLaws.renderWorkflowStep({
            title: "4. РђРєС‚РёРІР°С†РёСЏ",
            status: server?.is_active ? "active" : "disabled",
            detail: server
              ? (server.is_active ? "РЎРµСЂРІРµСЂ Р°РєС‚РёРІРµРЅ Рё РјРѕР¶РµС‚ РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊСЃСЏ РІ runtime." : "РџРѕСЃР»Рµ РїРѕРґРіРѕС‚РѕРІРєРё РІРєР»СЋС‡РёС‚Рµ СЃРµСЂРІРµСЂ.")
              : "РЁР°Рі СЃС‚Р°РЅРµС‚ РґРѕСЃС‚СѓРїРµРЅ РїРѕСЃР»Рµ РІС‹Р±РѕСЂР° РёР»Рё СЃРѕР·РґР°РЅРёСЏ СЃРµСЂРІРµСЂР°.",
            tone: server?.is_active ? "done" : "warning",
            actionHtml: `
              <button type="button" id="workflow-activate-server" class="primary-button" ${server ? "" : "disabled"}>${server?.is_active ? "РЎРµСЂРІРµСЂ СѓР¶Рµ Р°РєС‚РёРІРµРЅ" : "РђРєС‚РёРІРёСЂРѕРІР°С‚СЊ СЃРµСЂРІРµСЂ"}</button>
              <button type="button" id="workflow-open-server-panel" class="ghost-button" ${runtimeCount ? "" : "disabled"}>РџРѕРєР°Р·Р°С‚СЊ СЃРµСЂРІРµСЂС‹</button>
            `,
          })}
          ${window.OGPAdminRuntimeLaws.renderWorkflowStep({
            title: "5. Health",
            status: healthOk ? "ok" : "pending",
            detail: healthDetail,
            tone: healthOk ? "done" : "warning",
            actionHtml: `
              <button type="button" id="workflow-check-health" class="primary-button" ${server ? "" : "disabled"}>Check health</button>
              <button type="button" id="workflow-refresh-health" class="ghost-button" ${server ? "" : "disabled"}>Refresh health</button>
            `,
          })}
        </div>
        <p class="legal-field__hint">Health verification checks whether the server has an active indexed law version.</p>
      </div>
    `;
  },

  renderLawSetsTable(items) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    return `
      <table class="legal-table admin-table admin-table--compact">
        <thead><tr><th>ID</th><th>РќР°Р·РІР°РЅРёРµ</th><th>РЎС‚Р°С‚СѓСЃ</th><th>РџСѓР±Р»РёРєР°С†РёСЏ</th><th>Р­Р»РµРјРµРЅС‚РѕРІ</th><th>Р”РµР№СЃС‚РІРёСЏ</th></tr></thead>
        <tbody>
          ${items.length ? items.map((item) => `
            <tr>
              <td>${escapeHtml(String(item.id || "вЂ”"))}</td>
              <td>${escapeHtml(String(item.name || "вЂ”"))}</td>
              <td>${item.is_active ? "active" : "disabled"}</td>
              <td>${item.is_published ? "published" : "draft"}</td>
              <td>${escapeHtml(String(item.item_count || 0))}</td>
              <td>
                <button type="button" class="ghost-button" data-law-set-edit="${escapeHtml(String(item.id || ""))}" data-law-set-name="${escapeHtml(String(item.name || ""))}" data-law-set-active="${item.is_active ? "1" : "0"}">РР·РјРµРЅРёС‚СЊ</button>
                <button type="button" class="ghost-button" data-law-set-publish="${escapeHtml(String(item.id || ""))}">РћРїСѓР±Р»РёРєРѕРІР°С‚СЊ</button>
                <button type="button" class="ghost-button" data-law-set-rebuild="${escapeHtml(String(item.id || ""))}">Rebuild</button>
                <button type="button" class="ghost-button" data-law-set-rollback="${escapeHtml(String(item.id || ""))}">Rollback</button>
              </td>
            </tr>
          `).join("") : '<tr><td colspan="6" class="legal-section__description">РќР°Р±РѕСЂС‹ Р·Р°РєРѕРЅРѕРІ РїРѕРєР° РЅРµ СЃРѕР·РґР°РЅС‹.</td></tr>'}
        </tbody>
      </table>
    `;
  },

  renderServerLawBindingsTable(items) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    return `
      <table class="legal-table admin-table admin-table--compact">
        <thead><tr><th>Law set</th><th>Law code</th><th>Source</th><th>Priority</th><th>Effective from</th></tr></thead>
        <tbody>
          ${items.length ? items.map((item) => `
            <tr>
              <td>${escapeHtml(String(item.law_set_name || item.law_set_id || "вЂ”"))}</td>
              <td>${escapeHtml(String(item.law_code || "вЂ”"))}</td>
              <td>${escapeHtml(String(item.source_name || item.source_url || "вЂ”"))}</td>
              <td>${escapeHtml(String(item.priority || 0))}</td>
              <td>${escapeHtml(String(item.effective_from || "вЂ”"))}</td>
            </tr>
          `).join("") : '<tr><td colspan="5" class="legal-section__description">Р”Р»СЏ РІС‹Р±СЂР°РЅРЅРѕРіРѕ СЃРµСЂРІРµСЂР° РїРѕРєР° РЅРµС‚ РїСЂРёРІСЏР·Р°РЅРЅС‹С… Р·Р°РєРѕРЅРѕРІ.</td></tr>'}
        </tbody>
      </table>
    `;
  },

  renderRuntimeServersTable(items) {
    const escapeHtml = window.OGPWeb?.escapeHtml || ((value) => String(value ?? ""));
    return `
      <table class="legal-table admin-table admin-table--compact">
        <thead>
          <tr><th>РљРѕРґ</th><th>РќР°Р·РІР°РЅРёРµ</th><th>РЎС‚Р°С‚СѓСЃ</th><th>Р”РµР№СЃС‚РІРёСЏ</th></tr>
        </thead>
        <tbody>
          ${items.length
            ? items.map((item) => `
              <tr>
                <td>${escapeHtml(String(item.code || "вЂ”"))}</td>
                <td>${escapeHtml(String(item.title || "вЂ”"))}</td>
                <td>${item.is_active ? "active" : "disabled"}</td>
                <td>
                  <button type="button" class="ghost-button" data-runtime-server-edit="${escapeHtml(String(item.code || ""))}" data-runtime-server-title="${escapeHtml(String(item.title || ""))}">РР·РјРµРЅРёС‚СЊ</button>
                  <button type="button" class="ghost-button" data-runtime-server-toggle="${escapeHtml(String(item.code || ""))}" data-runtime-server-active="${item.is_active ? "1" : "0"}">${item.is_active ? "Р”РµР°РєС‚РёРІРёСЂРѕРІР°С‚СЊ" : "РђРєС‚РёРІРёСЂРѕРІР°С‚СЊ"}</button>
                </td>
              </tr>
            `).join("")
            : '<tr><td colspan="4" class="legal-section__description">РЎРµСЂРІРµСЂС‹ РЅРµ РЅР°Р№РґРµРЅС‹.</td></tr>'}
        </tbody>
      </table>
    `;
  },
};
