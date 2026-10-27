import { describe, expect, it } from "vitest";
import { STAGES, stageStates } from "./pipeline";

describe("stageStates", () => {
  it("marks every stage done when completed", () => {
    expect(stageStates("Completed", null)).toEqual(Array(STAGES.length).fill("done"));
  });
  it("marks everything pending before processing", () => {
    expect(new Set(stageStates("Uploaded", null))).toEqual(new Set(["pending"]));
  });
  it("animates while in flight", () => {
    expect(new Set(stageStates("Processing", null))).toEqual(new Set(["active"]));
  });
  it("pinpoints the failed stage", () => {
    const states = stageStates("Failed", "mask_validation");
    const i = STAGES.findIndex((s) => s.key === "mask_validation");
    expect(states.slice(0, i)).toEqual(Array(i).fill("done"));
    expect(states[i]).toBe("failed");
    expect(states.slice(i + 1).every((s) => s === "pending")).toBe(true);
  });
  it("treats save failures as after-the-pipeline and interruptions as unknown", () => {
    expect(new Set(stageStates("Failed", "persistence"))).toEqual(new Set(["done"]));
    expect(new Set(stageStates("Failed", "interrupted"))).toEqual(new Set(["pending"]));
  });
});
