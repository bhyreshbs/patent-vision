"use client";

import { useRef, useState } from "react";

interface Props {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
  hint?: string;
}

export function DropZone({ onFiles, disabled, hint }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  function take(list: FileList | null) {
    if (!list?.length || disabled) return;
    onFiles(Array.from(list));
    if (input.current) input.current.value = "";
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-disabled={disabled}
      aria-label="Upload product photos"
      onClick={() => !disabled && input.current?.click()}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !disabled && input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        take(e.dataTransfer.files);
      }}
      className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition ${
        over ? "border-blue-500 bg-blue-50" : "border-slate-300 bg-slate-50/60 hover:border-slate-400 hover:bg-slate-50"
      } ${disabled ? "pointer-events-none opacity-60" : ""}`}
    >
      <svg viewBox="0 0 24 24" className="h-8 w-8 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        <path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <p className="text-sm font-medium text-slate-800">
        Drop product photos here or <span className="text-blue-700 underline">browse</span>
      </p>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
      <input
        ref={input}
        type="file"
        multiple
        accept="image/jpeg,image/png,image/webp"
        aria-label="Choose images"
        className="hidden"
        onChange={(e) => take(e.target.files)}
      />
    </div>
  );
}
