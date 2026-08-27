import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import {
  usePositionsWithData,
  useTallySummary,
  useTallyTimeseries,
  useVotesByStation,
  useVotesByGroup,
} from "@/lib/hooks";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CandidateBars } from "@/components/dashboard/CandidateBars";
import { TimeSeriesChart } from "@/components/dashboard/TimeSeriesChart";
import { StationBreakdown } from "@/components/dashboard/StationBreakdown";
import { RegionalBreakdown } from "@/components/dashboard/RegionalBreakdown";
import { formatPct, positionLabel, cn } from "@/lib/utils";
import type { TimeseriesGranularity, GroupingLevel } from "@/types";

const GRANULARITY_OPTIONS: { value: TimeseriesGranularity | "auto"; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "second", label: "Sec" },
  { value: "minute", label: "Min" },
  { value: "hour", label: "Hour" },
  { value: "day", label: "Day" },
];

const LEVEL_LABEL: Record<GroupingLevel, string> = {
  county: "County",
  constituency: "Constituency",
  ward: "Ward",
  station: "Station",
};

export function DashboardPage() {
  const { data: positions } = usePositionsWithData();
  const [positionId, setPositionId] = useState<string | null>(null);
  const [scopeId, setScopeId] = useState<string | null>(null);
  const [granularity, setGranularity] = useState<TimeseriesGranularity | "auto">("auto");
  const [groupLevel, setGroupLevel] = useState<GroupingLevel>("station");

  const position = positions.find((p) => p.id === positionId) ?? null;
  const scopeRequired = position ? position.level !== "national" : false;
  const groupingLevels = position?.grouping_levels ?? ["station"];

  // Default to the first position that already has real data once positions load.
  useEffect(() => {
    if (positionId || positions.length === 0) return;
    const withData = positions.find((p) => p.has_data);
    setPositionId((withData ?? positions[0]).id);
  }, [positions, positionId]);

  useEffect(() => {
    setScopeId(null);
    setGroupLevel("station");
  }, [positionId]);

  const { data: summary } = useTallySummary(positionId, scopeId, scopeRequired);
  const { data: timeseries } = useTallyTimeseries(positionId, scopeId, scopeRequired, granularity);
  const { data: byStation } = useVotesByStation(groupLevel === "station" ? positionId : null, scopeId, scopeRequired);
  const { data: byGroup } = useVotesByGroup(groupLevel === "station" ? null : positionId, scopeId, scopeRequired, groupLevel);

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
          <CardContent className="flex flex-col items-center gap-3 py-14 text-sm text-muted-foreground">
            <Loader2 className="size-6 animate-spin text-primary" />
            Loading live results…
          </CardContent>
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
                No results reported yet — this dashboard updates automatically the moment agents submit forms.
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Totals</CardTitle>
                  <CardDescription>Sum of station-level submissions for this race, as agents submit them</CardDescription>
                </CardHeader>
                <CardContent>
                  <CandidateBars rows={summary.candidates.map((c) => ({ label: c.full_name, votes: c.votes }))} />
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
                  <div>
                    <CardTitle>Tally over time</CardTitle>
                    <CardDescription>
                      Cumulative total as submissions are approved
                      {granularity === "auto" && ` — bucketed by ${timeseries.granularity} to fit the reporting window`}
                    </CardDescription>
                  </div>
                  <div className="flex gap-1 rounded-md border border-border bg-muted p-0.5">
                    {GRANULARITY_OPTIONS.map((opt) => (
                      <Button
                        key={opt.value}
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => setGranularity(opt.value)}
                        className={cn("h-6 px-2 text-xs", granularity === opt.value ? "bg-card shadow-sm" : "text-muted-foreground")}
                      >
                        {opt.label}
                      </Button>
                    ))}
                  </div>
                </CardHeader>
                <CardContent>
                  <TimeSeriesChart data={timeseries} />
                </CardContent>
              </Card>
            </div>
          )}

          {!hasAnyVotes ? null : (
            <Card>
              <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>By {LEVEL_LABEL[groupLevel].toLowerCase()}</CardTitle>
                  <CardDescription>
                    {groupLevel === "station"
                      ? "Live feed of counted submissions, most recently reported station first"
                      : `Every reporting station's votes summed by ${LEVEL_LABEL[groupLevel].toLowerCase()}`}
                  </CardDescription>
                </div>
                {groupingLevels.length > 1 && (
                  <div className="flex gap-1 rounded-md border border-border bg-muted p-0.5">
                    {groupingLevels.map((level) => (
                      <Button
                        key={level}
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => setGroupLevel(level)}
                        className={cn("h-6 px-2 text-xs", groupLevel === level ? "bg-card shadow-sm" : "text-muted-foreground")}
                      >
                        {LEVEL_LABEL[level]}
                      </Button>
                    ))}
                  </div>
                )}
              </CardHeader>
              <CardContent>
                {groupLevel === "station" ? <StationBreakdown data={byStation} /> : <RegionalBreakdown data={byGroup} />}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
