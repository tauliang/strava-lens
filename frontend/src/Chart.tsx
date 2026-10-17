import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart, ScatterChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
echarts.use([
  LineChart,
  ScatterChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);
import type { PanelData } from "./api";
export function Chart({ panel }: { panel: PanelData }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    const series = panel.series ?? [];
    const labels = Array.from(
      new Set(
        series.flatMap((item) => item.data.map((point) => String(point.x))),
      ),
    ).sort((a, b) =>
      Number.isFinite(Number(a)) && Number.isFinite(Number(b))
        ? Number(a) - Number(b)
        : a.localeCompare(b),
    );
    chart.setOption({
      color: ["#d86e36", "#347661", "#b99948", "#6d79a1", "#b96878"],
      animationDuration: 350,
      tooltip: { trigger: "axis", confine: true },
      legend: { bottom: 0, type: "scroll" },
      grid: { top: 20, right: 20, bottom: 65, left: 65 },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: "#d8dfd9" } },
        axisLabel: { color: "#68746d" },
      },
      yAxis: {
        type: "value",
        name: panel.unit ?? "",
        axisLabel: { color: "#68746d" },
        splitLine: { lineStyle: { color: "#edf0ec" } },
      },
      series: series.map((item) => ({
        name: item.name,
        type: "line",
        smooth: false,
        showSymbol: item.data.length < 12,
        connectNulls: false,
        data: labels.map(
          (label) =>
            item.data.find((point) => String(point.x) === label)?.y ?? null,
        ),
        lineStyle: { width: 3 },
      })),
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [panel]);
  return (
    <div
      ref={ref}
      className="chart"
      role="img"
      aria-label={`${panel.title}. ${panel.unit ?? ""}. ${panel.series?.map((series) => series.name).join(", ")}`}
    />
  );
}
export function GeographyChart({ panel }: { panel: PanelData }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption({
      color: ["#347661"],
      tooltip: {
        trigger: "item",
        formatter: (item: { data: number[] }) =>
          `Latitude ${item.data[1]} / longitude ${item.data[0]} · ${item.data[2]} visits`,
      },
      grid: { left: 65, bottom: 60, right: 30, top: 20 },
      xAxis: { type: "value", name: "Longitude", scale: true },
      yAxis: { type: "value", name: "Latitude", scale: true },
      series: [
        {
          type: "scatter",
          data: panel.rows?.map((row) => [
            Number(row.longitude),
            Number(row.latitude),
            Number(row.visits),
          ]),
          symbolSize: (value: number[]) =>
            Math.min(40, 8 + Math.sqrt(value[2]) * 3),
        },
      ],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [panel]);
  return (
    <div
      ref={ref}
      className="chart"
      role="img"
      aria-label="Privacy-masked geographic activity visits. Longitude and latitude scatter plot."
    />
  );
}
