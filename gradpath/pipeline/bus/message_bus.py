"""
Pipeline message bus — a simple in-process queue connecting agents.

Each agent reads from its input queue and writes to its output queue.
The orchestrator wires them together: Ingestion → Validation → Enrichment → Storage.
"""
import queue
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """Unit of work flowing between pipeline agents."""
    source_agent: str
    payload: Any                         # the data chunk (DataFrame or dict)
    metadata: dict = field(default_factory=dict)
    error: str | None = None             # set if this message carries a failure

    @property
    def is_error(self) -> bool:
        return self.error is not None


class Bus:
    """
    Named queues shared by all agents.
    Each stage puts to its output queue; the next stage gets from that queue.
    """

    def __init__(self):
        self._queues: dict[str, queue.Queue] = {}
        self._lock = threading.Lock()

    def channel(self, name: str) -> queue.Queue:
        with self._lock:
            if name not in self._queues:
                self._queues[name] = queue.Queue()
            return self._queues[name]

    def put(self, channel_name: str, message: Message):
        self.channel(channel_name).put(message)

    def get(self, channel_name: str, timeout: float = 30.0) -> Message:
        return self.channel(channel_name).get(timeout=timeout)

    def task_done(self, channel_name: str):
        self.channel(channel_name).task_done()
