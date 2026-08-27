import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, API_URL, getToken } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { FormSubmission } from "@/types";

export function ReviewDialog({
  submissionId,
  onClose,
  onDone,
}: {
  submissionId: string | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [submission, setSubmission] = useState<FormSubmission | null>(null);
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [imageSrc, setImageSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!submissionId) {
      setSubmission(null);
      setImageSrc(null);
      return;
    }
    api.get<FormSubmission>(`/api/submissions/${submissionId}`).then((res) => {
      setSubmission(res.data);
      setCorrections({});
      setNotes("");
    });
    // The image endpoint requires a bearer token, so fetch it as a blob rather than <img src>.
    fetch(`${API_URL}/api/submissions/${submissionId}/image`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((r) => r.blob())
      .then((blob) => setImageSrc(URL.createObjectURL(blob)))
      .catch(() => setImageSrc(null));
  }, [submissionId]);

  async function submitReview(action: "approve" | "reject" | "mark_duplicate") {
    if (!submission) return;
    setBusy(true);
    try {
      const payload = {
        action,
        notes: notes || undefined,
        corrections: Object.entries(corrections)
          .filter(([, v]) => v !== "")
          .map(([candidate_id, v]) => ({ candidate_id, votes_corrected: Number(v) })),
      };
      await api.post(`/api/submissions/${submission.id}/review`, payload);
      toast.success(`Submission ${action.replace("_", " ")}d`);
      onDone();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Review failed");
    } finally {
      setBusy(false);
    }
  }

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
                    <Badge variant={v.field_confidence < 85 ? "warning" : "success"}>
                      {v.field_confidence.toFixed(0)}%
                    </Badge>
                    <span className="w-16 text-right font-mono text-sm tabular-nums text-muted-foreground line-through decoration-1">
                      {v.votes_detected}
                    </span>
                    <Input
                      className="w-24"
                      placeholder="corrected"
                      value={corrections[v.candidate_id] ?? ""}
                      onChange={(e) => setCorrections((c) => ({ ...c, [v.candidate_id]: e.target.value }))}
                    />
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

            <div className="mt-4 flex flex-col gap-1.5">
              <Label htmlFor="notes">Reviewer notes</Label>
              <Textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <Button onClick={() => submitReview("approve")} disabled={busy}>
                Approve
              </Button>
              <Button variant="outline" onClick={() => submitReview("mark_duplicate")} disabled={busy}>
                Mark duplicate
              </Button>
              <Button variant="destructive" onClick={() => submitReview("reject")} disabled={busy}>
                Reject
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
