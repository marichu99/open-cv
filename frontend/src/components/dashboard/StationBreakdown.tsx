import { Fragment, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Download, Eye, EyeOff } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { CandidateBars } from "@/components/dashboard/CandidateBars";
import { formatNumber } from "@/lib/utils";
import { API_URL } from "@/lib/api";
import type { VotesByStation } from "@/types";

function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString([], { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function leadingCandidate(votes: Record<string, number>, candidates: { candidate_id: string; full_name: string }[]) {
  let best: { name: string; votes: number } | null = null;
  for (const c of candidates) {
    const v = votes[c.candidate_id] ?? 0;
    if (!best || v > best.votes) best = { name: c.full_name, votes: v };
  }
  return best;
}

/** Preview state per row, keyed by rowKey — separate from `expanded` so
 * closing/reopening the row doesn't refetch an image already pulled once. */
type PreviewState = { status: "loading" | "loaded" | "error"; objectUrl?: string };

export function StationBreakdown({ data }: { data: VotesByStation }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [previews, setPreviews] = useState<Record<string, PreviewState>>({});
  const [previewOpen, setPreviewOpen] = useState<Record<string, boolean>>({});

  // Object URLs are only ever released on unmount, not when a preview is
  // toggled closed — cheap to keep around for a quick re-toggle, and this
  // panel's lifetime (one dashboard session) is short enough that holding a
  // handful of them never meaningfully adds up. Synced in an effect (not
  // during render) so the unmount cleanup below always sees the latest
  // value without needing `previews` itself in its dependency array.
  const previewsRef = useRef(previews);
  useEffect(() => {
    previewsRef.current = previews;
  }, [previews]);
  useEffect(() => {
    return () => {
      for (const p of Object.values(previewsRef.current)) {
        if (p.objectUrl) URL.revokeObjectURL(p.objectUrl);
      }
    };
  }, []);

  if (data.stations.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No stations have reported yet — each row here is one polling station's counted submission.
      </p>
    );
  }

  function togglePreview(rowKey: string, submissionId: string) {
    setPreviewOpen((prev) => ({ ...prev, [rowKey]: !prev[rowKey] }));
    if (previews[rowKey]) return; // already fetched (or in flight) once
    setPreviews((prev) => ({ ...prev, [rowKey]: { status: "loading" } }));
    // Public route (see api/submissions.py's get_public_image) — no auth
    // header needed, unlike the coordinator review dialog's /image route.
    fetch(`${API_URL}/api/submissions/${submissionId}/public-image`)
      .then((res) => {
        if (!res.ok) throw new Error(String(res.status));
        return res.blob();
      })
      .then((blob) => {
        const objectUrl = URL.createObjectURL(blob);
        setPreviews((prev) => ({ ...prev, [rowKey]: { status: "loaded", objectUrl } }));
      })
      .catch(() => {
        setPreviews((prev) => ({ ...prev, [rowKey]: { status: "error" } }));
      });
  }

  // Many-aspirant races (10+ candidates) don't fit as table columns — each
  // row shows just the leading candidate; click a row to expand the full
  // per-candidate breakdown (CandidateBars, same component as the Totals
  // card) below it.
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-8" />
          <TableHead>Station</TableHead>
          <TableHead>Reported</TableHead>
          <TableHead>Leading</TableHead>
          <TableHead className="text-right">Total</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.stations.map((s) => {
          const rowKey = `${s.station_id}-${s.stream_number}`;
          const isOpen = expanded === rowKey;
          const leader = leadingCandidate(s.votes, data.candidates);
          const showPreview = !!previewOpen[rowKey];
          const preview = previews[rowKey];
          // The station's *known* stream_count (not just how many streams
          // happen to be in the current result set) decides whether to show
          // "Stream N of M" — so a station with 3 streams reads as "Stream 1
          // of 3" the moment the first one reports, rather than looking like
          // an ordinary single-stream station until the others catch up.
          const displayName = s.stream_count > 1 ? `${s.station_name} · Stream ${s.stream_number} of ${s.stream_count}` : s.station_name;
          return (
            <Fragment key={rowKey}>
              <TableRow
                className="cursor-pointer select-none"
                onClick={() => setExpanded(isOpen ? null : rowKey)}
              >
                <TableCell className="text-muted-foreground">
                  {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                </TableCell>
                <TableCell className="font-medium">
                  <div>{displayName}</div>
                  <div className="text-xs font-normal text-muted-foreground">
                    Uploaded by {s.agent_name ?? "—"} · {formatTimestamp(s.uploaded_at)}
                  </div>
                </TableCell>
                <TableCell className="text-muted-foreground">{formatTimestamp(s.reported_at)}</TableCell>
                <TableCell className="text-sm">
                  {leader ? (
                    <span>
                      {leader.name}{" "}
                      <span className="font-mono text-muted-foreground tabular-nums">({formatNumber(leader.votes)})</span>
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums font-semibold">
                  {s.total_votes_cast ?? "—"}
                </TableCell>
              </TableRow>
              {isOpen && (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={5} className="bg-muted/30 py-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <span className="text-xs text-muted-foreground">
                        Compare against the uploaded form to independently verify these figures.
                      </span>
                      <div className="flex shrink-0 gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            togglePreview(rowKey, s.submission_id);
                          }}
                        >
                          {showPreview ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                          {showPreview ? "Hide preview" : "Preview form"}
                        </Button>
                        <Button variant="outline" size="sm" asChild>
                          <a
                            href={`${API_URL}/api/submissions/${s.submission_id}/public-image`}
                            download
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Download className="size-3.5" />
                            Download form
                          </a>
                        </Button>
                      </div>
                    </div>

                    <div className={showPreview ? "grid gap-4 sm:grid-cols-[minmax(0,260px)_1fr]" : ""}>
                      {showPreview && (
                        <div className="overflow-hidden rounded-md border border-border bg-background">
                          {preview?.status === "loaded" && preview.objectUrl && (
                            // An iframe (not <img>) so the browser's native
                            // image viewer handles zoom/pan — these scans
                            // run several thousand pixels wide and the
                            // handwritten vote counts need to be zoomable to
                            // actually verify against the tally.
                            <iframe
                              src={preview.objectUrl}
                              title={`Submitted form for ${s.station_name}`}
                              className="h-[28rem] w-full"
                            />
                          )}
                          {preview?.status === "loading" && (
                            <div className="flex h-48 items-center justify-center text-xs text-muted-foreground">Loading form…</div>
                          )}
                          {preview?.status === "error" && (
                            <div className="flex h-48 items-center justify-center px-4 text-center text-xs text-muted-foreground">
                              Couldn't load the form image.
                            </div>
                          )}
                        </div>
                      )}
                      <CandidateBars
                        rows={[...data.candidates]
                          .map((c) => ({ label: c.full_name, votes: s.votes[c.candidate_id] ?? 0 }))
                          .sort((a, b) => b.votes - a.votes)}
                      />
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          );
        })}
      </TableBody>
    </Table>
  );
}
