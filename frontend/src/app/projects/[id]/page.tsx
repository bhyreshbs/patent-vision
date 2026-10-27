"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorBanner } from "@/components/ErrorBanner";
import { SecureImage } from "@/components/SecureImage";
import { StatusBadge } from "@/components/StatusBadge";
import { usePolling } from "@/hooks/usePolling";
import { api } from "@/lib/api";
import { checkUploadFile, formatBytes, isActive, processActionLabel, stageLabel } from "@/lib/format";
import { VIEW_TYPES, type ImageItem, type Project, type ViewType } from "@/lib/types";

function ProjectView({ id }: { id: number }) {
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [images, setImages] = useState<ImageItem[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [uploadView, setUploadView] = useState<ViewType>("Front");
  const [uploading, setUploading] = useState(false);
  const [name, setName] = useState("");
  const [editing, setEditing] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    Promise.all([api.getProject(id), api.listImages(id)])
      .then(([p, imgs]) => {
        setProject(p);
        setImages(imgs);
      })
      .catch(setError);
  }, [id]);
  useEffect(load, [load]);
  usePolling(load, images.some((i) => isActive(i.processing_status)));

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    setError(null);
    for (const file of Array.from(files)) {
      const problem = checkUploadFile(file);
      if (problem) {
        setError(new Error(problem));
        continue;
      }
      try {
        await api.uploadImage(id, file, uploadView);
      } catch (err) {
        setError(err);
      }
    }
    if (fileInput.current) fileInput.current.value = "";
    setUploading(false);
    load();
  }

  async function run<T>(fn: () => Promise<T>) {
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err);
    }
    load();
  }

  async function removeProject() {
    if (!confirm("Delete this project and all of its images and drawings?")) return;
    try {
      await api.deleteProject(id);
      router.replace("/");
    } catch (err) {
      setError(err);
    }
  }

  if (!project) {
    return error ? <ErrorBanner error={error} /> : <p className="text-sm text-slate-500">Loading…</p>;
  }

  const pending = images.filter((i) => !isActive(i.processing_status) && i.processing_status !== "Completed");

  return (
    <div className="space-y-6">
      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      <div>
        <Link href="/" className="text-sm text-blue-700 hover:underline">← Dashboard</Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          {editing ? (
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                run(() => api.updateProject(id, { name })).then(() => setEditing(false));
              }}
            >
              <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Project name" className="rounded-md border border-slate-300 px-2 py-1" />
              <button className="rounded-md bg-blue-600 px-3 py-1 text-sm text-white">Save</button>
            </form>
          ) : (
            <h1 className="text-2xl font-semibold tracking-tight">
              {project.name}{" "}
              <button
                className="text-sm font-normal text-blue-700 hover:underline"
                onClick={() => {
                  setName(project.name);
                  setEditing(true);
                }}
              >
                rename
              </button>
            </h1>
          )}
          <button onClick={removeProject} className="rounded-md border border-red-300 px-3 py-1 text-sm text-red-700 hover:bg-red-50">
            Delete project
          </button>
        </div>
        {project.description && <p className="mt-1 text-sm text-slate-600">{project.description}</p>}
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="mb-1 font-medium">Upload product photographs</h2>
        <p className="mb-3 text-sm text-slate-600">
          JPG, PNG or WEBP up to 15 MB. Use a single product on a plain, contrasting background with the whole product in
          frame. Choose the view each photo shows.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm">
            View{" "}
            <select value={uploadView} onChange={(e) => setUploadView(e.target.value as ViewType)} className="rounded-md border border-slate-300 px-2 py-1">
              {VIEW_TYPES.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
          <input
            ref={fileInput}
            type="file"
            multiple
            accept="image/jpeg,image/png,image/webp"
            aria-label="Choose images"
            disabled={uploading}
            onChange={(e) => upload(e.target.files)}
            className="text-sm"
          />
          {uploading && <span className="text-sm text-slate-500">Uploading…</span>}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-medium">Images ({images.length})</h2>
          {pending.length > 0 && (
            <button
              onClick={() => run(() => api.processProject(id))}
              className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
            >
              Process {pending.length} pending
            </button>
          )}
        </div>
        {images.length === 0 && (
          <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
            No images yet. Upload a photograph to begin.
          </p>
        )}
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {images.map((img) => {
            const action = processActionLabel(img.processing_status);
            return (
              <li key={img.id} className="overflow-hidden rounded-xl border border-slate-200 bg-white">
                <div className="grid grid-cols-2 border-b border-slate-100">
                  <SecureImage src={img.original_url} alt={`Original ${img.original_filename}`} className="h-36 w-full object-contain" />
                  <SecureImage
                    src={img.result?.urls.drawing ?? null}
                    alt={`Drawing of ${img.original_filename}`}
                    placeholder="No drawing yet"
                    className="h-36 w-full border-l border-slate-100 bg-white object-contain"
                    version={img.result?.updated_at}
                  />
                </div>
                <div className="space-y-2 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <Link href={`/images/${img.id}`} className="truncate text-sm font-medium text-blue-800 hover:underline">
                      {img.original_filename}
                    </Link>
                    <StatusBadge status={img.processing_status} />
                  </div>
                  <p className="text-xs text-slate-500">
                    {img.width}×{img.height} · {formatBytes(img.size_bytes)}
                  </p>
                  {img.processing_status === "Failed" && img.result?.error_message && (
                    <p className="rounded-md bg-red-50 p-2 text-xs text-red-800">
                      <strong>{stageLabel(img.result.failed_stage)}:</strong> {img.result.error_message}
                    </p>
                  )}
                  <div className="flex items-center justify-between gap-2">
                    <select
                      value={img.view_type}
                      aria-label={`View for ${img.original_filename}`}
                      onChange={(e) => run(() => api.setView(img.id, e.target.value as ViewType))}
                      className="rounded-md border border-slate-300 px-2 py-1 text-sm"
                    >
                      {VIEW_TYPES.map((v) => (
                        <option key={v}>{v}</option>
                      ))}
                    </select>
                    <div className="flex gap-2">
                      {action && (
                        <button onClick={() => run(() => api.processImage(img.id))} className="rounded-md bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700">
                          {action}
                        </button>
                      )}
                      <button
                        disabled={isActive(img.processing_status)}
                        onClick={() => confirm("Delete this image?") && run(() => api.deleteImage(img.id))}
                        className="rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40"
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
