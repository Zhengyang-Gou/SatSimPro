"""Redis query worker moved out of the GUI thread."""

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.redis_latency import MultiRedisLatencyProvider, RedisLatencyProvider
from .link_state import LinkRecord


class RedisQueryWorker(QObject):
    """Run Redis and SSH tunnel I/O away from the GUI thread."""

    result_ready = Signal(int, int, object)
    error = Signal(int, int, str)

    def __init__(self, redis_config: Dict[str, Any]):
        super().__init__()
        self.redis_config = redis_config
        self.provider: Optional[Any] = None

    def _provider(self):
        if self.provider is None:
            if self.redis_config.get("backends"):
                self.provider = MultiRedisLatencyProvider(**self.redis_config)
            else:
                self.provider = RedisLatencyProvider(**self.redis_config)
        return self.provider

    @Slot(int, int, object, object)
    def query(self, query_id: int, time_slice: int, active_links: List[LinkRecord], satellites: List[Any]) -> None:
        try:
            metrics = self._provider().get_latest_link_metrics_many(active_links, satellites, time_slice)
            self.result_ready.emit(query_id, time_slice, metrics)
        except Exception as exc:  # Redis/SSH errors should never block or crash the UI.
            self.error.emit(query_id, time_slice, str(exc))

    @Slot()
    def close(self) -> None:
        if self.provider is not None:
            self.provider.close()
            self.provider = None
        QThread.currentThread().quit()
