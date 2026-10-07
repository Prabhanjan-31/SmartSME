/**
 * The health card's display rules. The one that matters most is null: a part
 * with no data behind it must never render as a red zero.
 */
import { describe, expect, it } from "vitest";

import { healthColor, healthLabel, healthTone } from "./health";

describe("health bands", () => {
  it.each([
    [100, "success", "Healthy"],
    [70, "success", "Healthy"],
    [69, "warning", "Fair"],
    [40, "warning", "Fair"],
    [39, "destructive", "At risk"],
    [0, "destructive", "At risk"],
  ] as const)("%i is %s / %s", (score, tone, label) => {
    expect(healthTone(score)).toBe(tone);
    expect(healthLabel(score)).toBe(label);
  });
});

describe("a score with no data", () => {
  it("reads as not enough data, not as zero", () => {
    expect(healthLabel(null)).toBe("Not enough data");
    expect(healthTone(null)).toBe("default");
  });

  it("draws an empty track rather than a coloured bar", () => {
    expect(healthColor(null)).toBeNull();
  });

  it("while a real zero is still coloured as at risk", () => {
    expect(healthColor(0)).toBe("--destructive");
    expect(healthColor(85)).toBe("--success");
  });
});
