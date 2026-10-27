import { ApiError } from "@/lib/api";

export function ErrorBanner({ error, onDismiss }: { error: unknown; onDismiss?: () => void }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  const next = error instanceof ApiError ? error.nextAction : undefined;
  return (
    <div role="alert" className="flex items-start justify-between gap-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      <div>
        <p className="font-medium">{message}</p>
        {next && <p className="mt-0.5 text-red-700">{next}</p>}
      </div>
      {onDismiss && (
        <button onClick={onDismiss} className="text-red-700 hover:text-red-900" aria-label="Dismiss error">
          ✕
        </button>
      )}
    </div>
  );
}
