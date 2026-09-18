import { Badge } from "@/components/ui/badge";
import type { VerificationLogEntry } from "@/types";

const ACTION_LABEL: Record<string, string> = {
  manual_correct: "Corrected a figure",
  approve: "Approved",
  reject: "Rejected",
  mark_duplicate: "Marked duplicate",
  auto_flag: "Auto-flagged",
};

/** Chronological audit trail for a submission — who touched it, when, and
 * (for a manual_correct row) exactly which candidate's figure changed and
 * what it changed from/to. This is the piece that used to be fetched
 * (FormSubmission.logs) but never rendered anywhere in the app. */
export function VerificationLogList({ logs }: { logs: VerificationLogEntry[] }) {
  if (logs.length === 0) {
    return <p className="text-sm text-muted-foreground">No corrections or review actions on this submission yet.</p>;
  }

  return (
    <ul className="flex flex-col gap-2">
      {[...logs].reverse().map((log) => (
        <li key={log.id} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm">
          <div className="flex items-baseline gap-2">
            <Badge variant={log.action === "reject" ? "destructive" : log.action === "manual_correct" ? "warning" : "neutral"}>
              {ACTION_LABEL[log.action] ?? log.action}
            </Badge>
            <span>
              {log.action === "manual_correct" && log.candidate_name ? (
                <>
                  <span className="font-medium">{log.candidate_name}</span>:{" "}
                  <span className="font-mono tabular-nums text-muted-foreground line-through decoration-1">
                    {log.old_value}
                  </span>{" "}
                  <span className="font-mono tabular-nums">→ {log.new_value}</span>
                </>
              ) : (
                <span className="text-muted-foreground">{log.reviewer_name ?? "Unknown reviewer"}</span>
              )}
            </span>
          </div>
          <div className="flex items-baseline gap-2 text-xs text-muted-foreground">
            {log.action === "manual_correct" && <span>{log.reviewer_name ?? "Unknown reviewer"}</span>}
            <span>{new Date(log.created_at).toLocaleString()}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
