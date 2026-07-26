import assert from "node:assert/strict";
import test from "node:test";

import { inferToolOperationType } from "../dist/mindscape/client.js";

test("classifies explicit read actions as read", () => {
  assert.equal(
    inferToolOperationType("default.workspace_list_executions"),
    "read"
  );
  assert.equal(
    inferToolOperationType("core.workspace_validate_report"),
    "read"
  );
});

test("preserves destructive and publication admission semantics", () => {
  assert.equal(
    inferToolOperationType("wordpress.delete_post"),
    "delete"
  );
  assert.equal(
    inferToolOperationType("web_generation.publish_site"),
    "publish"
  );
});

test("defaults unknown and report packaging actions to modify", () => {
  assert.equal(
    inferToolOperationType("default.workspace_package_report"),
    "modify"
  );
  assert.equal(
    inferToolOperationType("custom.do_something"),
    "modify"
  );
});
