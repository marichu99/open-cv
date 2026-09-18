import { useSubmission, useSubmissionImage } from "@/lib/hooks";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { VerificationLogList } from "@/components/dashboard/VerificationLogList";

/** Read-only submission detail: the original form photo, side by side with
 * each candidate's detected-vs-effective figures, plus the full audit log.
 * Used by campaign managers (scoped to their own agents' submissions by the
 * backend) and the aspirant (unscoped) to see what an agent uploaded, what
 * if anything was corrected, and by whom — without the correction inputs or
 * approve/reject actions that ReviewDialog offers a coordinator/admin. */
export function SubmissionAuditPanel({ submissionId, onClose }: { submissionId: string | null; onClose: () => void }) {
  const { data: submission } = useSubmission(submissionId);
  const imageSrc = useSubmissionImage(submissionId);

  return (
    <Dialog open={!!submissionId} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl">
        {submission && (
          <>
            <DialogHeader>
              <DialogTitle>
                {submission.station_name} — Form {submission.form_type}
              </DialogTitle>
              <DialogDescription>
                Uploaded by {submission.agent_name} · overall confidence {submission.ocr_confidence_avg?.toFixed(0)}%
              </DialogDescription>
            </DialogHeader>

            {submission.warnings.length > 0 && (
              <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                {submission.warnings.join(" · ")}
              </div>
            )}

            <div className="grid gap-5 sm:grid-cols-[minmax(0,220px)_1fr]">
              <div className="overflow-hidden rounded-md border border-border bg-muted">
                {imageSrc ? (
                  <img src={imageSrc} alt="Submitted form" className="w-full object-cover" />
                ) : (
                  <div className="flex h-48 items-center justify-center text-xs text-muted-foreground">Loading image…</div>
                )}
              </div>

              <div className="flex flex-col gap-3">
                {submission.vote_records?.map((v) => (
                  <div key={v.id} className="flex items-center gap-3">
                    <span className="flex-1 text-sm">{v.candidate_name}</span>
                    <Badge variant={v.field_confidence < 85 ? "warning" : "success"}>{v.field_confidence.toFixed(0)}%</Badge>
                    {v.manually_overridden && (
                      <span className="font-mono tabular-nums text-muted-foreground line-through decoration-1">
                        {v.votes_detected}
                      </span>
                    )}
                    <span className="w-12 text-right font-mono text-sm font-medium tabular-nums">{v.effective_votes}</span>
                  </div>
                ))}
                <Separator className="my-1" />
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Rejected ballots</span>
                  <span className="font-mono tabular-nums">{submission.rejected_ballots}</span>
                </div>
                <div className="flex justify-between text-sm font-medium">
                  <span>Total votes cast</span>
                  <span className="font-mono tabular-nums">{submission.total_votes_cast}</span>
                </div>
              </div>
            </div>

            <Separator className="my-4" />

            <h3 className="mb-2 text-sm font-semibold">Audit log</h3>
            <VerificationLogList logs={submission.logs ?? []} />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
