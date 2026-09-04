import { useEffect, useState, useCallback } from "react";
import { api } from "./api";
import { getSocket } from "./socket";
import type {
  County,
  Constituency,
  Ward,
  PollingStation,
  PositionWithData,
  TallySummary,
  Timeseries,
  TimeseriesGranularity,
  VotesByStation,
  VotesByGroup,
  GroupingLevel,
  FormSubmission,
} from "@/types";

// Lazy, cascading geography fetches — at national scale (47 counties, 290
// constituencies, ~1,450 wards, ~24.6k polling stations) fetching the whole
// tree up front isn't viable, so each level loads only once its parent is picked.

export function useCounties() {
  const [counties, setCounties] = useState<County[]>([]);
  useEffect(() => {
    api.get<County[]>("/api/geography/counties").then((res) => setCounties(res.data));
  }, []);
  return counties;
}

export function useConstituencies(countyId: string | null) {
  const [constituencies, setConstituencies] = useState<Constituency[]>([]);
  useEffect(() => {
    if (!countyId) {
      setConstituencies([]);
      return;
    }
    api.get<Constituency[]>("/api/geography/constituencies", { params: { county_id: countyId } }).then((res) => setConstituencies(res.data));
  }, [countyId]);
  return constituencies;
}

export function useWards(constituencyId: string | null) {
  const [wards, setWards] = useState<Ward[]>([]);
  useEffect(() => {
    if (!constituencyId) {
      setWards([]);
      return;
    }
    api.get<Ward[]>("/api/geography/wards", { params: { constituency_id: constituencyId } }).then((res) => setWards(res.data));
  }, [constituencyId]);
  return wards;
}

export function useStations(wardId: string | null) {
  const [stations, setStations] = useState<PollingStation[]>([]);
  useEffect(() => {
    if (!wardId) {
      setStations([]);
      return;
    }
    api.get<PollingStation[]>("/api/geography/stations", { params: { ward_id: wardId } }).then((res) => setStations(res.data));
  }, [wardId]);
  return stations;
}

/** Refetches whenever the backend emits `tally_updated`, plus a light poll as a fallback. */
function useLiveResource<T>(path: string | null, initial: T, pollMs = 20000) {
  const [data, setData] = useState<T>(initial);

  const refresh = useCallback(() => {
    if (!path) return;
    api.get<T>(path).then((res) => setData(res.data)).catch(() => {});
  }, [path]);

  useEffect(() => {
    if (!path) return;
    refresh();
    const socket = getSocket();
    socket.on("tally_updated", refresh);
    const interval = setInterval(refresh, pollMs);
    return () => {
      socket.off("tally_updated", refresh);
      clearInterval(interval);
    };
  }, [refresh, pollMs, path]);

  return { data, refresh };
}

/** Positions with at least one real submission so far, plus every position's
 * pickable scope list — drives the dashboard's position/scope selector. */
export function usePositionsWithData() {
  return useLiveResource<PositionWithData[]>("/api/tally/positions", []);
}

function tallyPath(base: string, positionId: string | null, scopeId: string | null | undefined, scopeRequired: boolean) {
  if (!positionId || (scopeRequired && !scopeId)) return null;
  return `${base}?position_id=${positionId}${scopeId ? `&scope_id=${scopeId}` : ""}`;
}

export function useTallySummary(positionId: string | null, scopeId: string | null | undefined, scopeRequired: boolean) {
  return useLiveResource<TallySummary>(
    tallyPath("/api/tally/summary", positionId, scopeId, scopeRequired),
    { candidates: [], stations_reported: 0, stations_total: 0 },
  );
}

export function useTallyTimeseries(
  positionId: string | null,
  scopeId: string | null | undefined,
  scopeRequired: boolean,
  granularity: TimeseriesGranularity | "auto" = "auto",
) {
  const base = tallyPath("/api/tally/timeseries", positionId, scopeId, scopeRequired);
  const path = base && granularity !== "auto" ? `${base}&granularity=${granularity}` : base;
  return useLiveResource<Timeseries>(path, { candidates: [], series: [], granularity: "hour" });
}

export function useVotesByStation(positionId: string | null, scopeId: string | null | undefined, scopeRequired: boolean) {
  return useLiveResource<VotesByStation>(
    tallyPath("/api/tally/by_station", positionId, scopeId, scopeRequired),
    { candidates: [], stations: [] },
  );
}

export function useVotesByGroup(
  positionId: string | null,
  scopeId: string | null | undefined,
  scopeRequired: boolean,
  level: GroupingLevel,
) {
  const base = tallyPath("/api/tally/by_group", positionId, scopeId, scopeRequired);
  const path = base ? `${base}&level=${level}` : null;
  return useLiveResource<VotesByGroup>(path, { candidates: [], level, groups: [] });
}

/** The coordinator/admin review queue — refetches on `tally_updated`
 * (emitted both when a new submission is finalized and when another
 * reviewer resolves one), so a newly-flagged submission or someone else's
 * review action shows up without a manual reload. */
export function useSubmissionsFeed(params: Record<string, string>) {
  const query = new URLSearchParams(params).toString();
  const path = `/api/submissions${query ? `?${query}` : ""}`;
  return useLiveResource<FormSubmission[]>(path, []);
}
