import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ReviewDialog } from "@/components/admin/ReviewDialog";
import type { FormSubmission, SubmissionStatus } from "@/types";

const STATUS_OPTIONS: { value: SubmissionStatus | "all" | "discrepancies"; label: string }[] = [
  { value: "pending_review", label: "Pending review" },
  { value: "discrepancies", label: "Discrepancies (flagged)" },
  { value: "auto_approved", label: "Auto-approved" },
  { value: "manually_approved", label: "Manually approved" },
  { value: "rejected", label: "Rejected" },
  { value: "duplicate", label: "Duplicate" },
  { value: "all", label: "All statuses" },
];

const STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "neutral"> = {
  auto_approved: "success",
  manually_approved: "success",
  pending_review: "warning",
  rejected: "destructive",
  duplicate: "destructive",
  draft: "neutral",
};

export function AdminPage() {
  const [status, setStatus] = useState<string>("pending_review");
  const [submissions, setSubmissions] = useState<FormSubmission[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  const load = useCallback(() => {
    const params =
      status === "all"
        ? {}
        : status === "discrepancies"
        ? { status: "pending_review", has_warnings: "true" }
        : { status };
    api.get<FormSubmission[]>("/api/submissions", { params }).then((res) => setSubmissions(res.data));
  }, [status]);

  useEffect(() => load(), [load]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold">Moderation queue</h1>
          <p className="text-sm text-muted-foreground">Review flagged submissions, correct misreads, approve or reject.</p>
        </div>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Submissions</CardTitle>
          <CardDescription>{submissions.length} shown</CardDescription>
        </CardHeader>
        <CardContent>
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
                  <TableCell className="text-right font-mono tabular-nums">
                    {s.ocr_confidence_avg?.toFixed(0) ?? "—"}%
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge variant={STATUS_VARIANT[s.status] ?? "neutral"}>{s.status.replace("_", " ")}</Badge>
                      {s.warnings.length > 0 && <Badge variant="destructive">flagged</Badge>}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Button size="sm" variant="outline" onClick={() => setActiveId(s.id)}>
                      Review
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {submissions.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                    Nothing here.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <ReviewDialog submissionId={activeId} onClose={() => setActiveId(null)} onDone={load} />
    </div>
  );
}
