import { Fragment, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Download, Eye } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { CandidateBars } from "@/components/dashboard/CandidateBars";
import { formatNumber } from "@/lib/utils";
import { API_URL } from "@/lib/api";
import type { VotesByStation, StationTally } from "@/types";

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

function rowKeyFor(s: StationTally) {
  return `${s.station_id}-${s.stream_number}`;
}

function displayNameFor(s: StationTally) {
  // The station's *known* stream_count (not just how many streams happen to
  // be in the current result set) decides whether to show "Stream N of M" —
  // so a station with 3 streams reads as "Stream 1 of 3" the moment the
  // first one reports, rather than looking like an ordinary single-stream
  // station until the others catch up.
  return s.stream_count > 1 ? `${s.station_name} · Stream ${s.stream_number} of ${s.stream_count}` : s.station_name;
}

/** Preview state per row, keyed by rowKey — separate from `expanded` so
 * closing/reopening the row doesn't refetch an image already pulled once. */
type PreviewState = { status: "loading" | "loaded" | "error"; objectUrl?: string };

export function StationBreakdown({ data }: { data: VotesByStation }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [previews, setPreviews] = useState<Record<string, PreviewState>>({});
  // Only one preview modal makes sense open at a time — the rowKey it's for,
  // or null when closed. A single shared Dialog (below) renders whichever
  // station that key points to, rather than mounting one Dialog per row.
  const [previewRowKey, setPreviewRowKey] = useState<string | null>(null);

  // Object URLs are only ever released on unmount, not when a preview modal
  // closes — cheap to keep around for a quick reopen, and this panel's
  // lifetime (one dashboard session) is short enough that holding a handful
  // of them never meaningfully adds up. Synced in an effect (not during
  // render) so the unmount cleanup below always sees the latest value
  // without needing `previews` itself in its dependency array.
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

  function openPreview(rowKey: string, submissionId: string) {
    setPreviewRowKey(rowKey);
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

  const previewStation = data.stations.find((s) => rowKeyFor(s) === previewRowKey) ?? null;
  const previewState = previewRowKey ? previews[previewRowKey] : undefined;

  // Many-aspirant races (10+ candidates) don't fit as table columns — each
  // row shows just the leading candidate; click a row to expand the full
  // per-candidate breakdown (CandidateBars, same component as the Totals
  // card) below it.
  return (
    <>
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
            const rowKey = rowKeyFor(s);
            const isOpen = expanded === rowKey;
            const leader = leadingCandidate(s.votes, data.candidates);
            const displayName = displayNameFor(s);
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
                              openPreview(rowKey, s.submission_id);
                            }}
                          >
                            <Eye className="size-3.5" />
                            Preview form
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
                      <CandidateBars
                        rows={[...data.candidates]
                          .map((c) => ({ label: c.full_name, votes: s.votes[c.candidate_id] ?? 0 }))
                          .sort((a, b) => b.votes - a.votes)}
                      />
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>

      <Dialog open={!!previewStation} onOpenChange={(open) => !open && setPreviewRowKey(null)}>
        <DialogContent overlayClassName="backdrop-blur-sm" className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{previewStation ? displayNameFor(previewStation) : ""}</DialogTitle>
            <DialogDescription>Submitted form — compare against the figures above.</DialogDescription>
          </DialogHeader>
          <div className="flex max-h-[70vh] items-center justify-center overflow-hidden rounded-md border border-border bg-background">
            {previewState?.status === "loaded" && previewState.objectUrl && previewStation && (
              // A plain <img> with object-contain, not an iframe — an
              // iframe hands sizing to the browser's own "image document"
              // fit heuristic, which isn't consistent enough to rely on
              // (some of these scans are several thousand pixels tall, and
              // the iframe ended up scrolling instead of fitting). This way
              // the image is always scaled down to fit inside the modal,
              // guaranteed by CSS rather than browser-internal behavior.
              // Click through to the full-resolution original in a new tab
              // for closer inspection than the fitted view allows.
              <a
                href={previewState.objectUrl}
                target="_blank"
                rel="noreferrer"
                title="Open full resolution in a new tab"
              >
                <img
                  src={previewState.objectUrl}
                  alt={`Submitted form for ${previewStation.station_name}`}
                  className="max-h-[70vh] w-auto max-w-full cursor-zoom-in object-contain"
                />
              </a>
            )}
            {previewState?.status === "loading" && (
              <div className="flex h-64 items-center justify-center text-xs text-muted-foreground">Loading form…</div>
            )}
            {previewState?.status === "error" && (
              <div className="flex h-64 items-center justify-center px-4 text-center text-xs text-muted-foreground">
                Couldn't load the form image.
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
