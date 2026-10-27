"use client";

import { useEffect, useRef } from "react";

/** Calls `fn` every `ms` while `active` is true. Always uses the latest `fn`. */
export function usePolling(fn: () => void, active: boolean, ms = 1500): void {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => saved.current(), ms);
    return () => clearInterval(id);
  }, [active, ms]);
}
