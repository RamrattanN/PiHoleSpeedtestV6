from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class Measurement:
    recorded_at: str
    download_mbps: float
    upload_mbps: float
    latency_ms: float
    jitter_ms: float
    server_name: str
    server_id: str
    interface_name: str
    started_at: Optional[str] = None

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["completed_at"] = self.recorded_at
        return result
