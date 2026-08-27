import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { GroupingLevel, VotesByGroup } from "@/types";

const LEVEL_LABEL: Record<GroupingLevel, string> = {
  county: "County",
  constituency: "Constituency",
  ward: "Ward",
  station: "Station",
};

export function RegionalBreakdown({ data }: { data: VotesByGroup }) {
  if (data.groups.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No {LEVEL_LABEL[data.level].toLowerCase()}s have reported yet — each row here sums every counted submission
        within one {data.level}.
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{LEVEL_LABEL[data.level]}</TableHead>
          {data.candidates.map((c) => (
            <TableHead key={c.candidate_id} className="text-right">
              {c.full_name}
            </TableHead>
          ))}
          <TableHead className="text-right">Total</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.groups.map((g) => {
          const total = Object.values(g.votes).reduce((sum, v) => sum + v, 0);
          return (
            <TableRow key={g.group_id}>
              <TableCell className="font-medium">{g.group_name}</TableCell>
              {data.candidates.map((c) => (
                <TableCell key={c.candidate_id} className="text-right font-mono tabular-nums">
                  {g.votes[c.candidate_id] ?? 0}
                </TableCell>
              ))}
              <TableCell className="text-right font-mono tabular-nums font-semibold">{total}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
