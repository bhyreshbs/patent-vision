"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";
import type { User } from "@/lib/types";

const UserContext = createContext<User | null>(null);
export const useUser = () => useContext(UserContext);

/** Requires a valid session; redirects to /login otherwise. Renders the page chrome. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => {
        setToken(null);
        router.replace("/login");
      });
  }, [router]);

  function logout() {
    setToken(null);
    router.replace("/login");
  }

  if (!user) return <div className="p-10 text-center text-sm text-slate-500">Loading…</div>;

  return (
    <UserContext.Provider value={user}>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link href="/" className="text-lg font-semibold tracking-tight">
            Patent<span className="text-blue-600">Vision</span> AI
          </Link>
          <div className="flex items-center gap-4 text-sm text-slate-600">
            <span data-testid="user-name">{user.name}</span>
            <button onClick={logout} className="rounded-md border border-slate-300 px-3 py-1 hover:bg-slate-50">
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-slate-500">
        Drawings are drafts to assist patent preparation. They do not guarantee patent-office acceptance and
        should be reviewed by a patent professional.
      </footer>
    </UserContext.Provider>
  );
}
