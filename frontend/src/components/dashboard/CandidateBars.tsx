import { useState } from "react";
import { formatNumber } from "@/lib/utils";

const COLORS = ["var(--color-cand-1)", "var(--color-cand-2)", "var(--color-cand-3)", "var(--color-cand-4)"];

export function CandidateBars({ rows }: { rows: { label: string; votes: number }[] }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const max = Math.max(1, ...rows.map((r) => r.votes));
  const total = rows.reduce((sum, r) => sum + r.votes, 0);

  return (
    <div className="flex flex-col gap-2.5">
      {rows.map((row, i) => {
        const widthPct = (row.votes / max) * 100;
        const sharePct = total > 0 ? (row.votes / total) * 100 : 0;
        const isHovered = hovered === i;
        return (
          <div key={row.label} className="flex items-center gap-3">
            <span className="w-28 shrink-0 truncate text-sm text-muted-foreground">{row.label}</span>
            <div
              className="relative h-3.5 flex-1 overflow-visible rounded bg-muted"
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered((h) => (h === i ? null : h))}
            >
              <div className="h-full overflow-hidden rounded">
                <div
                  className="h-full cursor-default rounded transition-[width,filter] duration-700 ease-out"
                  style={{ width: `${widthPct}%`, background: COLORS[i % COLORS.length], filter: isHovered ? "brightness(1.15)" : undefined }}
                />
              </div>
              <div
                role="tooltip"
                className={`pointer-events-none absolute bottom-full z-10 mb-2 w-max max-w-56 -translate-x-1/2 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-card-foreground shadow-md transition-all duration-150 ${
                  isHovered ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0"
                }`}
                style={{ left: `${Math.min(Math.max(widthPct, 10), 90)}%` }}
              >
                <div className="font-medium">{row.label}</div>
                <div className="text-muted-foreground">
                  {formatNumber(row.votes)} votes · {sharePct.toFixed(1)}% of shown total
                </div>
              </div>
            </div>
            <span className="w-16 shrink-0 text-right font-mono text-sm tabular-nums">{formatNumber(row.votes)}</span>
          </div>
        );
      })}
    </div>
  );
}
