import { describe, expect, it } from "vitest";
import { compactNumber, safePreview } from "../src/formatting";

describe("formatting", () => {
  it("formats compact numbers", () => {
    expect(compactNumber(undefined)).toBe("Unavailable");
    expect(compactNumber(1420)).toBe("1.42K");
    expect(compactNumber(3_810_000)).toBe("3.81M");
  });

  it("truncates text safely", () => {
    expect(safePreview("hello\nworld", 20)).toBe("hello world");
    expect(safePreview("x".repeat(20), 10)).toBe("xxxxxxx...");
  });
});

