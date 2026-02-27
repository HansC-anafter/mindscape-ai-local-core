import { describe, expect, it } from "vitest";

import { parseServerTimestamp } from "@/lib/time";

describe("parseServerTimestamp", () => {
  it("parses naive ISO timestamps as UTC", () => {
    const d = parseServerTimestamp("2026-02-27T16:34:43");
    expect(d).not.toBeNull();
    expect(d?.toISOString()).toBe("2026-02-27T16:34:43.000Z");
  });

  it("parses Zulu timestamps", () => {
    const d = parseServerTimestamp("2026-02-27T16:34:43Z");
    expect(d).not.toBeNull();
    expect(d?.toISOString()).toBe("2026-02-27T16:34:43.000Z");
  });

  it("parses explicit +00:00 timestamps", () => {
    const d = parseServerTimestamp("2026-02-27T16:34:43+00:00");
    expect(d).not.toBeNull();
    expect(d?.toISOString()).toBe("2026-02-27T16:34:43.000Z");
  });

  it("parses space-separated timestamps as UTC", () => {
    const d = parseServerTimestamp("2026-02-27 16:34:43");
    expect(d).not.toBeNull();
    expect(d?.toISOString()).toBe("2026-02-27T16:34:43.000Z");
  });

  it("returns null for invalid/empty inputs", () => {
    expect(parseServerTimestamp(null)).toBeNull();
    expect(parseServerTimestamp("")).toBeNull();
    expect(parseServerTimestamp("   ")).toBeNull();
    expect(parseServerTimestamp("invalid")).toBeNull();
  });
});
