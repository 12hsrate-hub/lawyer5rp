window.OGPAdminActions = {
  createAdminActionsController(deps = {}) {
    const apiFetch = deps.apiFetch || window.OGPWeb?.apiFetch;
    const parsePayload = deps.parsePayload || window.OGPWeb?.parsePayload;
    const formatHttpError = deps.formatHttpError || window.OGPAdmin?.formatHttpError;

    let pendingAction = null;

    function resetActionModalFields() {
      pendingAction = null;
      if (deps.actionReasonInput) deps.actionReasonInput.value = "";
      if (deps.actionEmailInput) deps.actionEmailInput.value = "";
      if (deps.actionPasswordInput) deps.actionPasswordInput.value = "";
      if (deps.actionQuotaInput) deps.actionQuotaInput.value = "";
      if (deps.actionReasonField) deps.actionReasonField.hidden = true;
      if (deps.actionEmailField) deps.actionEmailField.hidden = true;
      if (deps.actionPasswordField) deps.actionPasswordField.hidden = true;
      if (deps.actionQuotaField) deps.actionQuotaField.hidden = true;
      if (deps.actionConfirmButton) deps.actionConfirmButton.textContent = "Confirm";
      deps.setStateIdle?.(deps.actionModalErrors);
    }

    function openActionModal(config) {
      pendingAction = config;
      if (deps.actionModalTitle) {
        deps.actionModalTitle.textContent = config.title || "Action confirmation";
      }
      if (deps.actionModalDescription) {
        deps.actionModalDescription.textContent = config.description || "";
      }
      if (deps.actionConfirmButton) {
        deps.actionConfirmButton.textContent = config.confirmLabel || "Confirm";
      }
      if (deps.actionReasonField) {
        deps.actionReasonField.hidden = !config.askReason;
      }
      if (deps.actionEmailField) {
        deps.actionEmailField.hidden = !config.askEmail;
      }
      if (deps.actionPasswordField) {
        deps.actionPasswordField.hidden = !config.askPassword;
      }
      if (deps.actionQuotaField) {
        deps.actionQuotaField.hidden = !config.askQuota;
      }
      if (deps.actionEmailInput && config.defaultEmail) {
        deps.actionEmailInput.value = String(config.defaultEmail);
      }
      if (deps.actionReasonInput && config.defaultReason) {
        deps.actionReasonInput.value = String(config.defaultReason);
      }
      if (deps.actionQuotaInput && config.defaultQuota !== undefined) {
        deps.actionQuotaInput.value = String(config.defaultQuota);
      }
      deps.setStateIdle?.(deps.actionModalErrors);
      deps.actionModal?.open?.();
    }

    function closeActionModal() {
      deps.actionModal?.close?.();
      resetActionModalFields();
    }

    async function performAdminAction(url, successText, body = null) {
      deps.setStateIdle?.(deps.errorsHost);
      deps.clearMessage?.();
      try {
        const response = await apiFetch(url, {
          method: "POST",
          body: body ? JSON.stringify(body) : null,
        });
        if (!response.ok) {
          const payload = await parsePayload(response);
          deps.setStateError?.(
            deps.errorsHost,
            formatHttpError(response, payload, "Failed to run admin action."),
          );
          return false;
        }
        deps.showMessage?.(successText);
        await deps.loadAdminOverview?.();
        return true;
      } catch (error) {
        deps.setStateError?.(deps.errorsHost, error?.message || "Failed to run admin action.");
        return false;
      }
    }

    async function handleTarget(target) {
      const verifyUsername = target.getAttribute("data-verify-email");
      if (verifyUsername) {
        await performAdminAction(`/api/admin/users/${encodeURIComponent(verifyUsername)}/verify-email`, "Email user verified.");
        return true;
      }

      const unblockUsername = target.getAttribute("data-unblock-user");
      if (unblockUsername) {
        await performAdminAction(`/api/admin/users/${encodeURIComponent(unblockUsername)}/unblock`, "User access restored.");
        return true;
      }

      const blockUsername = target.getAttribute("data-block-user");
      if (blockUsername) {
        openActionModal({
          action: "block-user",
          username: blockUsername,
          askReason: true,
          title: "Block user",
          description: `Block user ${blockUsername}. Add a reason if needed.`,
          confirmLabel: "Block",
        });
        return true;
      }

      const grantTesterUsername = target.getAttribute("data-grant-tester");
      if (grantTesterUsername) {
        await performAdminAction(`/api/admin/users/${encodeURIComponent(grantTesterUsername)}/grant-tester`, "Tester status granted.");
        return true;
      }

      const revokeTesterUsername = target.getAttribute("data-revoke-tester");
      if (revokeTesterUsername) {
        await performAdminAction(`/api/admin/users/${encodeURIComponent(revokeTesterUsername)}/revoke-tester`, "Tester status removed.");
        return true;
      }

      const grantGkaUsername = target.getAttribute("data-grant-gka");
      if (grantGkaUsername) {
        await performAdminAction(`/api/admin/users/${encodeURIComponent(grantGkaUsername)}/grant-gka`, "GKA type granted.");
        return true;
      }

      const revokeGkaUsername = target.getAttribute("data-revoke-gka");
      if (revokeGkaUsername) {
        await performAdminAction(`/api/admin/users/${encodeURIComponent(revokeGkaUsername)}/revoke-gka`, "GKA type removed.");
        return true;
      }

      const changeEmailUsername = target.getAttribute("data-change-email");
      if (changeEmailUsername) {
        openActionModal({
          action: "change-email",
          username: changeEmailUsername,
          askEmail: true,
          defaultEmail: target.getAttribute("data-current-email") || "",
          title: "Change email",
          description: `Set a new email for ${changeEmailUsername}.`,
          confirmLabel: "Save email",
        });
        return true;
      }

      const resetPasswordUsername = target.getAttribute("data-reset-password");
      if (resetPasswordUsername) {
        openActionModal({
          action: "reset-password",
          username: resetPasswordUsername,
          askPassword: true,
          title: "Reset password",
          description: `Enter a new password for ${resetPasswordUsername}.`,
          confirmLabel: "Change password",
        });
        return true;
      }

      const deactivateUsername = target.getAttribute("data-deactivate-user");
      if (deactivateUsername) {
        openActionModal({
          action: "deactivate-user",
          username: deactivateUsername,
          askReason: true,
          title: "Deactivate account",
          description: `User ${deactivateUsername} will be soft-deactivated.`,
          confirmLabel: "Deactivate",
        });
        return true;
      }

      const reactivateUsername = target.getAttribute("data-reactivate-user");
      if (reactivateUsername) {
        await performAdminAction(`/api/admin/users/${encodeURIComponent(reactivateUsername)}/reactivate`, "Account reactivated.");
        return true;
      }

      const setQuotaUsername = target.getAttribute("data-set-quota");
      if (setQuotaUsername) {
        openActionModal({
          action: "set-daily-quota",
          username: setQuotaUsername,
          askQuota: true,
          defaultQuota: target.getAttribute("data-current-quota") || "0",
          title: "Daily API quota",
          description: `Set the daily API request limit for ${setQuotaUsername}.`,
          confirmLabel: "Save quota",
        });
        return true;
      }

      return false;
    }

    async function submitPendingAction() {
      if (!pendingAction) {
        return;
      }
      deps.setStateIdle?.(deps.actionModalErrors);
      const action = pendingAction.action;
      const username = String(pendingAction.username || "");

      if (action === "block-user") {
        const reason = String(deps.actionReasonInput?.value || "").trim();
        if (await performAdminAction(`/api/admin/users/${encodeURIComponent(username)}/block`, "User access blocked.", { reason })) {
          closeActionModal();
        }
        return;
      }

      if (action === "change-email") {
        const email = String(deps.actionEmailInput?.value || "").trim();
        if (!email) {
          deps.setStateError?.(deps.actionModalErrors, "Enter a new email.");
          return;
        }
        if (await performAdminAction(`/api/admin/users/${encodeURIComponent(username)}/email`, "User email updated.", { email })) {
          closeActionModal();
        }
        return;
      }

      if (action === "reset-password") {
        const password = String(deps.actionPasswordInput?.value || "").trim();
        if (!password) {
          deps.setStateError?.(deps.actionModalErrors, "Enter a new password.");
          return;
        }
        if (password.length < 10) {
          deps.setStateError?.(deps.actionModalErrors, "Password must be at least 10 characters.");
          return;
        }
        if (await performAdminAction(`/api/admin/users/${encodeURIComponent(username)}/reset-password`, "User password updated.", { password })) {
          closeActionModal();
        }
        return;
      }

      if (action === "deactivate-user") {
        const reason = String(deps.actionReasonInput?.value || "").trim();
        if (await performAdminAction(`/api/admin/users/${encodeURIComponent(username)}/deactivate`, "User account deactivated.", { reason })) {
          closeActionModal();
        }
        return;
      }

      if (action === "set-daily-quota") {
        const quota = Number(deps.actionQuotaInput?.value || 0);
        if (!Number.isFinite(quota) || quota < 0) {
          deps.setStateError?.(deps.actionModalErrors, "Quota must be a non-negative number.");
          return;
        }
        if (await performAdminAction(`/api/admin/users/${encodeURIComponent(username)}/daily-quota`, "Quota updated.", { daily_limit: quota })) {
          closeActionModal();
        }
      }
    }

    return {
      close: closeActionModal,
      handleTarget,
      open: openActionModal,
      performAction: performAdminAction,
      reset: resetActionModalFields,
      submitPendingAction,
    };
  },
};
