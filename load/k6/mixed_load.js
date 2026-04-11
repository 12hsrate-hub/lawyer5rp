import http from "k6/http";
import { check } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { buildSuggestPayload } from "./suggest_payload_profiles.js";

const baseUrl = String(__ENV.BASE_URL || "").replace(/\/+$/, "");
const sessionCookie = String(__ENV.SESSION_COOKIE || "").trim();
const groupAProfile = String(__ENV.GROUP_A_PROFILE || "long").trim().toLowerCase();
const groupAVus = Math.max(0, Number(__ENV.GROUP_A_VUS || 0));
const groupBVus = Math.max(1, Number(__ENV.GROUP_B_VUS || 10));
const duration = String(__ENV.DURATION || "1m").trim();
const summaryPath = String(__ENV.SUMMARY_PATH || "artifacts/load/mixed/summary.json").trim();

if (!baseUrl) {
  throw new Error("BASE_URL is required.");
}
if (!sessionCookie) {
  throw new Error("SESSION_COOKIE is required.");
}

const scenarios = {
  group_b_standard: {
    executor: "constant-vus",
    exec: "groupBStandard",
    vus: groupBVus,
    duration,
  },
};

if (groupAVus > 0) {
  scenarios.group_a_suggest = {
    executor: "constant-vus",
    exec: "groupASuggest",
    vus: groupAVus,
    duration,
  };
}

export const options = {
  scenarios,
  thresholds: {
    checks: ["rate>0.95"],
  },
};

const groupAReqDuration = new Trend("group_a_req_duration");
const groupAOk = new Counter("group_a_ok");
const groupAOverload = new Counter("group_a_overload");
const groupAError = new Counter("group_a_error");

const groupBReqDuration = new Trend("group_b_req_duration");
const groupBReqFailed = new Rate("group_b_req_failed");
const groupBOk = new Counter("group_b_ok");
const groupBError = new Counter("group_b_error");

function buildHeaders({ json = false } = {}) {
  const headers = {
    Cookie: `ogp_web_session=${sessionCookie}`,
  };
  if (json) {
    headers["Content-Type"] = "application/json";
  }
  return headers;
}

function requestGroupB(index) {
  const selector = index % 4;
  if (selector === 0) {
    return {
      name: "auth_me",
      response: http.get(`${baseUrl}/api/auth/me`, {
        headers: buildHeaders(),
        tags: { traffic_group: "group_b", endpoint_name: "auth_me" },
      }),
    };
  }
  if (selector === 1) {
    return {
      name: "profile_get",
      response: http.get(`${baseUrl}/api/profile`, {
        headers: buildHeaders(),
        tags: { traffic_group: "group_b", endpoint_name: "profile_get" },
      }),
    };
  }
  if (selector === 2) {
    return {
      name: "complaint_draft_get",
      response: http.get(`${baseUrl}/api/complaint-draft`, {
        headers: buildHeaders(),
        tags: { traffic_group: "group_b", endpoint_name: "complaint_draft_get" },
      }),
    };
  }
  return {
    name: "complaint_draft_put",
    response: http.put(
      `${baseUrl}/api/complaint-draft`,
      JSON.stringify({
        draft: {
          mixed_load_probe: `vu-${__VU}-iter-${__ITER}`,
          note: "standard endpoint write path during mixed load impact test",
        },
      }),
      {
        headers: buildHeaders({ json: true }),
        tags: { traffic_group: "group_b", endpoint_name: "complaint_draft_put" },
      }
    ),
  };
}

export function groupASuggest() {
  const response = http.post(`${baseUrl}/api/ai/suggest`, JSON.stringify(buildSuggestPayload(groupAProfile)), {
    headers: buildHeaders({ json: true }),
    tags: {
      traffic_group: "group_a",
      endpoint_name: "api_ai_suggest",
      profile: groupAProfile,
    },
  });

  groupAReqDuration.add(response.timings.duration);
  const passed = check(response, {
    "group A suggest returns 200": (r) => r.status === 200,
    "group A suggest returns text": (r) => {
      if (r.status !== 200) {
        return false;
      }
      try {
        const body = JSON.parse(r.body || "{}");
        return typeof body.text === "string" && body.text.trim().length > 0;
      } catch (_error) {
        return false;
      }
    },
  });

  if (response.status === 200 && passed) {
    groupAOk.add(1);
    return;
  }
  if (response.status === 429) {
    groupAOverload.add(1);
    return;
  }
  groupAError.add(1);
}

export function groupBStandard() {
  const { name, response } = requestGroupB(__ITER + __VU);

  groupBReqDuration.add(response.timings.duration);
  const passed = check(response, {
    [`group B ${name} returns 200`]: (r) => r.status === 200,
  });
  groupBReqFailed.add(!(response.status === 200 && passed));

  if (response.status === 200 && passed) {
    groupBOk.add(1);
    return;
  }
  groupBError.add(1);
}

export function handleSummary(data) {
  return {
    [summaryPath]: JSON.stringify(data, null, 2),
  };
}
