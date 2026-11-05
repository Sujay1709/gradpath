"""
Base agent class — all pipeline agents inherit from this.

Each agent runs in its own thread, reads from an input channel,
does its work, and writes to an output channel.
"""
import logging
import threading
import traceback
from abc import ABC, abstractmethod

from pipeline.bus.message_bus import Bus, Message


class BaseAgent(ABC):
    """
    Abstract pipeline agent.

    Subclasses implement:
        process(message) → Message | None
            Transform/validate/enrich/store one message.
            Return None to drop the message (e.g. filtered out).
            Raise an exception to route the message to the dead-letter channel.
    """

    def __init__(self, name: str, bus: Bus, in_channel: str, out_channel: str):
        self.name = name
        self.bus = bus
        self.in_channel = in_channel
        self.out_channel = out_channel
        self.log = logging.getLogger(f"agent.{name}")
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.stats = {"processed": 0, "errors": 0, "dropped": 0}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self._thread.start()
        self.log.info("started")

    def stop(self):
        self._stop_event.set()

    def join(self, timeout: float = 60.0):
        if self._thread:
            self._thread.join(timeout=timeout)

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _run(self):
        while not self._stop_event.is_set():
            try:
                msg = self.bus.get(self.in_channel, timeout=1.0)
            except Exception:
                # Timeout — loop and check stop_event
                continue

            # Poison pill: None payload signals end-of-stream
            if msg.payload is None:
                self.log.info("received end-of-stream signal, shutting down")
                # Forward the sentinel to the next stage
                self.bus.put(self.out_channel, msg)
                self.bus.task_done(self.in_channel)
                break

            try:
                result = self.process(msg)
                if result is None:
                    self.stats["dropped"] += 1
                    self.log.debug("dropped message from %s", msg.source_agent)
                else:
                    self.bus.put(self.out_channel, result)
                    self.stats["processed"] += 1
            except Exception as exc:
                self.stats["errors"] += 1
                error_msg = Message(
                    source_agent=self.name,
                    payload=msg.payload,
                    metadata=msg.metadata,
                    error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                )
                self.bus.put("dead_letter", error_msg)
                self.log.error("error processing message: %s", exc)
            finally:
                self.bus.task_done(self.in_channel)

        self.log.info("stopped | stats=%s", self.stats)

    # ── To implement ──────────────────────────────────────────────────────────

    @abstractmethod
    def process(self, message: Message) -> Message | None:
        """Process one message. Return transformed message or None to drop."""
        raise NotImplementedError
