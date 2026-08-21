from dataclasses import dataclass


@dataclass(frozen=True)
class AiPingResult:
    status: str
    message: str
    provider: str


def ping() -> AiPingResult:
    """Placeholder for a future open-model / inference backend."""
    return AiPingResult(
        status="ok",
        message="AI provider is not configured yet. Replace this stub when a model is chosen.",
        provider="placeholder",
    )
