"""Rights-module configuration errors. Tests run without network keys."""


class NotConfigured(RuntimeError):
    """Live fill cannot run: key missing, or the live client is not wired."""

    def __init__(self, module: str, env_var: str, reason: str | None = None) -> None:
        self.module = module
        self.env_var = env_var
        self.reason = reason or f"{env_var} unset"
        super().__init__(f"{module} not configured ({self.reason}); empty_stub only")
