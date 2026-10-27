import { describe, expect, it } from "vitest";
import {
  checkUploadFile,
  formatBytes,
  formatDate,
  isActive,
  MAX_UPLOAD_BYTES,
  processActionLabel,
  stageLabel,
} from "./format";

describe("formatBytes", () => {
  it("formats B, KB and MB", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });
  it("handles invalid input", () => {
    expect(formatBytes(-1)).toBe("—");
    expect(formatBytes(NaN)).toBe("—");
  });
});

describe("formatDate", () => {
  it("returns a dash for invalid dates", () => {
    expect(formatDate("not-a-date")).toBe("—");
  });
  it("formats valid ISO dates", () => {
    expect(formatDate("2026-10-27T10:00:00Z")).toMatch(/2026/);
  });
});

describe("status helpers", () => {
  it("knows which statuses are in flight", () => {
    expect(isActive("Queued")).toBe(true);
    expect(isActive("Processing")).toBe(true);
    expect(isActive("Completed")).toBe(false);
    expect(isActive("Failed")).toBe(false);
  });
  it("picks the right action label", () => {
    expect(processActionLabel("Uploaded")).toBe("Generate drawing");
    expect(processActionLabel("Failed")).toBe("Retry");
    expect(processActionLabel("Completed")).toBe("Reprocess");
    expect(processActionLabel("Processing")).toBeNull();
    expect(processActionLabel("Queued")).toBeNull();
  });
  it("prettifies stage names", () => {
    expect(stageLabel("mask_validation")).toBe("Mask validation");
    expect(stageLabel(null)).toBe("");
  });
});

describe("checkUploadFile", () => {
  const ok = { name: "a.png", type: "image/png", size: 1000 };
  it("accepts supported images", () => {
    expect(checkUploadFile(ok)).toBeNull();
    expect(checkUploadFile({ ...ok, type: "image/jpeg" })).toBeNull();
    expect(checkUploadFile({ ...ok, type: "image/webp" })).toBeNull();
  });
  it("rejects HEIC, other types, empty and oversized files", () => {
    expect(checkUploadFile({ ...ok, name: "x.HEIC", type: "image/heic" })).toMatch(/HEIC/);
    expect(checkUploadFile({ ...ok, type: "image/gif" })).toMatch(/JPG, PNG or WEBP/);
    expect(checkUploadFile({ ...ok, size: 0 })).toMatch(/empty/);
    expect(checkUploadFile({ ...ok, size: MAX_UPLOAD_BYTES + 1 })).toMatch(/larger than/);
  });
});
