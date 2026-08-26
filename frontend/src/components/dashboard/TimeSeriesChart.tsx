import { LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip } from "recharts";
import type { Timeseries } from "@/types";

const COLORS = ["#1e6f57", "#2b3a55", "#9c6b24", "#6b4c7a"];

export function TimeSeriesChart({ data }: { data: Timeseries }) {
  if (data.series.length === 0) {
    return <p className="text-sm text-muted-foreground">No approved submissions yet — the chart fills in as forms are confirmed.</p>;
  }

  const rows = data.series.map((point) => ({
    time: new Date(point.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
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
