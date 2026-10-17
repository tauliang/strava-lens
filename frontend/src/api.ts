export interface Metric {
  key?: string;
  id?: string;
  label: string;
  unit: string;
  available?: boolean;
}
export interface PanelDefinition {
  id: string;
  title: string;
  metrics: Metric[];
  modes?: string[];
  type?: string;
  default_metric?: string;
}
export interface Dashboard {
  id: string;
  title: string;
  description: string;
  panels: PanelDefinition[];
}
export interface Series {
  name: string;
  data: { x: string | number; y: number | null }[];
}
export interface PanelData {
  id: string;
  title: string;
  type?: string;
  value?: number | null;
  unit?: string;
  metric?: string;
  series?: Series[];
  rows?: Record<string, unknown>[];
  coverage?: unknown;
  message?: string;
}
export interface DashboardData {
  panels: PanelData[];
  [key: string]: unknown;
}
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = sessionStorage.getItem("lens-token");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (typeof init?.body === "string")
    headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail ?? body);
    } catch {
      /* HTTP status remains actionable. */
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}
export function metricKey(metric: Metric): string {
  return metric.key ?? metric.id ?? "";
}
export function tableValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number")
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
export function updateFilter(
  params: URLSearchParams,
  key: string,
  value: string,
): URLSearchParams {
  const next = new URLSearchParams(params);
  if (value) next.set(key, value);
  else next.delete(key);
  return next;
}
