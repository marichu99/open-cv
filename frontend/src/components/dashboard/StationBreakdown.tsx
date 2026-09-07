import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CandidateBars } from "@/components/dashboard/CandidateBars";
import { formatNumber } from "@/lib/utils";
import type { VotesByStation } from "@/types";

function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function leadingCandidate(votes: Record<string, number>, candidates: { candidate_id: string; full_name: string }[]) {
  let best: { name: string; votes: number } | null = null;
  for (const c of candidates) {
    const v = votes[c.candidate_id] ?? 0;
    if (!best || v > best.votes) best = { name: c.full_name, votes: v };
  }
  return best;
}

export function StationBreakdown({ data }: { data: VotesByStation }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (data.stations.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No stations have reported yet — each row here is one polling station's counted submission.
      </p>
    );
  }

  // Many-aspirant races (10+ candidates) don't fit as table columns — each
  // row shows just the leading candidate; click a row to expand the full
  // per-candidate breakdown (CandidateBars, same component as the Totals
  // card) below it.
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-8" />
          <TableHead>Station</TableHead>
          <TableHead>Reported</TableHead>
          <TableHead>Leading</TableHead>
          <TableHead className="text-right">Total</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.stations.map((s) => {
          const rowKey = `${s.station_id}-${s.stream_number}`;
          const isOpen = expanded === rowKey;
          const leader = leadingCandidate(s.votes, data.candidates);
          // The station's *known* stream_count (not just how many streams
          // happen to be in the current result set) decides whether to show
          // "Stream N of M" — so a station with 3 streams reads as "Stream 1
          // of 3" the moment the first one reports, rather than looking like
          // an ordinary single-stream station until the others catch up.
          const displayName = s.stream_count > 1 ? `${s.station_name} · Stream ${s.stream_number} of ${s.stream_count}` : s.station_name;
          return (
            <Fragment key={rowKey}>
              <TableRow
                className="cursor-pointer select-none"
                onClick={() => setExpanded(isOpen ? null : rowKey)}
              >
                <TableCell className="text-muted-foreground">
                  {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                </TableCell>
                <TableCell className="font-medium">
                  <div>{displayName}</div>
                  <div className="text-xs font-normal text-muted-foreground">
                    Uploaded by {s.agent_name ?? "—"} · {formatTimestamp(s.uploaded_at)}
                  </div>
                </TableCell>
                <TableCell className="text-muted-foreground">{formatTimestamp(s.reported_at)}</TableCell>
                <TableCell className="text-sm">
                  {leader ? (
                    <span>
                      {leader.name}{" "}
                      <span className="font-mono text-muted-foreground tabular-nums">({formatNumber(leader.votes)})</span>
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums font-semibold">
                  {s.total_votes_cast ?? "—"}
                </TableCell>
              </TableRow>
              {isOpen && (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={5} className="bg-muted/30 py-4">
                    <CandidateBars
                      rows={[...data.candidates]
                        .map((c) => ({ label: c.full_name, votes: s.votes[c.candidate_id] ?? 0 }))
                        .sort((a, b) => b.votes - a.votes)}
                    />
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          );
        })}
      </TableBody>
    </Table>
  );
}
