import { describe, expect, it } from "vitest";
import { ATTEMPTS, needsPreparation, preferredOutputType, renamed, targetDimensions } from "./imageprep";

describe("targetDimensions", () => {
  it("keeps images that already fit", () => {
    expect(targetDimensions(1200, 800, 2048)).toEqual({ width: 1200, height: 800 });
  });
  it("scales the long side down and keeps the aspect ratio", () => {
    expect(targetDimensions(6000, 4000, 3000)).toEqual({ width: 3000, height: 2000 });
    expect(targetDimensions(3000, 6000, 1500)).toEqual({ width: 750, height: 1500 });
  });
  it("handles degenerate sizes", () => {
    expect(targetDimensions(0, 100, 100)).toEqual({ width: 0, height: 0 });
  });
});

describe("upload preparation rules", () => {
  it("only re-encodes files over the limit", () => {
    expect(needsPreparation({ size: 100, type: "image/jpeg" }, 1000)).toBe(false);
    expect(needsPreparation({ size: 1001, type: "image/jpeg" }, 1000)).toBe(true);
  });
  it("keeps transparency-capable formats for PNG/WebP sources", () => {
    expect(preferredOutputType("image/png")).toBe("image/webp");
    expect(preferredOutputType("image/webp")).toBe("image/webp");
    expect(preferredOutputType("image/jpeg")).toBe("image/jpeg");
  });
  it("renames with the new extension", () => {
    expect(renamed("IMG_0001.HEIC.png", "image/webp")).toBe("IMG_0001.HEIC.webp");
    expect(renamed("photo.jpeg", "image/jpeg")).toBe("photo.jpg");
    expect(renamed(".png", "image/jpeg")).toBe("photo.jpg");
  });
  it("tries progressively smaller encodes", () => {
    for (let i = 1; i < ATTEMPTS.length; i++) {
      expect(ATTEMPTS[i].maxSide).toBeLessThan(ATTEMPTS[i - 1].maxSide);
      expect(ATTEMPTS[i].quality).toBeLessThanOrEqual(ATTEMPTS[i - 1].quality);
    }
  });
});
