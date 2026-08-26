import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useCounties, useConstituencies, useWards, useStations } from "@/lib/hooks";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { positionLabel, cn } from "@/lib/utils";
import type { AgentWithAssignment, ElectivePosition } from "@/types";

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
    </div>
  );
}
