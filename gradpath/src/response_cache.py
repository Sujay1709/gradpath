"""
In-memory cache for GradPath's read-only GET endpoints.

The Scorecard and tax data only change when the data is refreshed, and the
API process is restarted after a refresh, so identical requests always get
identical answers. Grafana repeats the same requests on every page load and
filter change; serving them from memory keeps dashboards fast.

/plan/* is not cached: its answers depend on today's date.
"""
from collections import OrderedDict

CACHEABLE_PREFIXES = ("/metrics/", "/options/", "/schools/", "/states/", "/meta/sources")


class ResponseCache:
    def __init__(self, app, max_bytes: int = 192 * 1024 * 1024, max_entry_bytes: int = 24 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes
        self.max_entry_bytes = max_entry_bytes
        self.entries: OrderedDict[str, tuple[int, list, bytes]] = OrderedDict()
        self.size = 0
        self.hits = self.misses = 0

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or scope["method"] != "GET" or not path.startswith(CACHEABLE_PREFIXES):
            await self.app(scope, receive, send)
            return

        key = path + "?" + scope.get("query_string", b"").decode("latin-1")
        hit = self.entries.get(key)
        if hit is not None:
            self.entries.move_to_end(key)
            self.hits += 1
            status, headers, body = hit
            await send({"type": "http.response.start", "status": status,
                        "headers": headers + [(b"x-cache", b"HIT")]})
            await send({"type": "http.response.body", "body": body})
            return

        self.misses += 1
        start, chunks = {}, []

        async def capture(message):
            if message["type"] == "http.response.start":
                # copy: GZipMiddleware rewrites this header list in place after we pass it on
                start.update(message, headers=list(message.get("headers", [])))
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
            await send(message)

        await self.app(scope, receive, capture)
        body = b"".join(chunks)
        if start.get("status") == 200 and len(body) <= self.max_entry_bytes:
            self._store(key, (200, list(start.get("headers", [])), body))

    def _store(self, key, entry):
        old = self.entries.pop(key, None)
        if old:
            self.size -= len(old[2])
        self.entries[key] = entry
        self.size += len(entry[2])
        while self.size > self.max_bytes and self.entries:
            _, evicted = self.entries.popitem(last=False)
            self.size -= len(evicted[2])

    def stats(self) -> dict:
        return {"entries": len(self.entries), "megabytes": round(self.size / 1048576, 2),
                "hits": self.hits, "misses": self.misses}
