import type { ImageStatus } from "./types";

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function isActive(status: ImageStatus): boolean {
  return status === "Queued" || status === "Processing";
}

export function stageLabel(stage: string | null): string {
  if (!stage) return "";
  return stage.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export const STATUS_STYLES: Record<ImageStatus, string> = {
  Uploaded: "bg-slate-100 text-slate-700 ring-slate-300",
  Queued: "bg-amber-50 text-amber-800 ring-amber-300",
  Processing: "bg-blue-50 text-blue-800 ring-blue-300",
  Completed: "bg-emerald-50 text-emerald-800 ring-emerald-300",
  Failed: "bg-red-50 text-red-800 ring-red-300",
};

/** Action label for the process button given the image's current status. */
export function processActionLabel(status: ImageStatus): string | null {
  switch (status) {
    case "Uploaded":
      return "Generate drawing";
    case "Failed":
      return "Retry";
    case "Completed":
      return "Reprocess";
    default:
      return null; // Queued / Processing: nothing to start
  }
}

const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];
/** Largest photo we try to shrink in the browser; anything under the server limit is sent as-is. */
export const MAX_UPLOAD_BYTES = 40 * 1024 * 1024;

/** Client-side pre-check so users get immediate feedback; the server remains the authority. */
export function checkUploadFile(file: { name: string; type: string; size: number }): string | null {
  if (/\.(heic|heif)$/i.test(file.name)) {
    return "HEIC images are not supported yet. Convert to JPG, PNG or WEBP first.";
  }
  if (!ACCEPTED.includes(file.type)) return `${file.name}: use a JPG, PNG or WEBP image.`;
  if (file.size === 0) return `${file.name}: the file is empty.`;
  if (file.size > MAX_UPLOAD_BYTES) return `${file.name}: larger than ${formatBytes(MAX_UPLOAD_BYTES)}.`;
  return null;
}
