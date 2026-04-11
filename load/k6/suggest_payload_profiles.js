export const SUGGEST_PAYLOAD_PROFILES = {
  short: {
    victim_name: "Victim Example",
    org: "LSPD",
    subject: "Officer Example",
    event_dt: "08.04.2026 14:30",
    complaint_basis: "wrongful_article",
    main_focus: "neutral_formulation",
    raw_desc:
      "The detainee asked for video review, said the insult claim was inaccurate, and asked to describe the episode neutrally for a complaint draft.",
  },
  mid: {
    victim_name: "Victim Example",
    org: "LSPD",
    subject: "Officer Example",
    event_dt: "08.04.2026 14:30",
    complaint_basis: "wrongful_article",
    main_focus: "neutral_formulation",
    raw_desc:
      "The detainee disputed the officer's wording, requested that bodycam evidence be checked, and explained that the phrase recorded on video did not amount to an actionable insult. The user wants a neutral paragraph for complaint section 3 that keeps facts, avoids escalation, and preserves the request for legal review against the selected server law base.",
  },
  long: {
    victim_name: "Victim Example",
    org: "LSPD",
    subject: "Officer Example",
    event_dt: "08.04.2026 14:30",
    complaint_basis: "wrongful_article",
    main_focus: "neutral_formulation",
    raw_desc:
      "The detainee states that the officer accused him of insulting a government employee, but the detainee denied that qualification and insisted that the exact wording on the available video was different. According to the user, the detainee immediately asked to preserve and review the bodycam or dashcam evidence, pointed out that the disputed phrase was colloquial rather than abusive, and requested that the situation be described neutrally in a formal complaint. The generated text should stay factual, avoid emotional language, reflect the disagreement over legal qualification, mention the request to verify the recording, and fit the current complaint flow used by the service.",
  },
};

export function buildSuggestPayload(profileName) {
  const normalized = String(profileName || "short").trim().toLowerCase();
  const payload = SUGGEST_PAYLOAD_PROFILES[normalized];
  if (!payload) {
    throw new Error(`Unsupported suggest profile: ${profileName}`);
  }
  return JSON.parse(JSON.stringify(payload));
}
