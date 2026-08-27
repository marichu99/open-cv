import { LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip } from "recharts";
import type { Timeseries, TimeseriesGranularity } from "@/types";

const COLORS = ["#1e6f57", "#2b3a55", "#9c6b24", "#6b4c7a"];

function formatBucket(iso: string, granularity: TimeseriesGranularity): string {
  const date = new Date(iso);
  if (granularity === "day") return date.toLocaleDateString([], { month: "short", day: "numeric" });
  if (granularity === "second") return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function TimeSeriesChart({ data }: { data: Timeseries }) {
  if (data.series.length === 0) {
    return <p className="text-sm text-muted-foreground">No approved submissions yet — the chart fills in as forms are confirmed.</p>;
  }

  const rows = data.series.map((point) => ({
    time: formatBucket(point.timestamp, data.granularity),
    ...Object.fromEntries(data.candidates.map((c) => [c.full_name, point.cumulative[c.candidate_id] ?? 0])),
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={rows} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="time" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
        />
        {data.candidates.map((c, i) => (
          <Line
            key={c.candidate_id}
            type="monotone"
            dataKey={c.full_name}
            stroke={COLORS[i % COLORS.length]}
            strokeWidth={2.5}
            dot={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
