import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CandidateBars } from "@/components/dashboard/CandidateBars";
import { formatNumber } from "@/lib/utils";
import type { GroupingLevel, VotesByGroup } from "@/types";

const LEVEL_LABEL: Record<GroupingLevel, string> = {
  county: "County",
  constituency: "Constituency",
  ward: "Ward",
  station: "Station",
};

function leadingCandidate(votes: Record<string, number>, candidates: { candidate_id: string; full_name: string }[]) {
  let best: { name: string; votes: number } | null = null;
  for (const c of candidates) {
    const v = votes[c.candidate_id] ?? 0;
    if (!best || v > best.votes) best = { name: c.full_name, votes: v };
  }
  return best;
}

export function RegionalBreakdown({ data }: { data: VotesByGroup }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (data.groups.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No {LEVEL_LABEL[data.level].toLowerCase()}s have reported yet — each row here sums every counted submission
        within one {data.level}.
      </p>
    );
  }

  // Many-aspirant races don't fit as table columns — each row shows just
  // the leading candidate; click a row to expand the full per-candidate
  // breakdown (CandidateBars, same component as the Totals card).
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-8" />
          <TableHead>{LEVEL_LABEL[data.level]}</TableHead>
          <TableHead>Leading</TableHead>
          <TableHead className="text-right">Total</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.groups.map((g) => {
          const isOpen = expanded === g.group_id;
          const total = Object.values(g.votes).reduce((sum, v) => sum + v, 0);
          const leader = leadingCandidate(g.votes, data.candidates);
          return (
            <Fragment key={g.group_id}>
              <TableRow className="cursor-pointer select-none" onClick={() => setExpanded(isOpen ? null : g.group_id)}>
                <TableCell className="text-muted-foreground">
                  {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                </TableCell>
                <TableCell className="font-medium">{g.group_name}</TableCell>
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
                <TableCell className="text-right font-mono tabular-nums font-semibold">{total}</TableCell>
              </TableRow>
              {isOpen && (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={4} className="bg-muted/30 py-4">
                    <CandidateBars
                      rows={[...data.candidates]
                        .map((c) => ({ label: c.full_name, votes: g.votes[c.candidate_id] ?? 0 }))
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
