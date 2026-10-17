import { describe, it, expect } from "vitest";
import { metricKey, tableValue, updateFilter } from "./api";
describe("bookmark filters", () => {
  it("preserves other filters while changing a parameterized panel", () => {
    const original = new URLSearchParams("sport=Run&metric_volume=distance");
    const next = updateFilter(original, "metric_volume", "duration");
    expect(next.get("sport")).toBe("Run");
    expect(next.get("metric_volume")).toBe("duration");
    expect(original.get("metric_volume")).toBe("distance");
  });
  it("clears empty filters", () => {
    expect(
      updateFilter(new URLSearchParams("sport=Run"), "sport", "").size,
    ).toBe(0);
  });
});
describe("display helpers", () => {
  it("does not render absent values as zero", () => {
    expect(tableValue(null)).toBe("—");
    expect(tableValue(0)).toBe("0");
  });
  it("supports registry identifier keys", () => {
    expect(metricKey({ id: "distance", label: "Distance", unit: "km" })).toBe(
      "distance",
    );
  });
});
