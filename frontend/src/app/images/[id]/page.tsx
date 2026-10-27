"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { CompareSlider } from "@/components/CompareSlider";
import { ErrorBanner } from "@/components/ErrorBanner";
import { PipelineStepper } from "@/components/PipelineStepper";
import { SecureImage } from "@/components/SecureImage";
import { StatusBadge } from "@/components/StatusBadge";
import { useToast } from "@/components/Toast";
import { usePolling } from "@/hooks/usePolling";
import { api, downloadFile } from "@/lib/api";
import { formatBytes, isActive, processActionLabel, stageLabel } from "@/lib/format";
import { VIEW_TYPES, type ImageItem, type ResultUrls, type ViewType } from "@/lib/types";

type Layer = "outline" | "mask" | "background_removed";
const LAYERS: { key: Layer; label: string }[] = [
  { key: "outline", label: "Outline" },
  { key: "mask", label: "Mask" },
  { key: "background_removed", label: "Cut-out" },
];

const DOWNLOADS: { kind: keyof ResultUrls; label: string; ext: string; primary?: boolean }[] = [
  { kind: "drawing", label: "Drawing (PNG)", ext: "png", primary: true },
  { kind: "svg", label: "Drawing (SVG)", ext: "svg", primary: true },
  { kind: "mask", label: "Mask", ext: "png" },
  { kind: "outline", label: "Outline overlay", ext: "png" },
  { kind: "background_removed", label: "Cut-out", ext: "png" },
  { kind: "original", label: "Original", ext: "img" },
];

function Card({ title, note, children, className = "" }: { title: string; note?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm ${className}`}>
      <header className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-medium">{title}</h2>
        {note && <p className="text-xs text-slate-500">{note}</p>}
      </header>
      {children}
    </section>
  );
}

function ImageView({ id }: { id: number }) {
  const toast = useToast();
  const [image, setImage] = useState<ImageItem | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [working, setWorking] = useState(false);
  const [layer, setLayer] = useState<Layer>("outline");

  const load = useCallback(() => {
    api.getImage(id).then(setImage).catch(setError);
  }, [id]);
  useEffect(load, [load]);
  usePolling(load, !working && !!image && isActive(image.processing_status), 2000);

  if (!image) {
    return error ? <ErrorBanner error={error} /> : <div className="h-64 animate-pulse rounded-2xl bg-slate-200/60" />;
  }

  const result = image.result;
  const urls = result?.urls;
  const status = working ? "Processing" : image.processing_status;
  const action = working ? null : processActionLabel(image.processing_status);
  const version = result?.updated_at;
  const stem = image.original_filename.replace(/\.[^.]+$/, "");
  const completed = image.processing_status === "Completed" && !working;
  const metrics = (result?.metrics ?? {}) as Record<string, unknown>;
  const drawingInfo = metrics.drawing as { width?: number; height?: number } | undefined;

  async function start() {
    setError(null);
    setWorking(true);
    try {
      const r = await api.processImage(id);
      toast(r.status === "Completed" ? "success" : "error", r.status === "Completed" ? "Drawing ready." : "Processing failed. See details below.");
    } catch (err) {
      setError(err);
    } finally {
      setWorking(false);
      load();
    }
  }

  async function changeView(view: ViewType) {
    try {
      setImage(await api.setView(id, view));
    } catch (err) {
      setError(err);
    }
  }

  async function download(kind: keyof ResultUrls, ext: string) {
    const path = urls?.[kind];
    if (!path) return;
    const extension = ext === "img" ? image!.original_filename.split(".").pop() ?? "png" : ext;
    try {
      await downloadFile(`${path}${path.includes("?") ? "&" : "?"}download=true`, `${stem}_${kind}.${extension}`);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <div className="space-y-6">
      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      <div>
        <Link href={`/projects/${image.project_id}`} className="text-sm text-slate-500 hover:text-slate-900">← Back to project</Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{image.original_filename}</h1>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
              <select
                value={image.view_type}
                onChange={(e) => changeView(e.target.value as ViewType)}
                aria-label="View"
                className="rounded-lg border border-slate-300 bg-white px-2 py-0.5 text-sm text-slate-700"
              >
                {VIEW_TYPES.map((v) => (
                  <option key={v} value={v}>
                    {v} view
                  </option>
                ))}
              </select>
              {image.width}×{image.height} · {formatBytes(image.size_bytes)}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={status} />
            {action && (
              <button onClick={start} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800">
                {action}
              </button>
            )}
          </div>
        </div>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-5 shadow-sm">
        <PipelineStepper status={status} failedStage={working ? null : (result?.failed_stage ?? null)} />
      </section>

      {image.processing_status === "Failed" && result && !working && (
        <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          <p className="font-medium">Failed at “{stageLabel(result.failed_stage)}”</p>
          <p className="mt-1">{result.error_message}</p>
          {image.job && image.job.retry_count > 0 && <p className="mt-1 text-xs text-red-700">Retries so far: {image.job.retry_count}</p>}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Photo vs. pipeline" note="Drag across the image to compare. Check the mask covers the whole product.">
          <div className="space-y-3 p-3">
            <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-sm" role="tablist">
              {LAYERS.map((l) => (
                <button
                  key={l.key}
                  role="tab"
                  aria-selected={layer === l.key}
                  onClick={() => setLayer(l.key)}
                  className={`flex-1 rounded-md px-3 py-1 ${layer === l.key ? "bg-white font-medium shadow-sm" : "text-slate-600 hover:text-slate-900"}`}
                >
                  {l.label}
                </button>
              ))}
            </div>
            <CompareSlider
              before={image.original_url}
              after={completed ? (urls?.[layer] ?? null) : null}
              beforeLabel="Photo"
              afterLabel={LAYERS.find((l) => l.key === layer)!.label}
              version={version}
              className={`h-80 ${layer === "background_removed" ? "checker" : ""}`}
            />
          </div>
        </Card>

        <Card title="Patent-style drawing" note="Uniform black outline on white. Draft for professional review.">
          <div className="flex h-[372px] items-center justify-center bg-white p-4">
            {working || isActive(image.processing_status) ? (
              <div className="flex items-center gap-2 text-sm text-slate-600">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600" />
                Generating drawing…
              </div>
            ) : (
              <SecureImage
                src={completed ? (urls?.drawing ?? null) : null}
                alt="Patent-style drawing"
                className="h-full w-full object-contain"
                placeholder={image.processing_status === "Failed" ? "No drawing: processing failed" : "Generate the drawing to see it here"}
                version={version}
              />
            )}
          </div>
        </Card>
      </div>

      {completed && (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card title="Downloads" className="lg:col-span-2">
            <div className="flex flex-wrap gap-2 p-4">
              {DOWNLOADS.map((d) => (
                <button
                  key={d.kind}
                  onClick={() => download(d.kind, d.ext)}
                  disabled={!urls?.[d.kind]}
                  className={`rounded-lg px-3 py-2 text-sm disabled:opacity-40 ${
                    d.primary ? "bg-slate-900 text-white hover:bg-slate-800" : "border border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  ⬇ {d.label}
                </button>
              ))}
            </div>
          </Card>
          <Card title="Processing details">
            <dl className="grid grid-cols-2 gap-x-3 gap-y-2 p-4 text-sm">
              <dt className="text-slate-500">Mask source</dt>
              <dd>{String(metrics.mask_candidate ?? "—")}</dd>
              <dt className="text-slate-500">Product area</dt>
              <dd>{typeof metrics.mask_area_ratio === "number" ? `${(metrics.mask_area_ratio * 100).toFixed(1)}% of photo` : "—"}</dd>
              <dt className="text-slate-500">Outlines</dt>
              <dd>{String(metrics.contours ?? "—")}</dd>
              <dt className="text-slate-500">Drawing size</dt>
              <dd>{drawingInfo?.width ? `${drawingInfo.width}×${drawingInfo.height}px` : "—"}</dd>
            </dl>
          </Card>
        </div>
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
