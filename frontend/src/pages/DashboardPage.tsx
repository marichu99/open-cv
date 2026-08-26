import { useEffect, useState } from "react";
import { usePositionsWithData, useTallySummary, useTallyTimeseries } from "@/lib/hooks";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CandidateBars } from "@/components/dashboard/CandidateBars";
import { TimeSeriesChart } from "@/components/dashboard/TimeSeriesChart";
import { formatPct, positionLabel } from "@/lib/utils";

export function DashboardPage() {
  const { data: positions } = usePositionsWithData();
  const [positionId, setPositionId] = useState<string | null>(null);
  const [scopeId, setScopeId] = useState<string | null>(null);

  const position = positions.find((p) => p.id === positionId) ?? null;
  const scopeRequired = position ? position.level !== "national" : false;

  // Default to the first position that already has real data once positions load.
  useEffect(() => {
    if (positionId || positions.length === 0) return;
    const withData = positions.find((p) => p.has_data);
    setPositionId((withData ?? positions[0]).id);
  }, [positions, positionId]);

  useEffect(() => {
    setScopeId(null);
  }, [positionId]);

  const { data: summary } = useTallySummary(positionId, scopeId, scopeRequired);
  const { data: timeseries } = useTallyTimeseries(positionId, scopeId, scopeRequired);

  const pct = summary.stations_total ? (summary.stations_reported / summary.stations_total) * 100 : 0;
  const hasAnyVotes = summary.candidates.some((c) => c.votes > 0);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <Badge variant="success">Live</Badge>
            <h1 className="font-display text-2xl font-semibold">
              {position ? positionLabel(position.name) : "Tally333"}
            </h1>
          </div>
          <p className="max-w-2xl text-sm text-muted-foreground">
            Unofficial parallel tally, computed from agent-submitted form photos as they're approved. Not an IEBC result.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Select value={positionId ?? ""} onValueChange={setPositionId}>
            <SelectTrigger className="w-64">
              <SelectValue placeholder="Select a race" />
            </SelectTrigger>
            <SelectContent>
              {positions.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {positionLabel(p.name)}
                  {!p.has_data ? " — no results yet" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {position && scopeRequired && (
            <Select value={scopeId ?? ""} onValueChange={setScopeId}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder={`Select a ${position.level}`} />
              </SelectTrigger>
              <SelectContent>
                {position.scopes.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </div>

      {position && scopeRequired && !scopeId ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Pick a {position.level} above to view this race.
          </CardContent>
        </Card>
      ) : !position ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">Loading…</CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardContent className="pt-5">
              <div className="mb-2 flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Stations reported</span>
                <span className="font-mono tabular-nums">
                  {summary.stations_reported} / {summary.stations_total} ({formatPct(pct)})
                </span>
              </div>
              <Progress value={pct} />
            </CardContent>
          </Card>

          {!hasAnyVotes ? (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                No results reported yet — this dashboard updates automatically as agents submit and coordinators approve forms.
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Totals</CardTitle>
                  <CardDescription>Sum of approved station-level submissions for this race</CardDescription>
                </CardHeader>
                <CardContent>
                  <CandidateBars rows={summary.candidates.map((c) => ({ label: c.full_name, votes: c.votes }))} />
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Tally over time</CardTitle>
                  <CardDescription>Cumulative total as submissions are approved</CardDescription>
                </CardHeader>
                <CardContent>
                  <TimeSeriesChart data={timeseries} />
                </CardContent>
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  );
}
