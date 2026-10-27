import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders the status text", () => {
    render(<StatusBadge status="Completed" />);
    expect(screen.getByTestId("status-badge")).toHaveTextContent("Completed");
  });
  it("uses distinct styling for failures", () => {
    const { rerender } = render(<StatusBadge status="Failed" />);
    expect(screen.getByTestId("status-badge").className).toContain("text-red-800");
    rerender(<StatusBadge status="Completed" />);
    expect(screen.getByTestId("status-badge").className).toContain("text-emerald-800");
  });
  it("animates only while a job is in flight", () => {
    const { container, rerender } = render(<StatusBadge status="Processing" />);
    expect(container.querySelector(".animate-pulse")).not.toBeNull();
    rerender(<StatusBadge status="Failed" />);
    expect(container.querySelector(".animate-pulse")).toBeNull();
  });
});
