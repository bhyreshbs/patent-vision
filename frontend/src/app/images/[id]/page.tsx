"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorBanner } from "@/components/ErrorBanner";
import { SecureImage } from "@/components/SecureImage";
import { StatusBadge } from "@/components/StatusBadge";
import { usePolling } from "@/hooks/usePolling";
import { api, downloadFile } from "@/lib/api";
import { formatBytes, isActive, processActionLabel, stageLabel } from "@/lib/format";
import type { ImageItem } from "@/lib/types";

function Panel({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <figure className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <figcaption className="border-b border-slate-100 px-3 py-2">
        <p className="text-sm font-medium">{title}</p>
        {note && <p className="text-xs text-slate-500">{note}</p>}
      </figcaption>
      {children}
    </figure>
  );
}

function ImageView({ id }: { id: number }) {
  const [image, setImage] = useState<ImageItem | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api.getImage(id).then(setImage).catch(setError);
  }, [id]);
  useEffect(load, [load]);
  usePolling(load, !!image && isActive(image.processing_status));

  if (!image) {
    return error ? <ErrorBanner error={error} /> : <p className="text-sm text-slate-500">Loading…</p>;
  }

  const result = image.result;
  const urls = result?.urls;
  const action = processActionLabel(image.processing_status);
  const version = result?.updated_at;
  const stem = image.original_filename.replace(/\.[^.]+$/, "");
  const box = "h-72 w-full object-contain";

  async function start() {
    setError(null);
    try {
      await api.processImage(id);
    } catch (err) {
      setError(err);
    }
    load();
  }

  async function download(kind: "drawing" | "mask" | "outline" | "background_removed" | "original") {
    const path = urls?.[kind];
    if (!path) return;
    setError(null);
    try {
      await downloadFile(`${path}${path.includes("?") ? "&" : "?"}download=true`, `${stem}_${kind}.png`);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <div className="space-y-6">
      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      <div>
        <Link href={`/projects/${image.project_id}`} className="text-sm text-blue-700 hover:underline">← Project</Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{image.original_filename}</h1>
            <p className="text-sm text-slate-500">
              {image.view_type} view · {image.width}×{image.height} · {formatBytes(image.size_bytes)}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={image.processing_status} />
            {action && (
              <button onClick={start} className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
                {action}
              </button>
            )}
          </div>
        </div>
      </div>

      {image.processing_status === "Failed" && result && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          <p className="font-medium">Processing failed at the “{stageLabel(result.failed_stage)}” stage.</p>
          <p className="mt-1">{result.error_message}</p>
          {image.job && image.job.retry_count > 0 && <p className="mt-1 text-xs">Retries so far: {image.job.retry_count}</p>}
        </div>
      )}
      {isActive(image.processing_status) && (
        <p className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900" role="status">
          {image.processing_status === "Queued" ? "Waiting for a worker…" : "Generating the drawing…"} This page updates automatically.
        </p>
      )}

      <section className="grid gap-4 md:grid-cols-2">
        <Panel title="Original photograph">
          <SecureImage src={image.original_url} alt="Original photograph" className={box} />
        </Panel>
        <Panel title="Final patent-style drawing" note="Black outline on white. Draft for professional review.">
          <SecureImage src={urls?.drawing ?? null} alt="Patent-style drawing" className={`${box} bg-white`} placeholder="Not generated yet" version={version} />
        </Panel>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Panel title="Background removed" note="Transparent background">
          <SecureImage src={urls?.background_removed ?? null} alt="Background removed" className={`${box} checker`} version={version} />
        </Panel>
        <Panel title="Segmentation mask" note="White = product. Check it covers the whole product.">
          <SecureImage src={urls?.mask ?? null} alt="Segmentation mask" className={`${box} bg-black`} version={version} />
        </Panel>
        <Panel title="Outer outline" note="Extracted outline over the photo">
          <SecureImage src={urls?.outline ?? null} alt="Outer outline" className={box} version={version} />
        </Panel>
      </section>

      {image.processing_status === "Completed" && (
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-3 font-medium">Downloads</h2>
          <div className="flex flex-wrap gap-2">
            {(
              [
                ["drawing", "Final drawing"],
                ["mask", "Mask"],
                ["outline", "Outline"],
                ["background_removed", "Background removed"],
                ["original", "Original"],
              ] as const
            ).map(([kind, label]) => (
              <button key={kind} onClick={() => download(kind)} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
                ⬇ {label}
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default function ImagePage() {
  const params = useParams<{ id: string }>();
  return (
    <AppShell>
      <ImageView id={Number(params.id)} />
    </AppShell>
  );
}
