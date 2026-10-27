"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ErrorBanner } from "@/components/ErrorBanner";
import { Logo } from "@/components/Logo";
import { api, setToken } from "@/lib/api";

const STEPS = [
  ["Upload", "Photograph the product on a plain background and choose its view."],
  ["Segment", "The pipeline removes the background and isolates the complete product."],
  ["Validate", "Incomplete or contaminated masks are rejected instead of drawn."],
  ["Download", "Get a clean black-on-white outline as PNG or SVG."],
];

function HeroIllustration() {
  return (
    <svg viewBox="0 0 320 150" className="w-full max-w-md" aria-hidden="true">
      <rect x="4" y="10" width="140" height="130" rx="10" fill="#1e293b" />
      <rect x="28" y="62" width="40" height="40" rx="6" fill="#e5c28f" />
      <rect x="80" y="62" width="40" height="40" rx="6" fill="#e5c28f" />
      <rect x="66" y="76" width="16" height="8" fill="#e5c28f" />
      <rect x="69" y="40" width="10" height="38" rx="3" fill="#e5c28f" />
      <path d="M156 75h22m-6-6 6 6-6 6" stroke="#94a3b8" strokeWidth="2.5" fill="none" strokeLinecap="round" />
      <rect x="190" y="10" width="126" height="130" rx="10" fill="#fff" stroke="#e2e8f0" />
      <path
        d="M209 66h33v8h10V48a4 4 0 0 1 8 0v26h10v-8h33v40h-33v-8h-10v0h-8v0h-10v8h-33z"
        fill="none"
        stroke="#0f172a"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = mode === "login" ? await api.login(email, password) : await api.register(name, email, password);
      setToken(res.access_token);
      router.replace("/");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const input =
    "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none";

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <section className="hidden flex-col justify-between bg-gradient-to-br from-slate-900 via-slate-900 to-blue-950 p-12 text-white lg:flex">
        <Logo light />
        <div className="space-y-8">
          <h1 className="text-4xl font-semibold leading-tight tracking-tight">
            Product photos in.
            <br />
            <span className="text-blue-300">Patent-style drawings out.</span>
          </h1>
          <HeroIllustration />
          <ol className="grid grid-cols-2 gap-4">
            {STEPS.map(([title, text], i) => (
              <li key={title} className="rounded-xl bg-white/5 p-4 ring-1 ring-white/10">
                <p className="text-xs font-semibold text-blue-300">0{i + 1}</p>
                <p className="mt-1 font-medium">{title}</p>
                <p className="mt-1 text-sm text-slate-300">{text}</p>
              </li>
            ))}
          </ol>
        </div>
        <p className="text-xs text-slate-400">Drafts assist patent preparation and should be professionally reviewed.</p>
      </section>

      <section className="flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <Logo />
          </div>
          <h2 className="text-2xl font-semibold tracking-tight">{mode === "login" ? "Welcome back" : "Create your account"}</h2>
          <p className="mt-1 text-sm text-slate-600">
            {mode === "login" ? "Log in to your projects and drawings." : "Start turning product photos into drawings."}
          </p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <ErrorBanner error={error} />
            {mode === "register" && (
              <label className="block text-sm font-medium text-slate-700">
                Name
                <input className={input} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required />
              </label>
            )}
            <label className="block text-sm font-medium text-slate-700">
              Email
              <input className={input} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Password
              <input
                className={input}
                type="password"
                minLength={mode === "register" ? 8 : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                required
              />
              {mode === "register" && <span className="mt-1 block text-xs font-normal text-slate-500">At least 8 characters.</span>}
            </label>
            <button
              disabled={busy}
              className="w-full rounded-lg bg-slate-900 px-3 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-slate-800 disabled:opacity-60"
            >
              {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
            </button>
          </form>
          <p className="mt-6 text-center text-sm text-slate-600">
            {mode === "login" ? "New to PatentVision?" : "Already have an account?"}{" "}
            <button
              type="button"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError(null);
              }}
              className="font-medium text-blue-700 hover:underline"
            >
              {mode === "login" ? "Create an account" : "Log in"}
            </button>
          </p>
        </div>
      </section>
    </div>
  );
}
