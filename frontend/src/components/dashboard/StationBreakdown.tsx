import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { VotesByStation } from "@/types";

function formatReportedAt(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function StationBreakdown({ data }: { data: VotesByStation }) {
  if (data.stations.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No stations have reported yet — each row here is one polling station's counted submission.
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Station</TableHead>
          <TableHead>Reported</TableHead>
          {data.candidates.map((c) => (
            <TableHead key={c.candidate_id} className="text-right">
              {c.full_name}
            </TableHead>
          ))}
          <TableHead className="text-right">Total</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.stations.map((s) => (
          <TableRow key={s.station_id}>
            <TableCell className="font-medium">{s.station_name}</TableCell>
            <TableCell className="text-muted-foreground">{formatReportedAt(s.reported_at)}</TableCell>
            {data.candidates.map((c) => (
              <TableCell key={c.candidate_id} className="text-right font-mono tabular-nums">
                {s.votes[c.candidate_id] ?? 0}
              </TableCell>
            ))}
            <TableCell className="text-right font-mono tabular-nums font-semibold">
              {s.total_votes_cast ?? "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
