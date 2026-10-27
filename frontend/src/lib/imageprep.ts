/**
 * Client-side photo preparation. Hosting limits request bodies (~4.5 MB on Vercel), so photos above the
 * server's upload limit are re-encoded in the browser before upload. Small photos are sent untouched.
 */

export interface Attempt {
  maxSide: number;
  quality: number;
}

/** Progressively smaller/lower-quality encodes; the first one under the limit wins. */
export const ATTEMPTS: Attempt[] = [
  { maxSide: 4096, quality: 0.92 },
  { maxSide: 3200, quality: 0.9 },
  { maxSide: 2560, quality: 0.86 },
  { maxSide: 2048, quality: 0.82 },
  { maxSide: 1600, quality: 0.78 },
];

export function targetDimensions(width: number, height: number, maxSide: number): { width: number; height: number } {
  if (width <= 0 || height <= 0) return { width: 0, height: 0 };
  const scale = Math.min(1, maxSide / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

export function needsPreparation(file: { size: number; type: string }, maxBytes: number): boolean {
  return file.size > maxBytes;
}

/** PNGs may carry transparency (a useful background hint), so keep alpha via WebP when the browser can. */
export function preferredOutputType(inputType: string): "image/webp" | "image/jpeg" {
  return inputType === "image/png" || inputType === "image/webp" ? "image/webp" : "image/jpeg";
}

export function renamed(name: string, type: string): string {
  const ext = type === "image/webp" ? "webp" : "jpg";
  const stem = name.replace(/\.[^.]+$/, "") || "photo";
  return `${stem}.${ext}`;
}

function encode(canvas: HTMLCanvasElement, type: string, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

export interface Prepared {
  file: File;
  optimized: boolean;
  originalSize: number;
}

export async function prepareForUpload(file: File, maxBytes: number): Promise<Prepared> {
  if (!needsPreparation(file, maxBytes)) return { file, optimized: false, originalSize: file.size };

  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  try {
    let type: string = preferredOutputType(file.type);
    for (const attempt of ATTEMPTS) {
      const { width, height } = targetDimensions(bitmap.width, bitmap.height, attempt.maxSide);
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      if (!ctx) break;
      ctx.drawImage(bitmap, 0, 0, width, height);
      let blob = await encode(canvas, type, attempt.quality);
      if (blob && blob.type !== type) {
        type = "image/jpeg"; // browser cannot encode WebP (e.g. older Safari)
        blob = await encode(canvas, type, attempt.quality);
      }
      if (blob && blob.size <= maxBytes) {
        return { file: new File([blob], renamed(file.name, type), { type }), optimized: true, originalSize: file.size };
      }
    }
  } finally {
    bitmap.close();
  }
  throw new Error(`${file.name}: could not be reduced below the upload limit.`);
}
