import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { ChevronRight, ExternalLink } from "lucide-react";
import { api, fetchSubmissionImageBlob } from "@/lib/api";
import { useCounties, useConstituencies, useWards, useStations, useUploadsLog } from "@/lib/hooks";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { positionLabel, cn } from "@/lib/utils";
import type { AgentWithAssignment, Candidate, ElectivePosition, FormSubmission, PositionLevel } from "@/types";

function AssignmentDialog({
  agent,
  onClose,
  onSaved,
}: {
  agent: AgentWithAssignment | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [countyId, setCountyId] = useState<string | null>(null);
  const [constituencyId, setConstituencyId] = useState<string | null>(null);
  const [wardId, setWardId] = useState<string | null>(null);
  const [stationId, setStationId] = useState<string | null>(null);
  const [positionIds, setPositionIds] = useState<string[]>([]);
  const [positions, setPositions] = useState<ElectivePosition[]>([]);
  const [busy, setBusy] = useState(false);

  function togglePosition(id: string) {
    setPositionIds((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]));
  }

  const counties = useCounties();
  const constituencies = useConstituencies(countyId);
  const wards = useWards(constituencyId);
  const stations = useStations(wardId);

  useEffect(() => {
    api.get<ElectivePosition[]>("/api/positions").then((res) => setPositions(res.data));
  }, []);

  useEffect(() => {
    if (!agent) return;
    setPositionIds(agent.position_ids);
    setStationId(agent.assigned_station_id ?? null);
    if (agent.assigned_station_id) {
      api.get(`/api/geography/stations/${agent.assigned_station_id}/ancestors`).then((res) => {
        const { ward, constituency, county } = res.data;
        if (county) setCountyId(county.id);
        if (constituency) setConstituencyId(constituency.id);
        if (ward) setWardId(ward.id);
      });
    } else {
      setCountyId(null);
      setConstituencyId(null);
      setWardId(null);
    }
  }, [agent]);

  async function save() {
    if (!agent) return;
    setBusy(true);
    try {
      await api.patch(`/api/agents/${agent.id}/assignment`, {
        assigned_station_id: stationId,
        position_ids: positionIds,
      });
      toast.success("Assignment updated");
      onSaved();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not update assignment");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={!!agent} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Assign {agent?.full_name}</DialogTitle>
          <DialogDescription>
            Set the ward/polling station this agent reports from and the elective position(s) they're tracking — one
            agent at a station commonly covers more than one race at once.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium uppercase text-muted-foreground">Elective positions</label>
            <div className="flex flex-col gap-1.5 rounded-md border border-border p-3">
              {positions.map((p) => (
                <label key={p.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className={cn("size-4 rounded border-border accent-primary")}
                    checked={positionIds.includes(p.id)}
                    onChange={() => togglePosition(p.id)}
                  />
                  {positionLabel(p.name)}
                </label>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium uppercase text-muted-foreground">County</label>
            <Select
              value={countyId ?? ""}
              onValueChange={(v) => {
                setCountyId(v);
                setConstituencyId(null);
                setWardId(null);
                setStationId(null);
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select county" />
              </SelectTrigger>
              <SelectContent>
                {counties.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium uppercase text-muted-foreground">Constituency</label>
            <Select
              value={constituencyId ?? ""}
              onValueChange={(v) => {
                setConstituencyId(v);
                setWardId(null);
                setStationId(null);
              }}
              disabled={!countyId}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select constituency" />
              </SelectTrigger>
              <SelectContent>
                {constituencies.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium uppercase text-muted-foreground">Ward</label>
            <Select
              value={wardId ?? ""}
              onValueChange={(v) => {
                setWardId(v);
                setStationId(null);
              }}
              disabled={!constituencyId}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select ward" />
              </SelectTrigger>
              <SelectContent>
                {wards.map((w) => (
                  <SelectItem key={w.id} value={w.id}>
                    {w.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium uppercase text-muted-foreground">Polling station</label>
            <Select value={stationId ?? ""} onValueChange={setStationId} disabled={!wardId}>
              <SelectTrigger>
                <SelectValue placeholder="Select station" />
              </SelectTrigger>
              <SelectContent>
                {stations.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Button onClick={save} disabled={busy}>
            {busy ? "Saving…" : "Save assignment"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function scopeIdFor(level: PositionLevel | undefined, countyId: string | null, constituencyId: string | null, wardId: string | null) {
  if (level === "county") return countyId;
  if (level === "constituency") return constituencyId;
  if (level === "ward") return wardId;
  return null;
}

function CandidatesCard() {
  const [positions, setPositions] = useState<ElectivePosition[]>([]);
  const [positionId, setPositionId] = useState<string | null>(null);
  const [countyId, setCountyId] = useState<string | null>(null);
  const [constituencyId, setConstituencyId] = useState<string | null>(null);
  const [wardId, setWardId] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [newName, setNewName] = useState("");
  const [newParty, setNewParty] = useState("");
  const [busy, setBusy] = useState(false);

  const position = positions.find((p) => p.id === positionId) ?? null;
  const counties = useCounties();
  const constituencies = useConstituencies(countyId);
  const wards = useWards(constituencyId);
  const scopeId = scopeIdFor(position?.level, countyId, constituencyId, wardId);
  const scopeReady = !position || position.level === "national" || !!scopeId;

  useEffect(() => {
    api.get<ElectivePosition[]>("/api/positions").then((res) => {
      setPositions(res.data);
      setPositionId((prev) => prev ?? res.data[0]?.id ?? null);
    });
  }, []);

  const load = useCallback(() => {
    if (!positionId || !scopeReady) {
      setCandidates([]);
      return;
    }
    const params: Record<string, string> = { position_id: positionId };
    if (position?.level === "county" && countyId) params.county_id = countyId;
    if (position?.level === "constituency" && constituencyId) params.constituency_id = constituencyId;
    if (position?.level === "ward" && wardId) params.ward_id = wardId;
    api.get<Candidate[]>("/api/candidates", { params }).then((res) => setCandidates(res.data));
  }, [positionId, position?.level, countyId, constituencyId, wardId, scopeReady]);

  useEffect(() => load(), [load]);

  async function addCandidate() {
    if (!positionId || !newName.trim()) return;
    setBusy(true);
    try {
      const payload: Record<string, string> = { position_id: positionId, full_name: newName.trim() };
      if (newParty.trim()) payload.party = newParty.trim();
      if (position?.level === "county" && countyId) payload.county_id = countyId;
      if (position?.level === "constituency" && constituencyId) payload.constituency_id = constituencyId;
      if (position?.level === "ward" && wardId) payload.ward_id = wardId;
      await api.post("/api/candidates", payload);
      setNewName("");
      setNewParty("");
      toast.success("Candidate added");
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not add candidate");
    } finally {
      setBusy(false);
    }
  }

  async function removeCandidate(id: string) {
    try {
      await api.delete(`/api/candidates/${id}`);
      toast.success("Candidate removed");
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not remove candidate");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Candidates</CardTitle>
        <CardDescription>
          Pre-seed the official name for each race so later form uploads — even a scan that reads the name slightly
          differently — count toward the right person instead of splitting into a duplicate.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          <Select
            value={positionId ?? ""}
            onValueChange={(v) => {
              setPositionId(v);
              setCountyId(null);
              setConstituencyId(null);
              setWardId(null);
            }}
          >
            <SelectTrigger className="w-56">
              <SelectValue placeholder="Select a race" />
            </SelectTrigger>
            <SelectContent>
              {positions.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {positionLabel(p.name)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {position && position.level !== "national" && (
            <Select
              value={countyId ?? ""}
              onValueChange={(v) => {
                setCountyId(v);
                setConstituencyId(null);
                setWardId(null);
              }}
            >
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Select county" />
              </SelectTrigger>
              <SelectContent>
                {counties.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          {position && (position.level === "constituency" || position.level === "ward") && (
            <Select
              value={constituencyId ?? ""}
              onValueChange={(v) => {
                setConstituencyId(v);
                setWardId(null);
              }}
              disabled={!countyId}
            >
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Select constituency" />
              </SelectTrigger>
              <SelectContent>
                {constituencies.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          {position && position.level === "ward" && (
            <Select value={wardId ?? ""} onValueChange={setWardId} disabled={!constituencyId}>
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Select ward" />
              </SelectTrigger>
              <SelectContent>
                {wards.map((w) => (
                  <SelectItem key={w.id} value={w.id}>
                    {w.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {!scopeReady ? (
          <p className="text-sm text-muted-foreground">Pick a {position?.level} above to manage this race's candidates.</p>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Party</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {candidates.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="font-medium">{c.full_name}</TableCell>
                    <TableCell className="text-muted-foreground">{c.party ?? "—"}</TableCell>
                    <TableCell>
                      <Button size="sm" variant="outline" onClick={() => removeCandidate(c.id)}>
                        Remove
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {candidates.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={3} className="py-6 text-center text-muted-foreground">
                      No candidates yet for this race.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>

            <div className="flex flex-wrap items-end gap-2">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium uppercase text-muted-foreground">Full name</label>
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. Odinga Raila Amolo"
                  className="w-56"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium uppercase text-muted-foreground">Party (optional)</label>
                <Input value={newParty} onChange={(e) => setNewParty(e.target.value)} className="w-40" />
              </div>
              <Button onClick={addCandidate} disabled={busy || !newName.trim()}>
                Add candidate
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

const UPLOAD_STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "draft", label: "Draft (not yet finalized)" },
  { value: "auto_approved", label: "Auto-approved" },
  { value: "manually_approved", label: "Manually approved" },
  { value: "rejected", label: "Rejected" },
  { value: "duplicate", label: "Duplicate" },
];

const UPLOAD_STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "neutral"> = {
  auto_approved: "success",
  manually_approved: "success",
  pending_review: "warning",
  rejected: "destructive",
  duplicate: "destructive",
  draft: "neutral",
};

interface LocationGroup {
  name: string;
  submissions: FormSubmission[];
  children: LocationGroup[];
}

function sortedEntries<T>(m: Map<string, T>) {
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

/** County → constituency → ward → polling station, built purely from the
 * submissions actually returned — so only locations with real uploads show
 * up, rather than every one of Kenya's ~24.6k stations. */
function groupByLocation(subs: FormSubmission[]): LocationGroup[] {
  const counties = new Map<string, Map<string, Map<string, Map<string, FormSubmission[]>>>>();

  for (const s of subs) {
    const county = s.county_name ?? "Unknown county";
    const constituency = s.constituency_name ?? "Unknown constituency";
    const ward = s.ward_name ?? "Unknown ward";
    const station = s.station_name ?? "Unknown station";

    const constituencies = counties.get(county) ?? new Map();
    counties.set(county, constituencies);
    const wards = constituencies.get(constituency) ?? new Map();
    constituencies.set(constituency, wards);
    const stations = wards.get(ward) ?? new Map();
    wards.set(ward, stations);
    const list = stations.get(station) ?? [];
    list.push(s);
    stations.set(station, list);
  }

  return sortedEntries(counties).map(([countyName, constituencies]) => ({
    name: countyName,
    submissions: [],
    children: sortedEntries(constituencies).map(([constituencyName, wards]) => ({
      name: constituencyName,
      submissions: [],
      children: sortedEntries(wards).map(([wardName, stations]) => ({
        name: wardName,
        submissions: [],
        children: sortedEntries(stations).map(([stationName, list]) => ({
          name: stationName,
          submissions: [...list].sort((a, b) => b.uploaded_at.localeCompare(a.uploaded_at)),
          children: [],
        })),
      })),
    })),
  }));
}

function countUploads(group: LocationGroup): number {
  return group.submissions.length + group.children.reduce((n, c) => n + countUploads(c), 0);
}

const LOCATION_LEVEL_LABELS = ["County", "Constituency", "Ward", "Polling station"];

/** Opens the submission's original photo in a new tab. */
async function viewSubmissionDocument(id: string) {
  try {
    const blob = await fetchSubmissionImageBlob(id);
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    // The new tab needs the blob URL to still resolve after it opens —
    // revoke it once that's had time to happen, not immediately.
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "Could not load the document");
  }
}

function LocationGroupNode({ group, depth }: { group: LocationGroup; depth: number }) {
  const total = countUploads(group);
  const levelLabel = LOCATION_LEVEL_LABELS[depth];

  return (
    <details className="group rounded-md border border-border" open={depth === 0}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 text-sm font-medium hover:bg-muted">
        <span className="flex items-center gap-2">
          <ChevronRight size={14} className="shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
          {group.name}
          {levelLabel && <Badge variant="neutral">{levelLabel}</Badge>}
        </span>
        <Badge variant="neutral">
          {total} upload{total === 1 ? "" : "s"}
        </Badge>
      </summary>
      <div className="flex flex-col gap-2 border-t border-border p-3 pl-6">
        {group.children.map((child) => (
          <LocationGroupNode key={child.name} group={child} depth={depth + 1} />
        ))}
        {group.children.length === 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Agent</TableHead>
                <TableHead>Form</TableHead>
                <TableHead>Uploaded at</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Document</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {group.submissions.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">{s.agent_name}</TableCell>
                  <TableCell>{s.form_type}</TableCell>
                  <TableCell className="text-muted-foreground">{new Date(s.uploaded_at).toLocaleString()}</TableCell>
                  <TableCell>
                    <Badge variant={UPLOAD_STATUS_VARIANT[s.status] ?? "neutral"}>{s.status.replace("_", " ")}</Badge>
                  </TableCell>
                  <TableCell>
                    <button
                      type="button"
                      onClick={() => viewSubmissionDocument(s.id)}
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                    >
                      <ExternalLink size={14} />
                      View
                    </button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </details>
  );
}

function UploadsCard() {
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const { data: submissions } = useUploadsLog(status);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return submissions;
    return submissions.filter((s) =>
      [s.agent_name, s.station_name, s.ward_name, s.constituency_name, s.county_name].some((field) =>
        field?.toLowerCase().includes(q)
      )
    );
  }, [submissions, search]);

  const groups = useMemo(() => groupByLocation(filtered), [filtered]);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Field uploads</CardTitle>
            <CardDescription>
              Every form photo a field agent has sent in, grouped by county, constituency, ward and polling station —
              expand a group to see exactly who uploaded it and when.
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search agent or location…"
              className="w-56"
            />
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {UPLOAD_STATUS_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {groups.length === 0 && <p className="py-8 text-center text-sm text-muted-foreground">No uploads yet.</p>}
        {groups.map((group) => (
          <LocationGroupNode key={group.name} group={group} depth={0} />
        ))}
      </CardContent>
    </Card>
  );
}

export function CampaignManagerPage() {
  const [agents, setAgents] = useState<AgentWithAssignment[]>([]);
  const [activeAgent, setActiveAgent] = useState<AgentWithAssignment | null>(null);

  const load = useCallback(() => {
    api.get<AgentWithAssignment[]>("/api/agents").then((res) => setAgents(res.data));
  }, []);

  useEffect(() => load(), [load]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl font-semibold">Campaign manager</h1>
        <p className="text-sm text-muted-foreground">
          Assign each field agent to a polling station and elective position — agents never pick this themselves.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Agents</CardTitle>
          <CardDescription>{agents.length} registered</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Agent</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Position</TableHead>
                <TableHead>Assignment</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {agents.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="font-medium">{a.full_name}</TableCell>
                  <TableCell className="text-muted-foreground">{a.phone_number}</TableCell>
                  <TableCell>
                    <Badge variant={a.phone_verified ? "success" : "neutral"}>
                      {a.phone_verified ? "Verified" : "Pending"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {a.position_names.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {a.position_names.map((name) => (
                          <Badge key={name} variant="neutral">
                            {positionLabel(name)}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <span className="text-muted-foreground">Unassigned</span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {a.assigned_station_name
                      ? `${a.county_name} / ${a.constituency_name} / ${a.ward_name} / ${a.assigned_station_name}`
                      : "Unassigned"}
                  </TableCell>
                  <TableCell>
                    <Button size="sm" variant="outline" onClick={() => setActiveAgent(a)}>
                      Assign
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {agents.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                    No agents yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <AssignmentDialog agent={activeAgent} onClose={() => setActiveAgent(null)} onSaved={load} />

      <UploadsCard />

      <CandidatesCard />
    </div>
  );
}
