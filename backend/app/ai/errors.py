class PipelineError(Exception):
    """A pipeline stage rejected its input or output. Carries the stage and a useful next action."""

    def __init__(self, stage: str, message: str, next_action: str | None = None):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.next_action = next_action

    def user_message(self) -> str:
        if self.next_action:
            return f"{self.message} {self.next_action}"
        return self.message
