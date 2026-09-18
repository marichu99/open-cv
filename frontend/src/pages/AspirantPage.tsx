import { useState } from "react";
import { Link } from "react-router-dom";
import { useAgentsWithCoverage, useSubmissionsFeed } from "@/lib/hooks";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { SubmissionsTable } from "@/components/dashboard/SubmissionsTable";
import { SubmissionAuditPanel } from "@/components/dashboard/SubmissionAuditPanel";
import { positionLabel } from "@/lib/utils";

export function AspirantPage() {
  const { agents } = useAgentsWithCoverage();
  const { data: submissions } = useSubmissionsFeed({});
  const [activeId, setActiveId] = useState<string | null>(null);

  const uploaded = agents.filter((a) => a.latest_submission_status !== null && a.latest_submission_status !== undefined);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Aspirant overview</h1>
        <p className="text-sm text-muted-foreground">
          Which field agents have reported in, and every submitted form with its full correction history. For the live
          tally itself, see the <Link to="/dashboard" className="underline">public dashboard</Link>.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Field agent coverage</CardTitle>
          <CardDescription>
            {uploaded.length} of {agents.filter((a) => a.assigned_station_id).length} assigned agents have uploaded a
            form so far
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Agent</TableHead>
                <TableHead>Station</TableHead>
                <TableHead>Position</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last upload</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {agents
                .filter((a) => a.assigned_station_id)
                .map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="font-medium">{a.full_name}</TableCell>
                    <TableCell className="text-muted-foreground">{a.assigned_station_name}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {a.position_names.map((name) => (
                          <Badge key={name} variant="neutral">
                            {positionLabel(name)}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell>
                      {a.has_tallied_submission ? (
                        <Badge variant="success">Counted</Badge>
                      ) : a.latest_submission_status ? (
                        <Badge variant="warning">Uploaded, pending</Badge>
                      ) : (
                        <Badge variant="destructive">Not yet uploaded</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {a.latest_submission_at ? new Date(a.latest_submission_at).toLocaleString() : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              {agents.filter((a) => a.assigned_station_id).length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                    No agents assigned yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Submissions</CardTitle>
          <CardDescription>{submissions.length} shown, most recent first</CardDescription>
        </CardHeader>
        <CardContent>
          <SubmissionsTable submissions={submissions} onSelect={setActiveId} />
        </CardContent>
      </Card>

      <SubmissionAuditPanel submissionId={activeId} onClose={() => setActiveId(null)} />
    </div>
  );
}
