from __future__ import annotations

from dataclasses import asdict, dataclass


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

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
