import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SUBMISSION_STATUS_VARIANT } from "@/lib/utils";
import type { FormSubmission } from "@/types";

/** Shared submissions grid — used by the moderation queue (AdminPage, via
 * ReviewDialog), and by the read-only campaign-manager/aspirant views (via
 * SubmissionAuditPanel). Only the action button's label and what it opens
 * differ between callers. */
export function SubmissionsTable({
  submissions,
  onSelect,
  actionLabel = "View",
  emptyLabel = "Nothing here.",
}: {
  submissions: FormSubmission[];
  onSelect: (id: string) => void;
  actionLabel?: string;
  emptyLabel?: string;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Station</TableHead>
          <TableHead>Form</TableHead>
          <TableHead>Agent</TableHead>
          <TableHead className="text-right">Confidence</TableHead>
          <TableHead>Status</TableHead>
          <TableHead />
        </TableRow>
      </TableHeader>
      <TableBody>
        {submissions.map((s) => (
          <TableRow key={s.id}>
            <TableCell className="font-medium">{s.station_name}</TableCell>
            <TableCell>{s.form_type}</TableCell>
            <TableCell className="text-muted-foreground">{s.agent_name}</TableCell>
            <TableCell className="text-right font-mono tabular-nums">{s.ocr_confidence_avg?.toFixed(0) ?? "—"}%</TableCell>
            <TableCell>
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant={SUBMISSION_STATUS_VARIANT[s.status] ?? "neutral"}>{s.status.replace("_", " ")}</Badge>
                {s.warnings.length > 0 && <Badge variant="destructive">flagged</Badge>}
              </div>
            </TableCell>
            <TableCell>
              <Button size="sm" variant="outline" onClick={() => onSelect(s.id)}>
                {actionLabel}
              </Button>
            </TableCell>
          </TableRow>
        ))}
        {submissions.length === 0 && (
          <TableRow>
            <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
              {emptyLabel}
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
