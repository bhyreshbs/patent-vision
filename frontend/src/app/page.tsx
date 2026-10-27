"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell, useUser } from "@/components/AppShell";
import { ErrorBanner } from "@/components/ErrorBanner";
import { SecureImage } from "@/components/SecureImage";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Dashboard, ImageStatus } from "@/lib/types";

const STATUSES: ImageStatus[] = ["Uploaded", "Queued", "Processing", "Completed", "Failed"];

function DashboardView() {
  const user = useUser();
  const router = useRouter();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState("");

  const load = useCallback(() => {
    api.dashboard().then(setData).catch(setError);
  }, []);
  useEffect(load, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const p = await api.createProject(name, description);
      router.push(`/projects/${p.id}`);
    } catch (err) {
      setError(err);
      setCreating(false);
    }
  }

  const coverFor = useMemo(() => {
    const map = new Map<number, string>();
    for (const img of data?.recent_results ?? []) {
      if (img.result?.urls.drawing && !map.has(img.project_id)) map.set(img.project_id, img.result.urls.drawing);
    }
    return map;
  }, [data]);

  const projects = (data?.recent_projects ?? []).filter((p) =>
    `${p.name} ${p.description}`.toLowerCase().includes(query.trim().toLowerCase()),
  );
  const completed = data?.status_counts.Completed ?? 0;
  const failed = data?.status_counts.Failed ?? 0;

  return (
    <div className="space-y-10">
      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500">Welcome back{user ? `, ${user.name.split(" ")[0]}` : ""}</p>
          <h1 className="text-3xl font-semibold tracking-tight">Your drawings</h1>
        </div>
      </section>

      <section aria-label="Summary" className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Projects" value={data?.project_count} />
        <Stat label="Photos" value={data?.image_count} />
        <Stat label="Drawings ready" value={data ? completed : undefined} accent="text-emerald-600" />
        <Stat label="Need attention" value={data ? failed : undefined} accent={failed ? "text-red-600" : undefined} />
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="font-medium">Start a new project</h2>
        <p className="mb-4 text-sm text-slate-500">One project per product. Add a photo for each view (front, side, top…).</p>
        <form onSubmit={create} className="flex flex-col gap-3 sm:flex-row">
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Product name, e.g. Desk organizer"
            aria-label="Project name"
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Notes (optional)"
            aria-label="Description"
            className="flex-[1.4] rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            disabled={creating || !name.trim()}
            className="rounded-lg bg-slate-900 px-5 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create project"}
          </button>
        </form>
      </section>

      <section>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-medium">Projects</h2>
          {(data?.recent_projects.length ?? 0) > 0 && (
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search projects"
              aria-label="Search projects"
              className="w-56 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
            />
          )}
        </div>
        {!data && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-56 animate-pulse rounded-2xl bg-slate-200/60" />
            ))}
          </div>
        )}
        {data && data.recent_projects.length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
            <p className="font-medium">No projects yet</p>
            <p className="mt-1 text-sm text-slate-500">Create a project above, then drop in a product photo.</p>
          </div>
        )}
        {data && data.recent_projects.length > 0 && projects.length === 0 && (
          <p className="text-sm text-slate-500">No projects match “{query}”.</p>
        )}
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <li key={p.id}>
              <Link
                href={`/projects/${p.id}`}
                className="group block overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
              >
                <div className="flex h-36 items-center justify-center border-b border-slate-100 bg-slate-50">
                  {coverFor.get(p.id) ? (
                    <SecureImage src={coverFor.get(p.id)!} alt={`Latest drawing in ${p.name}`} className="h-full w-full bg-white object-contain p-3" />
                  ) : (
                    <span className="text-xs text-slate-400">{p.image_count ? "No drawing yet" : "Empty project"}</span>
                  )}
                </div>
                <div className="p-4">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-medium group-hover:text-blue-700">{p.name}</h3>
                    <span className="shrink-0 text-xs text-slate-500">
                      {p.image_count} photo{p.image_count === 1 ? "" : "s"}
                    </span>
                  </div>
                  {p.description && <p className="mt-1 line-clamp-1 text-sm text-slate-600">{p.description}</p>}
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {STATUSES.filter((s) => p.status_counts[s]).map((s) => (
                      <span key={s} className="flex items-center gap-1 text-xs text-slate-500">
                        <StatusBadge status={s} />×{p.status_counts[s]}
                      </span>
                    ))}
                  </div>
                  <p className="mt-3 text-xs text-slate-400">Updated {formatDate(p.updated_at)}</p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      {data && data.recent_results.length > 0 && (
        <section>
          <h2 className="mb-4 text-lg font-medium">Recent drawings</h2>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {data.recent_results.map((img) => (
              <li key={img.id}>
                <Link href={`/images/${img.id}`} className="block overflow-hidden rounded-xl border border-slate-200 bg-white hover:border-blue-400">
                  <SecureImage
                    src={img.result?.urls.drawing ?? null}
                    alt={`Drawing of ${img.original_filename}`}
                    className="h-32 w-full bg-white object-contain p-2"
                  />
                  <p className="truncate border-t border-slate-100 px-2 py-1.5 text-xs text-slate-600">
                    {img.view_type} · {img.original_filename}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: number | undefined; accent?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-3xl font-semibold ${accent ?? ""}`}>{value ?? "–"}</p>
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
