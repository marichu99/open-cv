import { ArrowLeft, Download } from "lucide-react";
import { useSubmission, useSubmissionImage } from "@/lib/hooks";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { VerificationLogList } from "@/components/dashboard/VerificationLogList";
import { cn } from "@/lib/utils";

// Same idea as the backend's own `_image_response` attachment naming
// (api/submissions.py) — a station + form code beats a bare "image.jpg"
// once a coordinator has more than one of these downloaded at once.
const EXT_BY_CONTENT_TYPE: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
};

function downloadFileName(stationName: string, formType: string, contentType: string | null): string {
  const ext = (contentType && EXT_BY_CONTENT_TYPE[contentType]) || "jpg";
  const slug = stationName.trim().replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return `${slug || "form"}-form${formType}.${ext}`;
}

/** Read-only submission detail: the original form photo, side by side with
 * each candidate's detected-vs-effective figures, plus the full audit log.
 * Used by campaign managers (scoped to their own agents' submissions by the
 * backend) and the aspirant (unscoped) to see what an agent uploaded, what
 * if anything was corrected, and by whom — without the correction inputs or
 * approve/reject actions that ReviewDialog offers a coordinator/admin.
 *
 * `onBack` is optional — pass it when this panel was opened *from*
 * somewhere worth returning to (e.g. DiscrepancyReportDialog's "View").
 * Omitted, no back affordance shows and the X/overlay just closes (the
 * plain Submissions-table "View" case). `onClose` always fully closes,
 * even when `onBack` is present — the two are deliberately different
 * actions, not aliases of each other. */
export function SubmissionAuditPanel({
  submissionId,
  onClose,
  onBack,
}: {
  submissionId: string | null;
  onClose: () => void;
  onBack?: () => void;
}) {
  const { data: submission } = useSubmission(submissionId);
  const { imageSrc, contentType } = useSubmissionImage(submissionId);

  // Same arithmetic the backend's own gate checks at finalize time
  // (api/submissions.py's _arithmetic_ok) — recomputed here so the mismatch
  // the warning banner names is actually visible in the numbers themselves,
  // not just asserted in a sentence above them.
  const candidateTotal = submission?.vote_records?.reduce((sum, v) => sum + v.effective_votes, 0) ?? 0;
  const computedTotal = candidateTotal + (submission?.rejected_ballots ?? 0);
  const declaredTotal = submission?.total_votes_cast ?? null;
  const totalsMismatch = declaredTotal !== null && computedTotal !== declaredTotal;

  return (
    <Dialog open={!!submissionId} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl">
        {submission && (
          <>
            {onBack && (
              <button
                type="button"
                onClick={onBack}
                className="mb-3 flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                <ArrowLeft className="size-4" />
                Back to discrepancy report
              </button>
            )}
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
              <div className="relative overflow-hidden rounded-md border border-border bg-muted">
                {imageSrc ? (
                  <>
                    <img src={imageSrc} alt="Submitted form" className="w-full object-cover" />
                    <a
                      href={imageSrc}
                      download={downloadFileName(submission.station_name, submission.form_type, contentType)}
                      title="Download this form photo"
                      className="absolute right-2 top-2 flex size-8 items-center justify-center rounded-full bg-background/90 text-foreground shadow-sm ring-1 ring-border transition-colors hover:bg-background"
                    >
                      <Download className="size-4" />
                    </a>
                  </>
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
                <div className={cn("flex justify-between text-sm", totalsMismatch && "text-destructive")}>
                  <span className={totalsMismatch ? "" : "text-muted-foreground"}>Candidates + rejected</span>
                  <span className="font-mono tabular-nums">{computedTotal}</span>
                </div>
                <div className={cn("flex justify-between text-sm font-medium", totalsMismatch && "text-destructive")}>
                  <span>Total votes cast{totalsMismatch ? " (declared on form)" : ""}</span>
                  <span className="font-mono tabular-nums">{submission.total_votes_cast}</span>
                </div>
                {totalsMismatch && (
                  <p className="rounded-md bg-destructive/10 px-2.5 py-1.5 text-xs text-destructive">
                    Off by {Math.abs((declaredTotal ?? 0) - computedTotal)} —{" "}
                    {(declaredTotal ?? 0) > computedTotal
                      ? "the form's declared total is higher than what candidates + rejected ballots add up to."
                      : "candidates + rejected ballots add up to more than the form's declared total."}
                  </p>
                )}
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
