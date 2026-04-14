function createFormSnapshot(form) {
  return new FormData(form);
}

function readString(data, fieldName, fallback = "") {
  return data.get(fieldName)?.toString().trim() || fallback;
}

const SEMANTIC_KEYS = {
  appealNo: "meta.appeal_number",
  org: "context.organization",
  subjectNames: "context.subject_names",
  eventDt: "incident.datetime",
  todayDate: "meta.today_date",
  victimName: "victim.full_name",
  victimPassport: "victim.passport",
  victimAddress: "victim.address",
  victimPhone: "victim.phone",
  victimDiscord: "victim.discord",
  victimScan: "victim.passport_scan_url",
  complaintBasis: "incident.complaint_basis",
  mainFocus: "incident.main_focus",
  situationDescription: "incident.description",
  violationShort: "incident.violation_summary",
  contractUrl: "evidence.contract_url",
  barRequestUrl: "evidence.bar_request_url",
  officialAnswerUrl: "evidence.official_answer_url",
  mailNoticeUrl: "evidence.mail_notice_url",
  arrestRecordUrl: "evidence.arrest_record_url",
  personnelFileUrl: "evidence.personnel_file_url",
  videoFixUrls: "evidence.video_fix_urls",
  providedVideoUrls: "evidence.provided_video_urls",
  result: "draft.result",
};

const LEGACY_TO_SEMANTIC = {
  appeal_no: SEMANTIC_KEYS.appealNo,
  org: SEMANTIC_KEYS.org,
  subject_names: SEMANTIC_KEYS.subjectNames,
  event_dt: SEMANTIC_KEYS.eventDt,
  today_date: SEMANTIC_KEYS.todayDate,
  victim_name: SEMANTIC_KEYS.victimName,
  victim_passport: SEMANTIC_KEYS.victimPassport,
  victim_address: SEMANTIC_KEYS.victimAddress,
  victim_phone: SEMANTIC_KEYS.victimPhone,
  victim_discord: SEMANTIC_KEYS.victimDiscord,
  victim_scan: SEMANTIC_KEYS.victimScan,
  complaint_basis: SEMANTIC_KEYS.complaintBasis,
  main_focus: SEMANTIC_KEYS.mainFocus,
  situation_description: SEMANTIC_KEYS.situationDescription,
  violation_short: SEMANTIC_KEYS.violationShort,
  contract_url: SEMANTIC_KEYS.contractUrl,
  bar_request_url: SEMANTIC_KEYS.barRequestUrl,
  official_answer_url: SEMANTIC_KEYS.officialAnswerUrl,
  mail_notice_url: SEMANTIC_KEYS.mailNoticeUrl,
  arrest_record_url: SEMANTIC_KEYS.arrestRecordUrl,
  personnel_file_url: SEMANTIC_KEYS.personnelFileUrl,
  video_fix_urls: SEMANTIC_KEYS.videoFixUrls,
  provided_video_urls: SEMANTIC_KEYS.providedVideoUrls,
  result: SEMANTIC_KEYS.result,
};

function getStateValue(state, semanticKey, legacyKey, fallback = "") {
  if (!state || typeof state !== "object") {
    return fallback;
  }
  if (state[semanticKey] !== undefined && state[semanticKey] !== null) {
    return state[semanticKey];
  }
  if (legacyKey && state[legacyKey] !== undefined && state[legacyKey] !== null) {
    return state[legacyKey];
  }
  return fallback;
}

window.OGPComplaintPayload = {
  createFormSnapshot,
  readString,

  createPresetState(preset) {
    if (!preset) {
      return null;
    }
    return {
      [SEMANTIC_KEYS.appealNo]: preset.appeal_no || "",
      [SEMANTIC_KEYS.org]: preset.org || "",
      [SEMANTIC_KEYS.subjectNames]: preset.subject_names || "",
      [SEMANTIC_KEYS.eventDt]: preset.event_dt || "",
      [SEMANTIC_KEYS.todayDate]: "",
      [SEMANTIC_KEYS.victimName]: preset.victim_name || "",
      [SEMANTIC_KEYS.victimPassport]: preset.victim_passport || "",
      [SEMANTIC_KEYS.victimAddress]: preset.victim_address || "-",
      [SEMANTIC_KEYS.victimPhone]: preset.victim_phone || "",
      [SEMANTIC_KEYS.victimDiscord]: preset.victim_discord || "",
      [SEMANTIC_KEYS.victimScan]: preset.victim_scan || "",
      [SEMANTIC_KEYS.complaintBasis]: preset.complaint_basis || "",
      [SEMANTIC_KEYS.mainFocus]: preset.main_focus || "",
      [SEMANTIC_KEYS.situationDescription]: preset.situation_description || "",
      [SEMANTIC_KEYS.violationShort]: preset.violation_short || "",
      [SEMANTIC_KEYS.contractUrl]: preset.contract_url || "",
      [SEMANTIC_KEYS.barRequestUrl]: preset.bar_request_url || "",
      [SEMANTIC_KEYS.officialAnswerUrl]: preset.official_answer_url || "",
      [SEMANTIC_KEYS.mailNoticeUrl]: preset.mail_notice_url || "",
      [SEMANTIC_KEYS.arrestRecordUrl]: preset.arrest_record_url || "",
      [SEMANTIC_KEYS.personnelFileUrl]: preset.personnel_file_url || "",
      [SEMANTIC_KEYS.videoFixUrls]: preset.video_fix_urls || [],
      [SEMANTIC_KEYS.providedVideoUrls]: preset.provided_video_urls || [],
      [SEMANTIC_KEYS.result]: "",
    };
  },

  applyState({ form, resultHost, template, state, onChange }) {
    if (!state || typeof state !== "object") {
      return;
    }

    window.OGPForm.setFieldValue(form, "appeal_no", getStateValue(state, SEMANTIC_KEYS.appealNo, "appeal_no"));
    window.OGPForm.setFieldValue(form, "org", getStateValue(state, SEMANTIC_KEYS.org, "org"));
    window.OGPForm.setFieldValue(form, "subject_names", getStateValue(state, SEMANTIC_KEYS.subjectNames, "subject_names"));
    window.OGPForm.setFieldValue(
      form,
      "event_dt",
      window.OGPForm.toInputDateTime(getStateValue(state, SEMANTIC_KEYS.eventDt, "event_dt")),
    );
    window.OGPForm.setFieldValue(form, "today_date", getStateValue(state, SEMANTIC_KEYS.todayDate, "today_date"));
    window.OGPForm.setFieldValue(form, "victim_name", getStateValue(state, SEMANTIC_KEYS.victimName, "victim_name"));
    window.OGPForm.setFieldValue(form, "victim_passport", getStateValue(state, SEMANTIC_KEYS.victimPassport, "victim_passport"));
    window.OGPForm.setFieldValue(form, "victim_address", getStateValue(state, SEMANTIC_KEYS.victimAddress, "victim_address", "-"));
    window.OGPForm.setFieldValue(form, "victim_phone", getStateValue(state, SEMANTIC_KEYS.victimPhone, "victim_phone"));
    window.OGPForm.setFieldValue(form, "victim_discord", getStateValue(state, SEMANTIC_KEYS.victimDiscord, "victim_discord"));
    window.OGPForm.setFieldValue(form, "victim_scan", getStateValue(state, SEMANTIC_KEYS.victimScan, "victim_scan"));
    window.OGPForm.setFieldValue(form, "complaint_basis", getStateValue(state, SEMANTIC_KEYS.complaintBasis, "complaint_basis"));
    window.OGPForm.setFieldValue(form, "main_focus", getStateValue(state, SEMANTIC_KEYS.mainFocus, "main_focus"));
    window.OGPForm.setFieldValue(
      form,
      "situation_description",
      getStateValue(state, SEMANTIC_KEYS.situationDescription, "situation_description"),
    );
    window.OGPForm.setFieldValue(form, "violation_short", getStateValue(state, SEMANTIC_KEYS.violationShort, "violation_short"));
    window.OGPForm.setFieldValue(form, "contract_url", getStateValue(state, SEMANTIC_KEYS.contractUrl, "contract_url"));
    window.OGPForm.setFieldValue(form, "bar_request_url", getStateValue(state, SEMANTIC_KEYS.barRequestUrl, "bar_request_url"));
    window.OGPForm.setFieldValue(
      form,
      "official_answer_url",
      getStateValue(state, SEMANTIC_KEYS.officialAnswerUrl, "official_answer_url"),
    );
    window.OGPForm.setFieldValue(form, "mail_notice_url", getStateValue(state, SEMANTIC_KEYS.mailNoticeUrl, "mail_notice_url"));
    window.OGPForm.setFieldValue(form, "arrest_record_url", getStateValue(state, SEMANTIC_KEYS.arrestRecordUrl, "arrest_record_url"));
    window.OGPForm.setFieldValue(form, "personnel_file_url", getStateValue(state, SEMANTIC_KEYS.personnelFileUrl, "personnel_file_url"));

    window.OGPForm.setGroupValues({
      template,
      targetId: "video_fix_urls",
      values: getStateValue(state, SEMANTIC_KEYS.videoFixUrls, "video_fix_urls", []),
      onChange,
    });
    window.OGPForm.setGroupValues({
      template,
      targetId: "provided_video_urls",
      values: getStateValue(state, SEMANTIC_KEYS.providedVideoUrls, "provided_video_urls", []),
      onChange,
    });
    resultHost.value = getStateValue(state, SEMANTIC_KEYS.result, "result") || "";
  },

  collectDraftState({ form, resultHost }) {
    const data = createFormSnapshot(form);
    return {
      [SEMANTIC_KEYS.appealNo]: readString(data, "appeal_no"),
      [SEMANTIC_KEYS.org]: readString(data, "org"),
      [SEMANTIC_KEYS.subjectNames]: readString(data, "subject_names"),
      [SEMANTIC_KEYS.eventDt]: readString(data, "event_dt"),
      [SEMANTIC_KEYS.todayDate]: readString(data, "today_date"),
      [SEMANTIC_KEYS.victimName]: readString(data, "victim_name"),
      [SEMANTIC_KEYS.victimPassport]: readString(data, "victim_passport"),
      [SEMANTIC_KEYS.victimAddress]: readString(data, "victim_address", "-"),
      [SEMANTIC_KEYS.victimPhone]: readString(data, "victim_phone"),
      [SEMANTIC_KEYS.victimDiscord]: readString(data, "victim_discord"),
      [SEMANTIC_KEYS.victimScan]: readString(data, "victim_scan"),
      [SEMANTIC_KEYS.complaintBasis]: readString(data, "complaint_basis"),
      [SEMANTIC_KEYS.mainFocus]: readString(data, "main_focus"),
      [SEMANTIC_KEYS.situationDescription]: data.get("situation_description")?.toString() || "",
      [SEMANTIC_KEYS.violationShort]: data.get("violation_short")?.toString() || "",
      [SEMANTIC_KEYS.contractUrl]: readString(data, "contract_url"),
      [SEMANTIC_KEYS.barRequestUrl]: readString(data, "bar_request_url"),
      [SEMANTIC_KEYS.officialAnswerUrl]: readString(data, "official_answer_url"),
      [SEMANTIC_KEYS.mailNoticeUrl]: readString(data, "mail_notice_url"),
      [SEMANTIC_KEYS.arrestRecordUrl]: readString(data, "arrest_record_url"),
      [SEMANTIC_KEYS.personnelFileUrl]: readString(data, "personnel_file_url"),
      [SEMANTIC_KEYS.videoFixUrls]: window.OGPForm.collectGroup("video_fix_urls"),
      [SEMANTIC_KEYS.providedVideoUrls]: window.OGPForm.collectGroup("provided_video_urls"),
      [SEMANTIC_KEYS.result]: resultHost.value || "",
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
  LEGACY_TO_SEMANTIC,
};
