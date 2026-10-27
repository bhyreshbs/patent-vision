"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorBanner } from "@/components/ErrorBanner";
import { SecureImage } from "@/components/SecureImage";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Dashboard, ImageStatus } from "@/lib/types";

const STATUSES: ImageStatus[] = ["Uploaded", "Queued", "Processing", "Completed", "Failed"];

function DashboardView() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    api.dashboard().then(setData).catch(setError);
  }, []);
  useEffect(load, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await api.createProject(name, description);
      setName("");
      setDescription("");
      load();
    } catch (err) {
      setError(err);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-8">
      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      <section aria-label="Summary" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Projects" value={data?.project_count} />
        <Stat label="Images" value={data?.image_count} />
        <Stat label="Completed" value={data?.status_counts.Completed ?? 0} />
        <Stat label="Failed" value={data?.status_counts.Failed ?? 0} />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="mb-3 font-medium">New project</h2>
        <form onSubmit={create} className="flex flex-col gap-3 sm:flex-row">
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Project name"
            aria-label="Project name"
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            aria-label="Description"
            className="flex-[2] rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            disabled={creating || !name.trim()}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
          >
            Create project
          </button>
        </form>
      </section>

      <section>
        <h2 className="mb-3 font-medium">Projects</h2>
        {data && data.recent_projects.length === 0 && (
          <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
            No projects yet. Create one above, then upload a product photograph.
          </p>
        )}
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data?.recent_projects.map((p) => (
            <li key={p.id}>
              <Link href={`/projects/${p.id}`} className="block rounded-xl border border-slate-200 bg-white p-4 hover:border-blue-400">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-medium">{p.name}</h3>
                  <span className="text-xs text-slate-500">{p.image_count} image{p.image_count === 1 ? "" : "s"}</span>
                </div>
                {p.description && <p className="mt-1 line-clamp-2 text-sm text-slate-600">{p.description}</p>}
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {STATUSES.filter((s) => p.status_counts[s]).map((s) => (
                    <span key={s} className="flex items-center gap-1 text-xs">
                      <StatusBadge status={s} />×{p.status_counts[s]}
                    </span>
                  ))}
                </div>
                <p className="mt-2 text-xs text-slate-400">Updated {formatDate(p.updated_at)}</p>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      {data && data.recent_results.length > 0 && (
        <section>
          <h2 className="mb-3 font-medium">Recent results</h2>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {data.recent_results.map((img) => (
              <li key={img.id}>
                <Link href={`/images/${img.id}`} className="block overflow-hidden rounded-lg border border-slate-200 bg-white hover:border-blue-400">
                  <SecureImage
                    src={img.result?.urls.drawing ?? null}
                    alt={`Drawing of ${img.original_filename}`}
                    className="h-32 w-full bg-white object-contain"
                  />
                  <p className="truncate border-t border-slate-100 px-2 py-1 text-xs text-slate-600">{img.original_filename}</p>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value ?? "–"}</p>
    </div>
  );
}

export default function Home() {
  return (
    <AppShell>
      <DashboardView />
    </AppShell>
  );
}
