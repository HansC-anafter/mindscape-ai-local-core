import assert from "node:assert/strict";
import test from "node:test";

import { formatToolResult } from "../dist/mindscape/client_mappers.js";

test("maps owner review preflight to confirmation_required", () => {
  const result = formatToolResult({
    success: true,
    result: {
      artifact_created: false,
      review_requirements: ["verified_owner_review:report.html"],
      blocking_codes: [],
      review_binding_sha256: "a".repeat(64),
    },
  }, "core.workspace_package_report");

  assert.equal(result.status, "confirmation_required");
  assert.equal(result.outputs.artifact_created, false);
});

test("maps blocked preflight to a structured failure", () => {
  const result = formatToolResult({
    success: true,
    result: {
      artifact_created: false,
      review_requirements: [],
      blocking_codes: ["restricted_content:report.html"],
    },
  }, "core.workspace_package_report");

  assert.equal(result.status, "failed");
  assert.equal(result.error.code, "ARTIFACT_DISCLOSURE_BLOCKED");
  assert.deepEqual(result.error.details.blocking_codes, [
    "restricted_content:report.html",
  ]);
});
