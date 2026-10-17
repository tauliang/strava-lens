// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
vi.mock("./Chart", () => ({ Chart: () => null, GeographyChart: () => null }));
import { Panel } from "./main";
afterEach(cleanup);
describe("parameterized panels", () => {
  it("selects metrics using a panel-specific URL key", async () => {
    const filter = vi.fn();
    render(
      <Panel
        definition={{
          id: "volume",
          title: "Volume",
          default_metric: "distance",
          metrics: [
            { key: "distance", label: "Distance", unit: "km" },
            { key: "hours", label: "Time", unit: "h" },
          ],
        }}
        params={new URLSearchParams()}
        setFilter={filter}
      />,
    );
    await userEvent.selectOptions(screen.getByRole("combobox"), "hours");
    expect(filter).toHaveBeenCalledWith("metric_volume", "hours");
    expect(
      screen.getByText("No eligible data for this selection."),
    ).toBeTruthy();
  });
  it("renders missing activity measurements explicitly and keeps detail links", () => {
    render(
      <Panel
        definition={{ id: "activities", title: "Activities", metrics: [] }}
        params={new URLSearchParams()}
        setFilter={vi.fn()}
        data={{
          id: "activities",
          title: "Activities",
          rows: [{ activity_id: "42", heart_rate: null, distance: 0 }],
        }}
      />,
    );
    expect(screen.getByRole("link", { name: "42" }).getAttribute("href")).toBe(
      "/activity_detail?activity_id=42",
    );
    expect(screen.getByText("—")).toBeTruthy();
    expect(screen.getByText("0")).toBeTruthy();
  });
});
