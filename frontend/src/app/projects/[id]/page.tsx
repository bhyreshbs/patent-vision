"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { DropZone } from "@/components/DropZone";
import { ErrorBanner } from "@/components/ErrorBanner";
import { SecureImage } from "@/components/SecureImage";
import { StatusBadge } from "@/components/StatusBadge";
import { useToast } from "@/components/Toast";
import { usePolling } from "@/hooks/usePolling";
import { api } from "@/lib/api";
import { checkUploadFile, formatBytes, isActive, processActionLabel, stageLabel } from "@/lib/format";
import { prepareForUpload } from "@/lib/imageprep";
import { VIEW_TYPES, type ImageItem, type Project, type ViewType } from "@/lib/types";

type QueueState = "waiting" | "optimizing" | "uploading" | "done" | "error";
interface QueueItem {
  key: string;
  name: string;
  state: QueueState;
  note?: string;
}

const QUEUE_LABEL: Record<QueueState, string> = {
  waiting: "Waiting",
  optimizing: "Optimizing",
  uploading: "Uploading",
  done: "Uploaded",
  error: "Failed",
};

function ProjectView({ id }: { id: number }) {
  const router = useRouter();
  const toast = useToast();
  const [project, setProject] = useState<Project | null>(null);
  const [images, setImages] = useState<ImageItem[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [uploadView, setUploadView] = useState<ViewType>("Front");
  const [autoProcess, setAutoProcess] = useState(true);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [busy, setBusy] = useState<Set<number>>(new Set());
  const [batch, setBatch] = useState<{ done: number; total: number } | null>(null);
  const [maxBytes, setMaxBytes] = useState(4 * 1024 * 1024);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const load = useCallback(() => {
    Promise.all([api.getProject(id), api.listImages(id)])
      .then(([p, imgs]) => {
        setProject(p);
        setImages(imgs);
      })
      .catch(setError);
  }, [id]);
  useEffect(load, [load]);
  useEffect(() => {
    api.meta().then((m) => setMaxBytes(m.max_upload_bytes)).catch(() => {});
  }, []);
  usePolling(load, images.some((i) => isActive(i.processing_status)) && busy.size === 0, 2000);

  const setItem = (key: string, patch: Partial<QueueItem>) =>
    setQueue((q) => q.map((it) => (it.key === key ? { ...it, ...patch } : it)));

  async function process(imageId: number): Promise<boolean> {
    setBusy((b) => new Set(b).add(imageId));
    try {
      const r = await api.processImage(imageId);
      return r.status === "Completed";
    } catch (err) {
      setError(err);
      return false;
    } finally {
      setBusy((b) => {
        const next = new Set(b);
        next.delete(imageId);
        return next;
      });
      load();
    }
  }

  async function upload(files: File[]) {
    setError(null);
    const items = files.map((f, i) => ({ key: `${Date.now()}-${i}-${f.name}`, name: f.name, state: "waiting" as QueueState }));
    setQueue((q) => [...items, ...q.filter((it) => it.state !== "done")].slice(0, 12));
    const uploaded: number[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const item = items[i];
      const problem = checkUploadFile(file);
      if (problem) {
        setItem(item.key, { state: "error", note: problem });
        continue;
      }
      try {
        setItem(item.key, { state: "optimizing" });
        const prepared = await prepareForUpload(file, maxBytes);
        setItem(item.key, {
          state: "uploading",
          note: prepared.optimized ? `Optimized ${formatBytes(prepared.originalSize)} → ${formatBytes(prepared.file.size)}` : undefined,
        });
        const img = await api.uploadImage(id, prepared.file, uploadView);
        uploaded.push(img.id);
        setItem(item.key, { state: "done" });
      } catch (err) {
        setItem(item.key, { state: "error", note: err instanceof Error ? err.message : String(err) });
      }
    }
    load();
    if (uploaded.length) toast("success", `Uploaded ${uploaded.length} photo${uploaded.length > 1 ? "s" : ""}.`);
    if (autoProcess && uploaded.length) await runBatch(uploaded);
  }

  async function runBatch(ids: number[]) {
    setBatch({ done: 0, total: ids.length });
    let ok = 0;
    for (let i = 0; i < ids.length; i++) {
      if (await process(ids[i])) ok++;
      setBatch({ done: i + 1, total: ids.length });
    }
    setBatch(null);
    if (ok === ids.length) toast("success", ids.length === 1 ? "Drawing ready." : `${ok} drawings ready.`);
    else toast("error", `${ids.length - ok} of ${ids.length} photo(s) could not be processed. See the error on each card.`);
  }

  async function saveDetails(e: React.FormEvent) {
    e.preventDefault();
    try {
      setProject(await api.updateProject(id, { name, description }));
      setEditing(false);
      toast("success", "Project updated.");
    } catch (err) {
      setError(err);
    }
  }

  async function removeProject() {
    if (!confirm("Delete this project and all of its photos and drawings? This cannot be undone.")) return;
    try {
      await api.deleteProject(id);
      router.replace("/");
    } catch (err) {
      setError(err);
    }
  }

  async function removeImage(img: ImageItem) {
    if (!confirm(`Delete ${img.original_filename} and its drawing?`)) return;
    try {
      await api.deleteImage(img.id);
      toast("info", "Photo deleted.");
    } catch (err) {
      setError(err);
    }
    load();
  }

  async function changeView(img: ImageItem, view: ViewType) {
    try {
      await api.setView(img.id, view);
    } catch (err) {
      setError(err);
    }
    load();
  }

  if (!project) {
    return error ? <ErrorBanner error={error} /> : <div className="h-40 animate-pulse rounded-2xl bg-slate-200/60" />;
  }

  const pending = images.filter((i) => !isActive(i.processing_status) && i.processing_status !== "Completed" && !busy.has(i.id));
  const completed = images.filter((i) => i.processing_status === "Completed").length;

  return (
    <div className="space-y-8">
      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      <div>
        <Link href="/" className="text-sm text-slate-500 hover:text-slate-900">← All projects</Link>
        {editing ? (
          <form onSubmit={saveDetails} className="mt-3 flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white p-4 sm:flex-row">
            <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Project name" required className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <input value={description} onChange={(e) => setDescription(e.target.value)} aria-label="Description" placeholder="Notes" className="flex-[1.4] rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <div className="flex gap-2">
              <button className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white">Save</button>
              <button type="button" onClick={() => setEditing(false)} className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight">{project.name}</h1>
              <p className="mt-1 text-sm text-slate-500">
                {project.description || "No notes"} · {images.length} photo{images.length === 1 ? "" : "s"} · {completed} drawing
                {completed === 1 ? "" : "s"} ready
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setName(project.name);
                  setDescription(project.description);
                  setEditing(true);
                }}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
              >
                Edit
              </button>
              <button onClick={removeProject} className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm text-red-700 hover:bg-red-50">
                Delete
              </button>
            </div>
          </div>
        )}
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-medium">Add photos</h2>
            <p className="text-sm text-slate-500">One product, plain contrasting background, whole product in frame.</p>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <label className="flex items-center gap-2">
              View
              <select
                value={uploadView}
                onChange={(e) => setUploadView(e.target.value as ViewType)}
                className="rounded-lg border border-slate-300 bg-white px-2 py-1"
                aria-label="View for new photos"
              >
                {VIEW_TYPES.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={autoProcess} onChange={(e) => setAutoProcess(e.target.checked)} className="h-4 w-4 rounded" />
              Generate drawings automatically
            </label>
          </div>
        </div>
        <DropZone
          onFiles={upload}
          disabled={queue.some((q) => q.state === "optimizing" || q.state === "uploading")}
          hint={`JPG, PNG or WEBP. Photos over ${formatBytes(maxBytes)} are optimized in your browser before upload.`}
        />
        {queue.length > 0 && (
          <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-100 text-sm">
            {queue.map((q) => (
              <li key={q.key} className="flex items-center justify-between gap-3 px-3 py-2">
                <span className="truncate">{q.name}</span>
                <span className="flex shrink-0 items-center gap-2 text-xs">
                  {q.note && <span className={q.state === "error" ? "text-red-700" : "text-slate-500"}>{q.note}</span>}
                  <span
                    className={
                      q.state === "done"
                        ? "text-emerald-700"
                        : q.state === "error"
                          ? "font-medium text-red-700"
                          : "text-blue-700"
                    }
                  >
                    {QUEUE_LABEL[q.state]}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-medium">Photos & drawings</h2>
          {batch ? (
            <div className="flex w-64 items-center gap-3 text-sm text-slate-600" role="status">
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-200">
                <div className="h-full bg-blue-600 transition-all" style={{ width: `${(batch.done / batch.total) * 100}%` }} />
              </div>
              {batch.done}/{batch.total}
            </div>
          ) : (
            pending.length > 0 && (
              <button
                onClick={() => runBatch(pending.map((p) => p.id))}
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
              >
                Generate {pending.length} drawing{pending.length === 1 ? "" : "s"}
              </button>
            )
          )}
        </div>

        {images.length === 0 && (
          <p className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
            No photos yet. Drop one above to generate its drawing.
          </p>
        )}

        <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {images.map((img) => {
            const working = busy.has(img.id) || isActive(img.processing_status);
            const action = working ? null : processActionLabel(img.processing_status);
            return (
              <li key={img.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                <Link href={`/images/${img.id}`} className="relative grid grid-cols-2 border-b border-slate-100" aria-label={`Open ${img.original_filename}`}>
                  <SecureImage src={img.original_url} alt={`Photo ${img.original_filename}`} className="h-40 w-full bg-slate-50 object-contain" />
                  <SecureImage
                    src={img.result?.urls.drawing ?? null}
                    alt={`Drawing of ${img.original_filename}`}
                    placeholder={img.processing_status === "Failed" ? "No drawing" : "Not generated"}
                    className="h-40 w-full border-l border-slate-100 bg-white object-contain p-2"
                    version={img.result?.updated_at}
                  />
                  {working && (
                    <div className="absolute inset-0 flex items-center justify-center gap-2 bg-white/70 text-sm font-medium text-slate-700 backdrop-blur-[1px]">
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600" />
                      Generating…
                    </div>
                  )}
                </Link>
                <div className="space-y-3 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <Link href={`/images/${img.id}`} className="truncate text-sm font-medium hover:text-blue-700">
                      {img.original_filename}
                    </Link>
                    <StatusBadge status={busy.has(img.id) ? "Processing" : img.processing_status} />
                  </div>
                  <p className="text-xs text-slate-500">
                    {img.width}×{img.height} · {formatBytes(img.size_bytes)}
                  </p>
                  {img.processing_status === "Failed" && img.result?.error_message && !working && (
                    <p className="rounded-lg bg-red-50 p-2 text-xs text-red-800">
                      <strong>{stageLabel(img.result.failed_stage)}:</strong> {img.result.error_message}
                    </p>
                  )}
                  <div className="flex items-center justify-between gap-2">
                    <select
                      value={img.view_type}
                      aria-label={`View for ${img.original_filename}`}
                      onChange={(e) => changeView(img, e.target.value as ViewType)}
                      className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-sm"
                    >
                      {VIEW_TYPES.map((v) => (
                        <option key={v}>{v}</option>
                      ))}
                    </select>
                    <div className="flex gap-2">
                      {action && (
                        <button onClick={() => process(img.id)} className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-800">
                          {action}
                        </button>
                      )}
                      <button
                        disabled={working}
                        onClick={() => removeImage(img)}
                        className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm text-slate-500 hover:bg-slate-50 disabled:opacity-40"
                        aria-label={`Delete ${img.original_filename}`}
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}

export default function ProjectPage() {
  const params = useParams<{ id: string }>();
  return (
    <AppShell>
      <ProjectView id={Number(params.id)} />
    </AppShell>
  );
}
