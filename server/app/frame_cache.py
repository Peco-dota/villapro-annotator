"""Rolling per-service JPEG frame cache, so UDP single-image clients can backtrack
a few seconds around a detection event. Trimmed by age, count, and total size.

Storage is always dense (every processed frame goes in, tagged with whether it was
a "reportable" frame under the service's strict_output/state_changes_only settings)
so `latest()` always reflects the true current camera frame regardless of detection.
`reported_snapshot()` is the filtered view used for the `cache` field on outbound
payloads, so it stays in sync with whichever reporting mode the service uses."""
from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass


@dataclass
class CachedFrame:
    id: str
    ts: float
    jpeg: bytes
    boxes: list[dict]
    reported: bool  # True if this frame would also have triggered a normal report


class FrameCache:
    # ponytail: no lock around the deque — writes come from one UDP thread, reads
    # from FastAPI request threads; add a lock if get()/latest() ever race visibly
    # against _trim() (matches the existing unlocked _last_payload pattern in this codebase).
    def __init__(self, max_seconds: float, max_frames: int, max_bytes: int):
        self.max_seconds = max_seconds
        self.max_frames = max_frames
        self.max_bytes = max_bytes
        self._frames: deque[CachedFrame] = deque()
        self._total_bytes = 0

    def add(self, jpeg: bytes, boxes: list[dict], reported: bool = True) -> CachedFrame:
        frame = CachedFrame(id=uuid.uuid4().hex, ts=time.time(), jpeg=jpeg, boxes=boxes, reported=reported)
        self._frames.append(frame)
        self._total_bytes += len(jpeg)
        self._trim()
        return frame

    def _trim(self):
        cutoff = time.time() - self.max_seconds
        while self._frames and (
            self._frames[0].ts < cutoff
            or len(self._frames) > self.max_frames
            or self._total_bytes > self.max_bytes
        ):
            old = self._frames.popleft()
            self._total_bytes -= len(old.jpeg)

    def get(self, frame_id: str) -> CachedFrame | None:
        for f in self._frames:
            if f.id == frame_id:
                return f
        return None

    def latest(self) -> CachedFrame | None:
        """Most recent frame, always — regardless of whether it was 'reportable'."""
        return self._frames[-1] if self._frames else None

    def snapshot(self) -> list[CachedFrame]:
        """Every frame currently cached, oldest first (dense, unfiltered)."""
        return list(self._frames)

    def reported_snapshot(self) -> list[CachedFrame]:
        """Only the frames that qualified as reportable — synced to strict_output /
        state_changes_only, for attaching to the outbound `cache` field."""
        return [f for f in self._frames if f.reported]


if __name__ == "__main__":
    # ponytail: smallest runnable check for the eviction rules + reported filtering
    c = FrameCache(max_seconds=100, max_frames=3, max_bytes=1_000_000)
    for i in range(5):
        c.add(f"f{i}".encode(), [])
    assert len(c.snapshot()) == 3, "count eviction failed"
    assert c.snapshot()[0].jpeg == b"f2", "oldest frame not evicted first"
    assert c.latest().jpeg == b"f4"
    assert c.get(c.latest().id) is c.latest()
    assert c.get("missing") is None

    c2 = FrameCache(max_seconds=100, max_frames=100, max_bytes=8)
    c2.add(b"12345", [])
    c2.add(b"12345", [])
    assert len(c2.snapshot()) == 1, "size eviction failed"

    c3 = FrameCache(max_seconds=0.01, max_frames=100, max_bytes=1_000_000)
    c3.add(b"x", [])
    time.sleep(0.05)
    c3.add(b"y", [])
    assert len(c3.snapshot()) == 1, "time eviction failed"

    c4 = FrameCache(max_seconds=100, max_frames=100, max_bytes=1_000_000)
    c4.add(b"a", [], reported=False)
    c4.add(b"b", [], reported=True)
    c4.add(b"c", [], reported=False)
    assert len(c4.snapshot()) == 3, "dense storage should keep every frame"
    assert [f.jpeg for f in c4.reported_snapshot()] == [b"b"], "reported filter failed"
    assert c4.latest().jpeg == b"c", "latest() must ignore the reported flag"

    print("frame_cache self-check OK")
