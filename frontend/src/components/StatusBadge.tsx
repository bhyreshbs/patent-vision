import { STATUS_STYLES } from "@/lib/format";
import type { ImageStatus } from "@/lib/types";

export function StatusBadge({ status }: { status: ImageStatus }) {
  const pulsing = status === "Queued" || status === "Processing";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_STYLES[status]}`}
      data-testid="status-badge"
    >
      {pulsing && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {status}
    </span>
  );
}
