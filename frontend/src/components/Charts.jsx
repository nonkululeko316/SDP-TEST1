import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fmtDate, fmtInt, fmtPct } from "../format";

const PALETTE = [
  "#4f46e5",
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#14b8a6",
  "#f97316",
  "#64748b",
  "#a855f7",
  "#22c55e",
  "#e11d48",
];

function NoData() {
  return (
    <div className="loading" style={{ padding: 28, textAlign: "center" }}>
      No data in this selection.
    </div>
  );
}

function Note({ children }) {
  return <p className="chart-note">{children}</p>;
}

function clip(value, max) {
  return value.length > max ? `...${value.slice(-(max - 3))}` : value;
}

/** Churn of the current directory's children; click a bar to drill in. */
export function ChildrenChurnChart({ children, onPick }) {
  const total = children.length;
  const data = [...children]
    .sort((a, b) => b.churn - a.churn)
    .slice(0, 12)
    .map((child) => ({ name: child.path, churn: child.churn, kind: child.kind, path: child.path }));

  if (!data.length || data.every((entry) => entry.churn === 0)) return <NoData />;

  return (
    <>
      <ResponsiveContainer width="100%" height={Math.max(150, data.length * 30 + 30)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 30, bottom: 4, left: 8 }}>
          <CartesianGrid horizontal={false} stroke="#eef0f6" />
          <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
          <YAxis
            type="category"
            dataKey="name"
            width={190}
            tick={{ fontSize: 11 }}
            tickFormatter={(value) => clip(value, 30)}
          />
          <Tooltip formatter={(value) => [fmtInt(value), "churn"]} />
          <Bar
            dataKey="churn"
            fill="#4f46e5"
            radius={[0, 4, 4, 0]}
            cursor={onPick ? "pointer" : "default"}
            onClick={(entry) => {
              const payload = entry?.payload ?? entry;
              if (onPick && payload && payload.path !== undefined) {
                onPick({ kind: payload.kind, path: payload.path });
              }
            }}
          />
        </BarChart>
      </ResponsiveContainer>
      <Note>
        Top {data.length} of {total} children by churn. Click a bar to open that child.
      </Note>
    </>
  );
}

/** Cumulative growth (and churn) over the loaded history of an object. */
export function GrowthChart({ items, total }) {
  if (!items || !items.length) return <NoData />;
  const ascending = [...items].sort((a, b) => a.committer_ts - b.committer_ts);
  let growth = 0;
  let churn = 0;
  const data = ascending.map((item) => {
    growth += item.growth;
    churn += item.churn;
    return { date: fmtDate(item.committer_ts), growth, churn };
  });

  return (
    <>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 6, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="#eef0f6" vertical={false} />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={42} />
          <YAxis tick={{ fontSize: 11 }} width={64} />
          <Tooltip formatter={(value, name) => [fmtInt(value), name]} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            type="monotone"
            dataKey="growth"
            name="Cumulative growth (delta)"
            stroke="#4f46e5"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="churn"
            name="Cumulative churn"
            stroke="#94a3b8"
            strokeWidth={1.5}
            strokeDasharray="4 3"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
      {total > items.length ? (
        <Note>
          Newest {fmtInt(items.length)} of {fmtInt(total)} commits touching this object - the
          chart shows that most recent window.
        </Note>
      ) : (
        <Note>{fmtInt(total)} commit{total === 1 ? "" : "s"} touched this object in the selected set.</Note>
      )}
    </>
  );
}

/** Ownership share (by churn) of the top authors on the current object. */
export function AuthorPie({ authors }) {
  if (!authors.length || authors.every((author) => author.churn === 0)) return <NoData />;

  const top = authors.slice(0, 8).map((author) => ({ name: author.email, value: author.churn }));
  const rest = authors.slice(8);
  const restChurn = rest.reduce((sum, author) => sum + author.churn, 0);
  if (restChurn > 0) {
    top.push({ name: `other (${rest.length} author${rest.length === 1 ? "" : "s"})`, value: restChurn });
  }
  const totalChurn = top.reduce((sum, entry) => sum + entry.value, 0) || 1;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart>
        <Pie
          data={top}
          dataKey="value"
          nameKey="name"
          innerRadius={55}
          outerRadius={92}
          paddingAngle={2}
        >
          {top.map((entry, index) => (
            <Cell key={entry.name} fill={PALETTE[index % PALETTE.length]} />
          ))}
        </Pie>
        <Tooltip
          formatter={(value) => [
            `${fmtInt(value)} churn (${((value / totalChurn) * 100).toFixed(1)}%)`,
            "",
          ]}
        />
        <Legend layout="vertical" align="right" verticalAlign="middle" wrapperStyle={{ fontSize: 12 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

/** Churn per author (top 10), annotated with ownership share. */
export function AuthorChurnChart({ authors }) {
  const data = [...authors]
    .sort((a, b) => b.churn - a.churn)
    .slice(0, 10)
    .map((author) => ({ name: author.email, churn: author.churn, ownership: author.ownership }));

  if (!data.length || data.every((entry) => entry.churn === 0)) return <NoData />;

  return (
    <>
      <ResponsiveContainer width="100%" height={Math.max(150, data.length * 30 + 30)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 30, bottom: 4, left: 8 }}>
          <CartesianGrid horizontal={false} stroke="#eef0f6" />
          <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
          <YAxis
            type="category"
            dataKey="name"
            width={190}
            tick={{ fontSize: 11 }}
            tickFormatter={(value) => clip(value, 30)}
          />
          <Tooltip
            formatter={(value, _name, item) => [
              `${fmtInt(value)} churn · ${fmtPct(item?.payload?.ownership ?? 0)} ownership`,
              "",
            ]}
          />
          <Bar dataKey="churn" fill="#0ea5e9" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <Note>Top {data.length} of {authors.length} authors by churn on this object.</Note>
    </>
  );
}
