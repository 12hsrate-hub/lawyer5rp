function createFormSnapshot(form) {
  return new FormData(form);
}

function readString(data, fieldName, fallback = "") {
  return data.get(fieldName)?.toString().trim() || fallback;
}

window.OGPComplaintPayload = {
  createFormSnapshot,
  readString,

  createPresetState(preset) {
    if (!preset) {
      return null;
    }
    return {
      appeal_no: preset.appeal_no || "",
      org: preset.org || "",
      subject_names: preset.subject_names || "",
      event_dt: preset.event_dt || "",
      today_date: "",
      victim_name: preset.victim_name || "",
      victim_passport: preset.victim_passport || "",
      victim_address: preset.victim_address || "-",
      victim_phone: preset.victim_phone || "",
      victim_discord: preset.victim_discord || "",
      victim_scan: preset.victim_scan || "",
      complaint_basis: preset.complaint_basis || "",
      main_focus: preset.main_focus || "",
      situation_description: preset.situation_description || "",
      violation_short: preset.violation_short || "",
      contract_url: preset.contract_url || "",
      bar_request_url: preset.bar_request_url || "",
      official_answer_url: preset.official_answer_url || "",
      mail_notice_url: preset.mail_notice_url || "",
      arrest_record_url: preset.arrest_record_url || "",
      personnel_file_url: preset.personnel_file_url || "",
      video_fix_urls: preset.video_fix_urls || [],
      provided_video_urls: preset.provided_video_urls || [],
      result: "",
    };
  },

  applyState({ form, resultHost, template, state, onChange }) {
    if (!state || typeof state !== "object") {
      return;
    }

    window.OGPForm.setFieldValue(form, "appeal_no", state.appeal_no);
    window.OGPForm.setFieldValue(form, "org", state.org);
    window.OGPForm.setFieldValue(form, "subject_names", state.subject_names);
    window.OGPForm.setFieldValue(form, "event_dt", window.OGPForm.toInputDateTime(state.event_dt));
    window.OGPForm.setFieldValue(form, "today_date", state.today_date);
    window.OGPForm.setFieldValue(form, "victim_name", state.victim_name);
    window.OGPForm.setFieldValue(form, "victim_passport", state.victim_passport);
    window.OGPForm.setFieldValue(form, "victim_address", state.victim_address);
    window.OGPForm.setFieldValue(form, "victim_phone", state.victim_phone);
    window.OGPForm.setFieldValue(form, "victim_discord", state.victim_discord);
    window.OGPForm.setFieldValue(form, "victim_scan", state.victim_scan);
    window.OGPForm.setFieldValue(form, "complaint_basis", state.complaint_basis);
    window.OGPForm.setFieldValue(form, "main_focus", state.main_focus);
    window.OGPForm.setFieldValue(form, "situation_description", state.situation_description);
    window.OGPForm.setFieldValue(form, "violation_short", state.violation_short);
    window.OGPForm.setFieldValue(form, "contract_url", state.contract_url);
    window.OGPForm.setFieldValue(form, "bar_request_url", state.bar_request_url);
    window.OGPForm.setFieldValue(form, "official_answer_url", state.official_answer_url);
    window.OGPForm.setFieldValue(form, "mail_notice_url", state.mail_notice_url);
    window.OGPForm.setFieldValue(form, "arrest_record_url", state.arrest_record_url);
    window.OGPForm.setFieldValue(form, "personnel_file_url", state.personnel_file_url);
    window.OGPForm.setGroupValues({ template, targetId: "video_fix_urls", values: state.video_fix_urls, onChange });
    window.OGPForm.setGroupValues({ template, targetId: "provided_video_urls", values: state.provided_video_urls, onChange });
    resultHost.value = state.result || "";
  },

  collectDraftState({ form, resultHost }) {
    const data = createFormSnapshot(form);
    return {
      appeal_no: readString(data, "appeal_no"),
      org: readString(data, "org"),
      subject_names: readString(data, "subject_names"),
      event_dt: readString(data, "event_dt"),
      today_date: readString(data, "today_date"),
      victim_name: readString(data, "victim_name"),
      victim_passport: readString(data, "victim_passport"),
      victim_address: readString(data, "victim_address", "-"),
      victim_phone: readString(data, "victim_phone"),
      victim_discord: readString(data, "victim_discord"),
      victim_scan: readString(data, "victim_scan"),
      complaint_basis: readString(data, "complaint_basis"),
      main_focus: readString(data, "main_focus"),
      situation_description: data.get("situation_description")?.toString() || "",
      violation_short: data.get("violation_short")?.toString() || "",
      contract_url: readString(data, "contract_url"),
      bar_request_url: readString(data, "bar_request_url"),
      official_answer_url: readString(data, "official_answer_url"),
      mail_notice_url: readString(data, "mail_notice_url"),
      arrest_record_url: readString(data, "arrest_record_url"),
      personnel_file_url: readString(data, "personnel_file_url"),
      video_fix_urls: window.OGPForm.collectGroup("video_fix_urls"),
      provided_video_urls: window.OGPForm.collectGroup("provided_video_urls"),
      result: resultHost.value || "",
    };
  },

  buildPayload({ form, presetPayload }) {
    const data = createFormSnapshot(form);
    return {
      appeal_no: readString(data, "appeal_no"),
      org: readString(data, "org"),
      subject_names: readString(data, "subject_names"),
      situation_description: data.get("situation_description")?.toString() || "",
      violation_short: data.get("violation_short")?.toString() || "",
      event_dt: window.OGPForm.toServerDateTime(readString(data, "event_dt")),
      today_date: readString(data, "today_date"),
      representative: presetPayload?.representative || null,
      victim: {
        name: readString(data, "victim_name"),
        passport: readString(data, "victim_passport"),
        address: readString(data, "victim_address", "-"),
        phone: readString(data, "victim_phone"),
        discord: readString(data, "victim_discord"),
        passport_scan_url: readString(data, "victim_scan"),
      },
      contract_url: readString(data, "contract_url"),
      bar_request_url: readString(data, "bar_request_url"),
      official_answer_url: readString(data, "official_answer_url"),
      mail_notice_url: readString(data, "mail_notice_url"),
      arrest_record_url: readString(data, "arrest_record_url"),
      personnel_file_url: readString(data, "personnel_file_url"),
      video_fix_urls: window.OGPForm.collectGroup("video_fix_urls"),
      provided_video_urls: window.OGPForm.collectGroup("provided_video_urls"),
    };
  },
};
