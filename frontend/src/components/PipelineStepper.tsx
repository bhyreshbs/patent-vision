import { STAGES, stageStates, type StageState } from "@/lib/pipeline";
import type { ImageStatus } from "@/lib/types";

const DOT: Record<StageState, string> = {
  done: "bg-emerald-500 text-white",
  failed: "bg-red-500 text-white",
  active: "animate-pulse bg-blue-500 text-white",
  pending: "bg-slate-200 text-slate-500",
};
const ICON: Record<StageState, string> = { done: "✓", failed: "!", active: "•", pending: "" };

export function PipelineStepper({ status, failedStage }: { status: ImageStatus; failedStage: string | null }) {
  const states = stageStates(status, failedStage);
  return (
    <ol className="grid grid-cols-4 gap-y-3 sm:grid-cols-8" aria-label="Processing pipeline">
      {STAGES.map((stage, i) => (
        <li key={stage.key} className="flex flex-col items-center gap-1.5 text-center" data-state={states[i]}>
          <div className="flex w-full items-center">
            <span className={`h-0.5 flex-1 ${i === 0 ? "invisible" : states[i] === "done" || states[i] === "failed" ? "bg-emerald-400" : "bg-slate-200"}`} />
            <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${DOT[states[i]]}`}>
              {ICON[states[i]]}
            </span>
            <span className={`h-0.5 flex-1 ${i === STAGES.length - 1 ? "invisible" : states[i] === "done" ? "bg-emerald-400" : "bg-slate-200"}`} />
          </div>
          <span className={`text-[11px] leading-tight ${states[i] === "failed" ? "font-semibold text-red-700" : "text-slate-600"}`}>
            {stage.label}
          </span>
        </li>
      ))}
    </ol>
  );
}
