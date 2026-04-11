import http from "k6/http";
import { Counter } from "k6/metrics";
import { check } from "k6";
import { buildSuggestPayload } from "./suggest_payload_profiles.js";

const baseUrl = String(__ENV.BASE_URL || "").replace(/\/+$/, "");
const sessionCookie = String(__ENV.SESSION_COOKIE || "").trim();
const profile = String(__ENV.PROFILE || "short").trim().toLowerCase();
const summaryPath = String(__ENV.SUMMARY_PATH || "artifacts/load/summary.json").trim();

if (!baseUrl) {
  throw new Error("BASE_URL is required.");
}
if (!sessionCookie) {
  throw new Error("SESSION_COOKIE is required.");
}

const p95Threshold = String(__ENV.THRESHOLD_P95_MS || "").trim();
const errorRateThreshold = String(__ENV.THRESHOLD_ERROR_RATE || "").trim();

const thresholds = {
  checks: ["rate>0.95"],
};
if (p95Threshold) {
  thresholds.http_req_duration = [`p(95)<${p95Threshold}`];
}
if (errorRateThreshold) {
  thresholds.http_req_failed = [`rate<${errorRateThreshold}`];
}

export const options = {
  vus: Number(__ENV.VUS || 5),
  duration: String(__ENV.DURATION || "1m"),
  thresholds,
};

const suggestOk = new Counter("suggest_ok");
const suggestOverload = new Counter("suggest_overload");
const suggestError = new Counter("suggest_error");

export default function () {
  const response = http.post(`${baseUrl}/api/ai/suggest`, JSON.stringify(buildSuggestPayload(profile)), {
    headers: {
      "Content-Type": "application/json",
      Cookie: `ogp_web_session=${sessionCookie}`,
    },
    tags: {
      endpoint: "api_ai_suggest",
      profile,
    },
  });

  const passed = check(response, {
    "suggest returns 200": (r) => r.status === 200,
    "suggest returns text": (r) => {
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
    suggestOk.add(1);
    return;
  }
  if (response.status === 429) {
    suggestOverload.add(1);
    return;
  }
  suggestError.add(1);
}

export function handleSummary(data) {
  return {
    [summaryPath]: JSON.stringify(data, null, 2),
  };
}
