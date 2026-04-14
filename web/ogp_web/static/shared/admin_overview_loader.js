window.OGPAdminOverviewLoader = {
  createAdminOverviewLoader(deps = {}) {
    const apiFetch = deps.apiFetch || window.OGPWeb?.apiFetch;
    const parsePayload = deps.parsePayload || window.OGPWeb?.parsePayload;
    const formatHttpError = deps.formatHttpError || window.OGPAdmin?.formatHttpError;

    return {
      async load({ silent = false } = {}) {
        if (!silent) {
          deps.setStateIdle?.(deps.errorsHost);
          deps.clearMessage?.();
          deps.showOverviewLoading?.();
        } else {
          deps.setLiveStatus?.("Live: updating...", "info");
        }

        try {
          const response = await apiFetch(deps.buildOverviewUrl());
          if (!response.ok) {
            const payload = await parsePayload(response);
            if (!silent) {
              deps.setStateError?.(
                deps.errorsHost,
                formatHttpError(response, payload, "Failed to load admin overview."),
              );
            } else {
              deps.setLiveStatus?.("Live: refresh failed", "danger");
            }
            return;
          }

          const payload = await parsePayload(response);
          deps.renderActiveFilters?.(deps.currentFilters());
          deps.renderTotals?.(payload.totals || {});
          deps.renderModelPolicy?.(payload.model_policy || {});
          deps.renderCostSummary?.(payload.totals || {});
          deps.renderExamImport?.(payload.exam_import || null);
          deps.renderTopEndpoints?.(payload.top_endpoints || []);
          deps.renderSynthetic?.(payload.synthetic || {});
          deps.renderUsers?.(payload.users || [], payload.filters?.user_sort || "complaints");
          deps.renderErrorExplorer?.(payload.error_explorer || null);
          deps.renderAdminAudit?.(payload.recent_events || []);
          deps.renderEvents?.(payload.recent_events || []);

          const partialErrors = Array.isArray(payload.partial_errors) ? payload.partial_errors : [];
          if (partialErrors.length && !silent) {
            const first = partialErrors[0] || {};
            const source = first.source ? `[${String(first.source)}] ` : "";
            const message = String(first.message || "").trim();
            deps.setStateError?.(
              deps.errorsHost,
              `Panel loaded partially (${partialErrors.length}). ${source}${message}`.trim(),
            );
          }

          const selectedUser = deps.getSelectedUser?.();
          const userIndex = deps.userIndex;
          if (selectedUser && userIndex?.has?.(String(selectedUser).toLowerCase())) {
            deps.renderUserModal?.(userIndex.get(String(selectedUser).toLowerCase()));
          }

          if (silent) {
            deps.setLiveStatus?.(
              `Live: synced ${new Date().toLocaleTimeString("ru-RU")}`,
              "success-soft",
            );
          }
        } catch (error) {
          if (!silent) {
            deps.setStateError?.(
              deps.errorsHost,
              error?.message || "Failed to load admin overview.",
            );
          } else {
            deps.setLiveStatus?.("Live: refresh failed", "danger");
          }
        }
      },
    };
  },
};
