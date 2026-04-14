window.OGPAdminLawRuntimeController = {
  createAdminLawRuntimeController(deps = {}) {
    return {
      async fetchRuntimeServersPayload() {
        const response = await deps.apiFetch?.("/api/admin/runtime-servers");
        const payload = await deps.parsePayload?.(response);
        if (!response?.ok) {
          deps.setRuntimeServerItems?.([]);
          deps.renderServerSetupWorkflow?.();
          return { response, payload };
        }
        const items = Array.isArray(payload?.items) ? payload.items : [];
        deps.setRuntimeServerItems?.(items);
        return { response, payload };
      },

      syncLawServerOptionsFromRuntimeServers() {
        const runtimeServerItems = deps.getRuntimeServerItems?.() || [];
        const lawServerOptions = runtimeServerItems
          .filter((item) => item && String(item.code || "").trim())
          .map((item) => ({
            code: String(item.code || "").trim().toLowerCase(),
            title: String(item.title || "").trim(),
            is_active: Boolean(item.is_active),
          }));
        deps.setLawServerOptions?.(lawServerOptions);
        const activeLawServerCode = String(deps.getActiveLawServerCode?.() || "").trim().toLowerCase();
        if (!activeLawServerCode) {
          const firstActive = lawServerOptions.find((item) => item.is_active);
          if (firstActive?.code) {
            deps.setActiveLawServerCode?.(firstActive.code);
          } else if (lawServerOptions[0]?.code) {
            deps.setActiveLawServerCode?.(lawServerOptions[0].code);
          }
        }
      },

      getActiveRuntimeServer() {
        const activeLawServerCode = String(deps.getActiveLawServerCode?.() || "").trim().toLowerCase();
        const runtimeServerItems = deps.getRuntimeServerItems?.() || [];
        return runtimeServerItems.find(
          (item) => String(item?.code || "").trim().toLowerCase() === activeLawServerCode,
        ) || null;
      },

      renderServerSetupWorkflow() {
        const host = document.getElementById("server-setup-workflow-host");
        if (!host) {
          return;
        }
        const lawSetOptions = deps.getLawSetOptions?.() || [];
        const serverLawBindingItems = deps.getServerLawBindingItems?.() || [];
        const runtimeServerItems = deps.getRuntimeServerItems?.() || [];
        const publishedLawSet = lawSetOptions.find((item) => item?.is_published);
        const activeLawSet = lawSetOptions.find((item) => item?.is_active) || publishedLawSet || null;
        const bindingCount = Array.isArray(serverLawBindingItems) ? serverLawBindingItems.length : 0;
        host.innerHTML = deps.renderServerSetupWorkflowMarkup?.({
          server: this.getActiveRuntimeServer(),
          activeLawServerCode: deps.getActiveLawServerCode?.(),
          runtimeServerItems,
          activeLawSet,
          bindingCount,
          runtimeServerHealth: deps.getRuntimeServerHealth?.(),
        }) || "";
      },

      async loadRuntimeServerHealth({ silent = true } = {}) {
        const activeLawServerCode = String(deps.getActiveLawServerCode?.() || "").trim().toLowerCase();
        if (!activeLawServerCode) {
          deps.setRuntimeServerHealth?.(null);
          this.renderServerSetupWorkflow();
          return null;
        }
        try {
          const response = await deps.apiFetch?.(`/api/admin/runtime-servers/${encodeURIComponent(activeLawServerCode)}/health`);
          const payload = await deps.parsePayload?.(response);
          if (!response?.ok) {
            deps.setRuntimeServerHealth?.(null);
            if (!silent) {
              deps.setStateError?.(
                deps.errorsHost,
                deps.formatHttpError?.(response, payload, "Failed to load runtime server health."),
              );
            }
            this.renderServerSetupWorkflow();
            return null;
          }
          deps.setRuntimeServerHealth?.(payload);
          this.renderServerSetupWorkflow();
          return payload;
        } catch (error) {
          deps.setRuntimeServerHealth?.(null);
          if (!silent) {
            deps.setStateError?.(deps.errorsHost, error?.message || "Failed to load runtime server health.");
          }
          this.renderServerSetupWorkflow();
          return null;
        }
      },

      renderLawSets(payload) {
        const host = document.getElementById("law-sets-host");
        if (!host) {
          return;
        }
        const items = Array.isArray(payload?.items) ? payload.items : [];
        deps.setLawSetOptions?.(items);
        this.renderServerSetupWorkflow();
        host.innerHTML = deps.renderLawSetsTable?.(items) || "";
      },

      async loadLawSets() {
        const host = document.getElementById("law-sets-host");
        const activeLawServerCode = String(deps.getActiveLawServerCode?.() || "").trim().toLowerCase();
        if (!host || !activeLawServerCode) {
          deps.setLawSetOptions?.([]);
          deps.setRuntimeServerHealth?.(null);
          this.renderServerSetupWorkflow();
          return;
        }
        const response = await deps.apiFetch?.(`/api/admin/runtime-servers/${encodeURIComponent(activeLawServerCode)}/law-sets`);
        const payload = await deps.parsePayload?.(response);
        if (!response?.ok) {
          deps.setLawSetOptions?.([]);
          this.renderServerSetupWorkflow();
          host.innerHTML = `<p class="legal-section__description">${deps.escapeHtml?.(
            deps.formatHttpError?.(response, payload, "Failed to load law sets."),
          )}</p>`;
          return;
        }
        this.renderLawSets(payload);
        await this.loadRuntimeServerHealth();
      },

      renderServerLawBindings(payload) {
        const host = document.getElementById("server-law-bindings-host");
        if (!host) {
          return;
        }
        const items = Array.isArray(payload?.items) ? payload.items.filter((row) => row?.item_id) : [];
        deps.setServerLawBindingItems?.(items);
        this.renderServerSetupWorkflow();
        host.innerHTML = deps.renderServerLawBindingsTable?.(items) || "";
      },

      async loadServerLawBindings() {
        const host = document.getElementById("server-law-bindings-host");
        const activeLawServerCode = String(deps.getActiveLawServerCode?.() || "").trim().toLowerCase();
        if (!host || !activeLawServerCode) {
          deps.setServerLawBindingItems?.([]);
          deps.setRuntimeServerHealth?.(null);
          this.renderServerSetupWorkflow();
          return;
        }
        const response = await deps.apiFetch?.(`/api/admin/runtime-servers/${encodeURIComponent(activeLawServerCode)}/law-bindings`);
        const payload = await deps.parsePayload?.(response);
        if (!response?.ok) {
          deps.setServerLawBindingItems?.([]);
          this.renderServerSetupWorkflow();
          host.innerHTML = `<p class="legal-section__description">${deps.escapeHtml?.(
            deps.formatHttpError?.(response, payload, "Failed to load server law bindings."),
          )}</p>`;
          return;
        }
        this.renderServerLawBindings(payload);
        await this.loadRuntimeServerHealth();
      },

      parseLawSetItemsInput(raw) {
        const rows = String(raw || "")
          .split(/\r?\n/)
          .map((line) => String(line || "").trim())
          .filter(Boolean);
        return rows.map((line, index) => {
          const [lawCode, sourceIdRaw, priorityRaw, effectiveFromRaw] = line
            .split("|")
            .map((part) => String(part || "").trim());
          if (!lawCode) {
            throw new Error(`Line ${index + 1}: law_code is required.`);
          }
          const sourceId = Number(sourceIdRaw || 0);
          const priority = Number(priorityRaw || 100);
          return {
            law_code: lawCode,
            source_id: Number.isFinite(sourceId) && sourceId > 0 ? sourceId : null,
            priority: Number.isFinite(priority) ? priority : 100,
            effective_from: effectiveFromRaw || "",
          };
        });
      },

      async createLawSetFlow() {
        const activeLawServerCode = String(deps.getActiveLawServerCode?.() || "").trim().toLowerCase();
        if (!activeLawServerCode) {
          deps.setStateError?.(deps.errorsHost, "Select a server first.");
          return;
        }
        const name = String(window.prompt("Law set name", `${activeLawServerCode}-default`) || "").trim();
        if (!name) {
          return;
        }
        const rawItems = String(
          window.prompt(
            "Items, one per line: law_code|source_id|priority|effective_from",
            "",
          ) || "",
        );
        let items = [];
        try {
          items = rawItems ? this.parseLawSetItemsInput(rawItems) : [];
        } catch (error) {
          deps.setStateError?.(deps.errorsHost, String(error?.message || error));
          return;
        }
        const response = await deps.apiFetch?.(`/api/admin/runtime-servers/${encodeURIComponent(activeLawServerCode)}/law-sets`, {
          method: "POST",
          body: JSON.stringify({ name, is_active: true, items }),
        });
        const payload = await deps.parsePayload?.(response);
        if (!response?.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Failed to create law set."));
          return;
        }
        deps.showMessage?.(`Law set created: ${name}.`);
        await this.loadLawSets();
      },

      async editLawSetFlow(lawSetId, currentName, currentIsActive) {
        const name = String(window.prompt("Law set name", currentName || "") || "").trim();
        if (!name) {
          return;
        }
        const rawItems = String(
          window.prompt(
            "Items, one per line: law_code|source_id|priority|effective_from",
            "",
          ) || "",
        );
        let items = [];
        try {
          items = rawItems ? this.parseLawSetItemsInput(rawItems) : [];
        } catch (error) {
          deps.setStateError?.(deps.errorsHost, String(error?.message || error));
          return;
        }
        const response = await deps.apiFetch?.(`/api/admin/law-sets/${encodeURIComponent(String(lawSetId))}`, {
          method: "PUT",
          body: JSON.stringify({ name, is_active: currentIsActive, items }),
        });
        const payload = await deps.parsePayload?.(response);
        if (!response?.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Failed to update law set."));
          return;
        }
        deps.showMessage?.(`Law set #${lawSetId} updated.`);
        await this.loadLawSets();
      },

      async publishLawSetFlow(lawSetId) {
        const response = await deps.apiFetch?.(`/api/admin/law-sets/${encodeURIComponent(String(lawSetId))}/publish`, { method: "POST" });
        const payload = await deps.parsePayload?.(response);
        if (!response?.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Failed to publish law set."));
          return;
        }
        deps.showMessage?.(`Law set #${lawSetId} published.`);
        await this.loadLawSets();
      },

      async rebuildLawSetFlow(lawSetId) {
        const dryRun = window.confirm("Dry-run? OK = preview only, Cancel = apply.");
        const response = await deps.apiFetch?.(`/api/admin/law-sets/${encodeURIComponent(String(lawSetId))}/rebuild`, {
          method: "POST",
          body: JSON.stringify({ dry_run: dryRun }),
        });
        const payload = await deps.parsePayload?.(response);
        if (payload?.result?.dry_run) {
          deps.showMessage?.(`Dry-run completed. Articles: ${String(payload?.result?.article_count || 0)}.`);
          await deps.loadLawSourcesManager?.();
          await deps.loadLawJobsOverview?.();
          return;
        }
        if (!response?.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Failed to rebuild law set."));
          return;
        }
        deps.showMessage?.(`Law set #${lawSetId} rebuilt. Version: ${String(payload?.result?.law_version_id || "n/a")}.`);
        await deps.loadLawSourcesManager?.();
        await deps.loadLawJobsOverview?.();
      },

      async rollbackLawSetFlow(lawSetId) {
        const versionRaw = String(window.prompt("Target law version ID (optional)", "") || "").trim();
        const lawVersionId = versionRaw ? Number(versionRaw) : null;
        const response = await deps.apiFetch?.(`/api/admin/law-sets/${encodeURIComponent(String(lawSetId))}/rollback`, {
          method: "POST",
          body: JSON.stringify({ law_version_id: Number.isFinite(lawVersionId) ? lawVersionId : null }),
        });
        const payload = await deps.parsePayload?.(response);
        if (!response?.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Failed to rollback law set."));
          return;
        }
        deps.showMessage?.(
          `Rollback completed. Active version: ${String(payload?.result?.active_law_version_id || "none")}.`,
        );
        await deps.loadLawSourcesManager?.();
        await deps.loadLawJobsOverview?.();
      },

      async loadLawServerOptions() {
        const catalogHost = deps.getCatalogHost?.();
        if (!catalogHost || deps.getActiveCatalogEntity?.() !== "laws") {
          return;
        }
        const { response } = await this.fetchRuntimeServersPayload();
        if (!response?.ok) {
          deps.setLawServerOptions?.([]);
          deps.setRuntimeServerHealth?.(null);
          this.renderServerSetupWorkflow();
          return;
        }
        this.syncLawServerOptionsFromRuntimeServers();
        deps.renderLawServerSelector?.();
        this.renderServerSetupWorkflow();
        await this.loadRuntimeServerHealth();
      },

      renderRuntimeServersPanel(payload) {
        const host = document.getElementById("runtime-servers-host");
        const items = Array.isArray(payload?.items) ? payload.items : [];
        deps.setRuntimeServerItems?.(items);
        this.syncLawServerOptionsFromRuntimeServers();
        deps.renderLawServerSelector?.();
        this.renderServerSetupWorkflow();
        if (!host) {
          return;
        }
        host.innerHTML = deps.renderRuntimeServersTable?.(items) || "";
      },

      async loadRuntimeServersPanel() {
        const host = document.getElementById("runtime-servers-host");
        const { response, payload } = await this.fetchRuntimeServersPayload();
        if (!response?.ok) {
          this.renderServerSetupWorkflow();
          if (!host) {
            return;
          }
          host.innerHTML = `<p class="legal-section__description">${deps.escapeHtml?.(
            deps.formatHttpError?.(response, payload, "Failed to load runtime servers."),
          )}</p>`;
          return;
        }
        this.renderRuntimeServersPanel(payload);
        await this.loadRuntimeServerHealth();
      },

      async createRuntimeServerFlow() {
        const code = String(window.prompt("Введите код сервера (латиница/цифры/_-.)", "") || "").trim().toLowerCase();
        if (!code) {
          return;
        }
        const title = String(window.prompt("Название сервера", code) || "").trim();
        if (!title) {
          return;
        }
        const response = await deps.apiFetch?.("/api/admin/runtime-servers", {
          method: "POST",
          body: JSON.stringify({ code, title }),
        });
        const payload = await deps.parsePayload?.(response);
        if (!response?.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Failed to create runtime server."));
          return;
        }
        deps.setActiveLawServerCode?.(code);
        deps.showMessage?.(`Runtime server created: ${code}.`);
        await this.loadRuntimeServersPanel();
        await this.loadLawServerOptions();
        await this.loadLawSets();
        await this.loadServerLawBindings();
      },

      async editRuntimeServerFlow(code, currentTitle) {
        const title = String(window.prompt(`Server title for ${code}`, currentTitle || code) || "").trim();
        if (!title) {
          return;
        }
        const response = await deps.apiFetch?.(`/api/admin/runtime-servers/${encodeURIComponent(code)}`, {
          method: "PUT",
          body: JSON.stringify({ code, title }),
        });
        const payload = await deps.parsePayload?.(response);
        if (!response?.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Failed to update runtime server."));
          return;
        }
        deps.showMessage?.(`Runtime server updated: ${code}.`);
        await this.loadRuntimeServersPanel();
      },

      async toggleRuntimeServerFlow(code, isActive) {
        const action = isActive ? "deactivate" : "activate";
        const response = await deps.apiFetch?.(`/api/admin/runtime-servers/${encodeURIComponent(code)}/${action}`, {
          method: "POST",
        });
        const payload = await deps.parsePayload?.(response);
        if (!response?.ok) {
          deps.setStateError?.(deps.errorsHost, deps.formatHttpError?.(response, payload, "Failed to toggle runtime server."));
          return;
        }
        deps.showMessage?.(`Runtime server state changed: ${code}.`);
        await this.loadRuntimeServersPanel();
        this.renderServerSetupWorkflow();
      },

      async loadCatalogContext() {
        await this.loadLawServerOptions();
        await deps.loadLawSourcesManager?.();
        await this.loadLawSets();
        await deps.loadLawSourceRegistry?.();
        await this.loadServerLawBindings();
        await deps.loadLawJobsOverview?.();
      },

      async handleCatalogChange(target) {
        if (!(target instanceof HTMLElement)) {
          return false;
        }
        if (target.id === "catalog-entity") {
          await deps.loadCatalog?.(String(target.value || "servers"));
          return true;
        }
        if (target.id === "law-sources-server-select") {
          deps.setActiveLawServerCode?.(String(target.value || "").trim().toLowerCase());
          await deps.loadLawSourcesManager?.();
          await this.loadLawSets();
          await this.loadServerLawBindings();
          return true;
        }
        return false;
      },

      async handleCatalogClick(target) {
        if (!(target instanceof HTMLElement)) {
          return false;
        }
        if (target.id === "runtime-servers-refresh" || target.id === "workflow-refresh-runtime") {
          await this.loadRuntimeServersPanel();
          return true;
        }
        if (target.id === "runtime-servers-create" || target.id === "workflow-create-server") {
          await this.createRuntimeServerFlow();
          return true;
        }
        if (target.id === "workflow-create-law-set" || target.id === "law-sets-create") {
          await this.createLawSetFlow();
          return true;
        }
        if (target.id === "workflow-refresh-law-sets" || target.id === "law-sets-refresh") {
          await this.loadLawSets();
          return true;
        }
        if (target.id === "workflow-add-binding" || target.id === "server-law-bindings-add") {
          await deps.addServerLawBindingFlow?.();
          return true;
        }
        if (target.id === "workflow-refresh-bindings" || target.id === "server-law-bindings-refresh") {
          await this.loadServerLawBindings();
          return true;
        }
        if (target.id === "workflow-activate-server") {
          const activeServer = this.getActiveRuntimeServer();
          if (activeServer && !activeServer.is_active) {
            await this.toggleRuntimeServerFlow(String(activeServer.code || ""), false);
          }
          return true;
        }
        if (target.id === "workflow-open-server-panel") {
          await deps.loadCatalog?.("servers");
          return true;
        }
        if (target.id === "workflow-check-health" || target.id === "workflow-refresh-health") {
          await this.loadRuntimeServerHealth({ silent: false });
          return true;
        }

        const runtimeEditCode = target.getAttribute("data-runtime-server-edit");
        if (runtimeEditCode) {
          const currentTitle = String(target.getAttribute("data-runtime-server-title") || runtimeEditCode);
          await this.editRuntimeServerFlow(runtimeEditCode, currentTitle);
          return true;
        }
        const runtimeToggleCode = target.getAttribute("data-runtime-server-toggle");
        if (runtimeToggleCode) {
          const activeRaw = String(target.getAttribute("data-runtime-server-active") || "0");
          await this.toggleRuntimeServerFlow(runtimeToggleCode, activeRaw === "1");
          return true;
        }
        if (target.id === "law-sources-sync") {
          await deps.syncLawSourcesFromServerConfig?.();
          return true;
        }
        if (target.id === "law-sources-rebuild") {
          await deps.rebuildLawSources?.();
          return true;
        }
        if (target.id === "law-sources-rebuild-async") {
          await deps.rebuildLawSourcesAsync?.();
          return true;
        }
        if (target.id === "law-sources-save") {
          await deps.saveLawSourcesManifest?.();
          return true;
        }
        if (target.id === "law-sources-preview") {
          await deps.previewLawSources?.();
          return true;
        }
        if (target.id === "law-source-registry-refresh") {
          await deps.loadLawSourceRegistry?.();
          return true;
        }
        if (target.id === "law-source-registry-create") {
          await deps.createLawSourceRegistryFlow?.();
          return true;
        }
        if (target.id === "law-jobs-refresh") {
          await deps.loadLawJobsOverview?.();
          return true;
        }

        const lawSetEditId = target.getAttribute("data-law-set-edit");
        if (lawSetEditId) {
          const currentName = String(target.getAttribute("data-law-set-name") || "");
          const currentIsActive = String(target.getAttribute("data-law-set-active") || "1") === "1";
          await this.editLawSetFlow(lawSetEditId, currentName, currentIsActive);
          return true;
        }
        const lawSetPublishId = target.getAttribute("data-law-set-publish");
        if (lawSetPublishId) {
          await this.publishLawSetFlow(lawSetPublishId);
          return true;
        }
        const lawSetRebuildId = target.getAttribute("data-law-set-rebuild");
        if (lawSetRebuildId) {
          await this.rebuildLawSetFlow(lawSetRebuildId);
          return true;
        }
        const lawSetRollbackId = target.getAttribute("data-law-set-rollback");
        if (lawSetRollbackId) {
          await this.rollbackLawSetFlow(lawSetRollbackId);
          return true;
        }

        const lawSourceEditId = target.getAttribute("data-law-source-edit");
        if (lawSourceEditId) {
          const currentName = String(target.getAttribute("data-law-source-name") || "");
          const currentKind = String(target.getAttribute("data-law-source-kind") || "url");
          const currentUrl = String(target.getAttribute("data-law-source-url") || "");
          const currentActive = String(target.getAttribute("data-law-source-active") || "1") === "1";
          await deps.editLawSourceRegistryFlow?.(lawSourceEditId, currentName, currentKind, currentUrl, currentActive);
          return true;
        }

        return false;
      },
    };
  },
};
