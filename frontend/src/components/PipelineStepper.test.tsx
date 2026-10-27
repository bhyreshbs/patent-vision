import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PipelineStepper } from "./PipelineStepper";

describe("PipelineStepper", () => {
  it("highlights the failed stage", () => {
    const { container } = render(<PipelineStepper status="Failed" failedStage="segmentation" />);
    const failed = container.querySelectorAll('[data-state="failed"]');
    expect(failed).toHaveLength(1);
    expect(failed[0]).toHaveTextContent("Segment");
    expect(container.querySelectorAll('[data-state="done"]')).toHaveLength(3);
  });
  it("shows all stages done on completion", () => {
    const { container } = render(<PipelineStepper status="Completed" failedStage={null} />);
    expect(container.querySelectorAll('[data-state="done"]')).toHaveLength(8);
    expect(screen.getByLabelText("Processing pipeline")).toBeInTheDocument();
  });
});
