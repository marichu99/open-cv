import { useState } from "react";
import { useSubmissionsFeed } from "@/lib/hooks";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ReviewDialog } from "@/components/admin/ReviewDialog";
import { SubmissionsTable } from "@/components/dashboard/SubmissionsTable";
import type { SubmissionStatus } from "@/types";

const STATUS_OPTIONS: { value: SubmissionStatus | "all" | "discrepancies"; label: string }[] = [
  { value: "discrepancies", label: "Discrepancies (flagged)" },
  { value: "pending_review", label: "Pending review (legacy)" },
  { value: "auto_approved", label: "Auto-approved" },
  { value: "manually_approved", label: "Manually approved" },
  { value: "rejected", label: "Rejected" },
  { value: "duplicate", label: "Duplicate" },
  { value: "all", label: "All statuses" },
];

export function AdminPage() {
  const [status, setStatus] = useState<string>("discrepancies");
  const [activeId, setActiveId] = useState<string | null>(null);

  const params: Record<string, string> =
    status === "all"
      ? {}
      : status === "discrepancies"
      ? { has_warnings: "true" }
      : { status };
  const { data: submissions, refresh: load } = useSubmissionsFeed(params);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold">Moderation queue</h1>
          <p className="text-sm text-muted-foreground">
            Submissions count toward the tally the moment an agent submits — this grid is for spot-checking forms the
            model flagged (ambiguous reads, mismatched totals, low confidence) and correcting them if needed.
          </p>
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
          <SubmissionsTable submissions={submissions} onSelect={setActiveId} actionLabel="Review" />
        </CardContent>
      </Card>

      <ReviewDialog submissionId={activeId} onClose={() => setActiveId(null)} onDone={load} />
    </div>
  );
}
