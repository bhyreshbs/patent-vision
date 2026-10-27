export function LogoMark({ className = "h-7 w-7", light = false }: { className?: string; light?: boolean }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <rect width="32" height="32" rx="8" fill={light ? "rgba(255,255,255,0.12)" : "#0f172a"} />
      <path d="M8 22V10h7a4 4 0 0 1 0 8H8" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M19 10l3.5 12L26 10" fill="none" stroke="#60a5fa" strokeWidth="2.2" strokeLinejoin="round" />
    </svg>
  );
}

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <span className={`flex items-center gap-2 text-[17px] font-semibold tracking-tight ${light ? "text-white" : "text-slate-900"}`}>
      <LogoMark light={light} />
      PatentVision <span className={`font-normal ${light ? "text-slate-300" : "text-slate-500"}`}>AI</span>
    </span>
  );
}
