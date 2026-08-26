import { formatNumber } from "@/lib/utils";

const COLORS = ["var(--color-cand-1)", "var(--color-cand-2)", "var(--color-cand-3)", "var(--color-cand-4)"];

export function CandidateBars({ rows }: { rows: { label: string; votes: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.votes));
  return (
    <div className="flex flex-col gap-2.5">
      {rows.map((row, i) => (
        <div key={row.label} className="flex items-center gap-3">
          <span className="w-28 shrink-0 truncate text-sm text-muted-foreground">{row.label}</span>
          <div className="h-3.5 flex-1 overflow-hidden rounded bg-muted">
            <div
              className="h-full rounded transition-[width] duration-700"
              style={{ width: `${(row.votes / max) * 100}%`, background: COLORS[i % COLORS.length] }}
            />
          </div>
          <span className="w-16 shrink-0 text-right font-mono text-sm tabular-nums">{formatNumber(row.votes)}</span>
        </div>
      ))}
    </div>
  );
}
