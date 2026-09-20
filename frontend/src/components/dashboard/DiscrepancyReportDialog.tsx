import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import type { DiscrepancyReport, DiscrepancyType } from "@/types";

const TYPE_VARIANT: Record<DiscrepancyType, "success" | "warning" | "destructive" | "neutral"> = {
  agent_correction: "warning",
  extraction_failed: "destructive",
  arithmetic_mismatch: "destructive",
  low_confidence: "warning",
  illegible: "warning",
  duplicate_superseded: "neutral",
  duplicate_reversed: "warning",
};

/** Every correction, duplicate resolution, and extraction-time flag across
 * the caller's own submissions (backend scopes it the same way it scopes
 * the Submissions table — see GET /api/submissions/discrepancy-report),
 * grouped by kind with a ready-to-read sentence per instance rather than
 * raw fields the reader has to interpret themselves. `onSelectSubmission`
 * is expected to also close this dialog before opening the audit panel —
 * kept the caller's call, not this component's, so it stays a dumb display
 * of whatever report it's handed. */
export function DiscrepancyReportDialog({
  open,
  onOpenChange,
  report,
  onSelectSubmission,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  report: DiscrepancyReport | null;
  onSelectSubmission: (submissionId: string) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Discrepancy report</DialogTitle>
          <DialogDescription>
            {report
              ? `Every correction, duplicate resolution, and extraction flag across ${report.total_submissions_in_scope} ` +
                `submission${report.total_submissions_in_scope === 1 ? "" : "s"} — generated ` +
                `${new Date(report.generated_at).toLocaleString()}.`
              : "Loading…"}
          </DialogDescription>
        </DialogHeader>

        {report && report.groups.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No corrections, duplicates, or extraction flags on record for your agents — nothing to report.
          </p>
        )}

        <div className="flex flex-col gap-6">
          {report?.groups.map((group) => (
            <div key={group.type} className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Badge variant={TYPE_VARIANT[group.type] ?? "neutral"}>{group.count}</Badge>
                <h3 className="text-sm font-semibold">{group.label}</h3>
              </div>
              <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
                {group.instances.map((instance, i) => (
                  <li
                    key={`${instance.submission_id}-${i}`}
                    className="flex flex-col items-start justify-between gap-2 p-3 text-sm sm:flex-row sm:items-center sm:gap-3"
                  >
                    <div className="flex flex-col gap-1">
                      <p>{instance.narration}</p>
                      {instance.occurred_at && (
                        <span className="text-xs text-muted-foreground">{new Date(instance.occurred_at).toLocaleString()}</span>
                      )}
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="shrink-0"
                      onClick={() => onSelectSubmission(instance.submission_id)}
                    >
                      View
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
