"use client";

import { useState } from "react";
import { SecureImage } from "@/components/SecureImage";

interface Props {
  before: string;
  after: string | null;
  beforeLabel: string;
  afterLabel: string;
  version?: string;
  className?: string;
}

/** Before/after comparison: both images share one box, a slider reveals the "after" layer. */
export function CompareSlider({ before, after, beforeLabel, afterLabel, version, className = "h-80" }: Props) {
  const [pos, setPos] = useState(50);
  return (
    <div className={`relative select-none overflow-hidden rounded-lg bg-slate-100 ${className}`}>
      <SecureImage src={before} alt={beforeLabel} className="absolute inset-0 h-full w-full object-contain" />
      {after && (
        <div className="absolute inset-0" style={{ clipPath: `inset(0 0 0 ${pos}%)` }}>
          <SecureImage src={after} alt={afterLabel} className="h-full w-full object-contain" version={version} />
        </div>
      )}
      {after && (
        <>
          <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-white shadow-[0_0_0_1px_rgba(15,23,42,0.25)]" style={{ left: `${pos}%` }}>
            <span className="absolute top-1/2 left-1/2 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white text-xs text-slate-700 shadow ring-1 ring-slate-300">
              ⇆
            </span>
          </div>
          <span className="absolute left-2 top-2 rounded bg-slate-900/70 px-2 py-0.5 text-xs text-white">{beforeLabel}</span>
          <span className="absolute right-2 top-2 rounded bg-slate-900/70 px-2 py-0.5 text-xs text-white">{afterLabel}</span>
          <input
            type="range"
            min={0}
            max={100}
            value={pos}
            onChange={(e) => setPos(Number(e.target.value))}
            aria-label={`Compare ${beforeLabel} and ${afterLabel}`}
            className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
          />
        </>
      )}
    </div>
  );
}
