import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Chart, GeographyChart } from "./Chart";
import {
  metricKey,
  request,
  tableValue,
  updateFilter,
  type Dashboard,
  type DashboardData,
  type PanelData,
  type PanelDefinition,
} from "./api";
import "./style.css";
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30000 } },
});
const icons: Record<string, string> = {
  overview: "◈",
  training: "↗",
  run_performance: "⌁",
  gear_sports: "◉",
  geography: "◎",
  activity_detail: "≋",
  social: "☷",
  vitals: "♡",
  data_health: "✓",
  setup: "⚙",
};
function useLocation() {
  const [location, setLocation] = useState(() => ({
    path: window.location.pathname,
    search: window.location.search,
  }));
  useEffect(() => {
    const listener = () =>
      setLocation({
        path: window.location.pathname,
        search: window.location.search,
      });
    window.addEventListener("popstate", listener);
    return () => window.removeEventListener("popstate", listener);
  }, []);
  function navigate(
    path: string,
    params = new URLSearchParams(location.search),
  ) {
    window.history.pushState(
      {},
      "",
      `${path}${params.size ? `?${params}` : ""}`,
    );
    setLocation({ path, search: params.toString() });
  }
  return { ...location, navigate };
}
function ErrorNotice({ error }: { error: unknown }) {
  return (
    <div className="notice error" role="alert">
      {error instanceof Error
        ? error.message
        : "Something went wrong. Please try again."}
    </div>
  );
}
function DataTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return null;
  const keys = Array.from(new Set(rows.flatMap(Object.keys)));
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {keys.map((key) => (
              <th key={key}>{key.replaceAll("_", " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={String(row.event_id ?? row.activity_id ?? index)}>
              {keys.map((key) => (
                <td key={key}>
                  {key === "activity_id" ? (
                    <a
                      href={`/activity_detail?activity_id=${encodeURIComponent(String(row[key]))}`}
                    >
                      {tableValue(row[key])}
                    </a>
                  ) : (
                    tableValue(row[key])
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function Panel({
  definition,
  data,
  params,
  setFilter,
}: {
  definition: PanelDefinition;
  data?: PanelData;
  params: URLSearchParams;
  setFilter: (key: string, value: string) => void;
}) {
  const hasSeries = data?.series?.some((series) =>
    series.data.some((point) => point.y !== null),
  );
  return (
    <article className="panel">
      <div className="panel-heading">
        <h2>{data?.title ?? definition.title}</h2>
        {definition.modes && definition.modes.length > 0 && (
          <label>
            <span className="sr-only">{definition.title} view</span>
            <select
              value={params.get(`mode_${definition.id}`) ?? definition.modes[0]}
              onChange={(event) =>
                setFilter(`mode_${definition.id}`, event.target.value)
              }
            >
              {definition.modes.map((mode) => (
                <option key={mode}>{mode}</option>
              ))}
            </select>
          </label>
        )}
        {definition.metrics.length > 0 && (
          <label className="metric-select">
            <span className="sr-only">{definition.title} metric</span>
            <select
              value={
                params.get(`metric_${definition.id}`) ??
                definition.default_metric ??
                metricKey(definition.metrics[0])
              }
              onChange={(event) =>
                setFilter(`metric_${definition.id}`, event.target.value)
              }
            >
              {definition.metrics.map((metric) => (
                <option key={metricKey(metric)} value={metricKey(metric)}>
                  {metric.label}
                  {metric.unit ? ` · ${metric.unit}` : ""}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {data?.type === "single" && (
        <div className="big-number">
          {tableValue(data.value)} <small>{data.unit}</small>
        </div>
      )}
      {hasSeries ? (
        <Chart panel={data!} />
      ) : (
        !data?.rows?.length && (
          <div className="empty">
            <span>◌</span>
            <p>{data?.message ?? "No eligible data for this selection."}</p>
            <small>
              Try another metric, sport or date range. Missing measurements
              remain unknown.
            </small>
          </div>
        )
      )}
      {data?.type === "map" && !!data.rows?.length && (
        <GeographyChart panel={data} />
      )}
      {!!data?.rows?.length && <DataTable rows={data.rows} />}
      {hasSeries && (
        <details>
          <summary>View chart data</summary>
          <DataTable
            rows={data!.series!.flatMap((series) =>
              series.data.map((point) => ({
                series: series.name,
                period: point.x,
                value: point.y,
                unit: data?.unit ?? "",
              })),
            )}
          />
        </details>
      )}
      {data?.coverage !== undefined && (
        <div className="coverage">Coverage · {tableValue(data.coverage)}</div>
      )}
    </article>
  );
}
function Imports() {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [notice, setNotice] = useState("");
  const imports = useQuery({
    queryKey: ["imports"],
    queryFn: () => request<unknown>("/imports"),
    refetchInterval: 3000,
  });
  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    setError(undefined);
    try {
      const form = new FormData();
      form.append("file", file);
      await request("/imports", { method: "POST", body: form });
      setNotice(
        "Export queued. You can continue browsing while it is processed.",
      );
      await client.invalidateQueries();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void client.invalidateQueries({ queryKey: ["dashboard"] });
    void client.invalidateQueries({ queryKey: ["snapshots"] });
  }, [imports.dataUpdatedAt, client]);
  const raw = imports.data;
  const rows = Array.isArray(raw)
    ? raw
    : raw && typeof raw === "object"
      ? ((raw as { imports?: unknown[] }).imports ?? [])
      : [];
  return (
    <>
      <section
        className="upload"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          if (!busy) void upload(event.dataTransfer.files[0]);
        }}
      >
        <div>
          <h2>Bring your training history</h2>
          <p>
            Drop in a Strava export ZIP. Overlapping exports retain snapshot
            history and unique activity totals.
          </p>
        </div>
        <label className="button">
          {busy ? "Uploading…" : "Choose export ZIP"}
          <input
            type="file"
            aria-label="Choose Strava export ZIP"
            accept=".zip,application/zip"
            disabled={busy}
            onChange={(event) => void upload(event.target.files?.[0])}
          />
        </label>
      </section>
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      {error ? <ErrorNotice error={error} /> : null}
      {imports.error && <ErrorNotice error={imports.error} />}
      <article className="panel">
        <h2>Import history</h2>
        {rows.length ? (
          <DataTable rows={rows as Record<string, unknown>[]} />
        ) : (
          <p className="muted">
            No imports yet. Upload your first export to populate the dashboards.
          </p>
        )}
      </article>
    </>
  );
}
function Settings() {
  const config = useQuery({
    queryKey: ["config"],
    queryFn: () => request<Record<string, unknown>>("/config"),
  });
  const client = useQueryClient();
  const [text, setText] = useState("");
  const [error, setError] = useState<unknown>();
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (config.data) setText(JSON.stringify(config.data, null, 2));
  }, [config.data]);
  async function save() {
    try {
      const body = JSON.parse(text);
      await request("/config", { method: "PUT", body: JSON.stringify(body) });
      setSaved(true);
      setError(undefined);
      await client.invalidateQueries();
    } catch (error) {
      setError(error);
      setSaved(false);
    }
  }
  return (
    <article className="panel">
      <h2>Import settings, zones and goals</h2>
      <p className="muted">
        Settings apply to future imports. Re-import an export after changing
        timezone, heart-rate boundaries or privacy rules. Keep exact GPS
        disabled unless you explicitly want to retain it.
      </p>
      {config.error && <ErrorNotice error={config.error} />}
      <label>
        Configuration JSON
        <textarea
          aria-label="Configuration JSON"
          rows={18}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setSaved(false);
          }}
          spellCheck={false}
        />
      </label>
      <button onClick={() => void save()}>Save configuration</button>
      {saved && <p role="status">Configuration saved.</p>}
      {error ? <ErrorNotice error={error} /> : null}
    </article>
  );
}
function App() {
  const { path, search, navigate } = useLocation();
  const params = new URLSearchParams(search);
  const id = path.split("/")[1] || "overview";
  const [token, setToken] = useState(
    sessionStorage.getItem("lens-token") ?? "",
  );
  const registry = useQuery({
    queryKey: ["dashboards"],
    queryFn: () => request<{ dashboards: Dashboard[] }>("/dashboards"),
  });
  const dashboards = registry.data?.dashboards ?? [];
  const dashboard = dashboards.find((item) => item.id === id);
  const [snapshotError, setSnapshotError] = useState<unknown>();
  const snapshots = useQuery({
    queryKey: ["snapshots"],
    queryFn: () => request<{ id: string; active: boolean }[]>("/snapshots"),
    refetchInterval: 10000,
  });
  const currentConfig = useQuery({
    queryKey: ["config"],
    queryFn: () => request<Record<string, unknown>>("/config"),
  });
  const snapshotId =
    params.get("snapshot_id") ??
    snapshots.data?.find((snapshot) => snapshot.active)?.id;
  const resolvedParams = new URLSearchParams(params);
  if (snapshotId) resolvedParams.set("snapshot_id", snapshotId);
  const query = useQuery({
    queryKey: [
      "dashboard",
      id,
      search,
      snapshotId,
      currentConfig.dataUpdatedAt,
    ],
    queryFn: () =>
      request<DashboardData>(`/dashboards/${id}?${resolvedParams}`),
    enabled: !!dashboard && snapshots.isSuccess,
  });
  const setFilter = (key: string, value: string) =>
    navigate(`/${id}`, updateFilter(params, key, value));
  return (
    <div className="app">
      <aside>
        <a
          className="brand"
          href="/overview"
          onClick={(event) => {
            event.preventDefault();
            navigate("/overview");
          }}
        >
          <span className="brand-icon">≋</span>strava<span>lens</span>
        </a>
        <div className="sidebar-caption">YOUR TRAINING, IN PERSPECTIVE</div>
        <nav aria-label="Dashboards">
          {dashboards.map((item) => (
            <a
              key={item.id}
              href={`/${item.id}`}
              aria-current={id === item.id ? "page" : undefined}
              onClick={(event) => {
                event.preventDefault();
                navigate(`/${item.id}`);
              }}
            >
              <span>{icons[item.id] ?? "◈"}</span>
              {item.title}
            </a>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="status-dot" /> Personal training workspace
          <br />
          <small>Export insights. Your data.</small>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <div className="eyebrow">
              TRAINING WORKSPACE <span>/</span> {dashboard?.title ?? "Loading"}
            </div>
            <h1>{dashboard?.title ?? "Strava Lens"}</h1>
            <p>
              {dashboard?.description ??
                "Explore the patterns behind your training."}
            </p>
          </div>
          <a
            className="button subtle"
            href="/setup"
            onClick={(event) => {
              event.preventDefault();
              navigate("/setup");
            }}
          >
            ↑ Import export
          </a>
        </header>
        {registry.error && (
          <>
            <ErrorNotice error={registry.error} />
            <section className="panel">
              <label>
                Access token
                <input
                  type="password"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  autoComplete="off"
                />
              </label>
              <button
                onClick={() => {
                  sessionStorage.setItem("lens-token", token);
                  void queryClient.invalidateQueries();
                }}
              >
                Connect
              </button>
            </section>
          </>
        )}
        {registry.isPending && <p role="status">Loading dashboard catalog…</p>}
        {dashboard && (
          <>
            <section className="filters" aria-label="Dashboard filters">
              <datalist id="sports">
                {(
                  (query.data?.dimensions as { sports?: string[] })?.sports ??
                  []
                ).map((sport) => (
                  <option key={sport}>{sport}</option>
                ))}
              </datalist>
              <datalist id="gears">
                {(
                  (query.data?.dimensions as { gears?: string[] })?.gears ?? []
                ).map((gear) => (
                  <option key={gear}>{gear}</option>
                ))}
              </datalist>
              <label>
                Sport
                <input
                  list="sports"
                  value={params.get("sport") ?? ""}
                  placeholder="All sports"
                  onChange={(event) => setFilter("sport", event.target.value)}
                />
              </label>
              <label>
                From
                <input
                  type="date"
                  value={params.get("start") ?? ""}
                  onChange={(event) => setFilter("start", event.target.value)}
                />
              </label>
              <label>
                To
                <input
                  type="date"
                  value={params.get("end") ?? ""}
                  onChange={(event) => setFilter("end", event.target.value)}
                />
              </label>
              {[
                [
                  "grain",
                  "Period",
                  [
                    ["week", "Weekly"],
                    ["month", "Monthly"],
                    ["year", "Yearly"],
                  ],
                ],
                [
                  "units",
                  "Units",
                  [
                    ["metric", "Metric"],
                    ["imperial", "Imperial"],
                  ],
                ],
                [
                  "quality",
                  "Quality",
                  [
                    ["reported", "Reported"],
                    ["validated", "Validated"],
                    ["flagged", "Flagged"],
                  ],
                ],
                [
                  "history",
                  "Comparison",
                  [
                    ["all", "Full periods"],
                    ["ytd", "Comparable YTD"],
                  ],
                ],
                [
                  "split",
                  "Group by",
                  [
                    ["none", "Combined"],
                    ["sport", "Sport"],
                    ["gear", "Gear"],
                  ],
                ],
                [
                  "cadence",
                  "Running cadence",
                  [
                    ["unconfirmed", "Unconfirmed"],
                    ["steps", "Steps/min"],
                    ["strides", "Strides/min"],
                  ],
                ],
              ].map(([key, label, options]) => (
                <label key={String(key)}>
                  {String(label)}
                  <select
                    value={
                      params.get(String(key)) ?? (options as string[][])[0][0]
                    }
                    onChange={(event) =>
                      setFilter(String(key), event.target.value)
                    }
                  >
                    {(options as string[][]).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
              <label>
                Gear
                <input
                  list="gears"
                  value={params.get("gear") ?? ""}
                  placeholder="All gear"
                  onChange={(event) => setFilter("gear", event.target.value)}
                />
              </label>
              {id === "activity_detail" && (
                <label>
                  Activity ID
                  <input
                    value={params.get("activity_id") ?? ""}
                    onChange={(event) =>
                      setFilter("activity_id", event.target.value)
                    }
                  />
                </label>
              )}
              <button
                className="reset"
                onClick={() => navigate(`/${id}`, new URLSearchParams())}
              >
                Reset
              </button>
            </section>
            <div className="context">
              <span className="status-dot" />
              {query.isFetching
                ? "Updating insights…"
                : "Export-based insights"}
              <span>Missing values are never treated as zero</span>
              <details>
                <summary>Snapshot history</summary>
                <div className="snapshot-popover">
                  {(Array.isArray(snapshots.data) ? snapshots.data : []).map(
                    (snapshot: {
                      id: string;
                      active?: boolean;
                      status?: string;
                    }) => (
                      <div key={snapshot.id}>
                        <code>{snapshot.id.slice(0, 16)}</code> ·{" "}
                        {snapshot.status}{" "}
                        <button
                          onClick={() => setFilter("snapshot_id", snapshot.id)}
                        >
                          View
                        </button>
                        {snapshot.active ? (
                          "· Active"
                        ) : (
                          <button
                            onClick={() => {
                              void request(
                                `/snapshots/${encodeURIComponent(snapshot.id)}/activate`,
                                { method: "POST" },
                              )
                                .then(() => queryClient.invalidateQueries())
                                .catch(setSnapshotError);
                            }}
                          >
                            Activate
                          </button>
                        )}
                      </div>
                    ),
                  )}
                  {snapshotError ? <ErrorNotice error={snapshotError} /> : null}
                </div>
              </details>
            </div>
            {id === "setup" && (
              <>
                <Imports />
                <Settings />
              </>
            )}
            {query.error && <ErrorNotice error={query.error} />}
            <section className="panel-grid" aria-busy={query.isFetching}>
              {dashboard.panels.map((definition) => (
                <Panel
                  key={definition.id}
                  definition={definition}
                  data={query.data?.panels.find(
                    (panel) => panel.id === definition.id,
                  )}
                  params={params}
                  setFilter={setFilter}
                />
              ))}
            </section>
          </>
        )}
        <footer>
          Strava Lens <span>Independent training analytics · v0.1.0</span>
        </footer>
      </main>
    </div>
  );
}
const rootElement = document.getElementById("root");
if (rootElement)
  createRoot(rootElement).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </React.StrictMode>,
  );
