"""Track API costs per interaction and session."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger("jarvis")


@dataclass
class CostTracker:
    """Accumulates API costs across interactions."""

    total_usd: float = 0.0
    interaction_count: int = 0
    _history: list[float] = field(default_factory=list)

    def record(self, cost_usd: float | None) -> None:
        """Record cost from a single interaction."""
        if cost_usd is None:
            return
        self.total_usd += cost_usd
        self.interaction_count += 1
        self._history.append(cost_usd)
        log.info(rf"Cost: \${cost_usd:.4f} (total: \${self.total_usd:.4f})")

    @property
    def average_cost(self) -> float:
        if not self._history:
            return 0.0
        return self.total_usd / len(self._history)

    def summary(self) -> str:
        return (
            f"{self.interaction_count} interactions, "
            rf"total: \${self.total_usd:.4f}, "
            rf"avg: \${self.average_cost:.4f}"
        )
