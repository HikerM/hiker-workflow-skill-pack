from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:password|passwd|token|api[_-]?key|secret)\s*[=:]\s*)[^\s,;]+"),
)


@dataclass(frozen=True)
class CaptureBudget:
    max_spool_bytes: int = 8 * 1024 * 1024
    max_inline_chars: int = 4_000
    max_lines: int = 100_000
    max_single_line_bytes: int = 256 * 1024


@dataclass
class CaptureReceipt:
    observed_bytes: int = 0
    stored_bytes: int = 0
    discarded_bytes: int = 0
    lines: int = 0
    truncated: bool = False
    line_limit_reached: bool = False


def redact(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(r"\1[REDACTED]", text)
    return text


def pump_bounded(source: BinaryIO, destination: BinaryIO, budget: CaptureBudget, receipt: CaptureReceipt) -> None:
    # Keep only a bounded prefix of the current line. A command can emit one
    # newline-free multi-gigabyte value; buffering until a newline would defeat
    # the result fuse even when the final spool is capped.
    pending = bytearray()
    observed_line_bytes = 0

    def append(fragment: bytes) -> None:
        nonlocal observed_line_bytes
        observed_line_bytes += len(fragment)
        remaining = budget.max_single_line_bytes - len(pending)
        if remaining > 0:
            pending.extend(fragment[:remaining])

    def flush() -> None:
        nonlocal observed_line_bytes
        if observed_line_bytes == 0:
            return
        _store_raw_line(bytes(pending), observed_line_bytes, destination, budget, receipt)
        pending.clear()
        observed_line_bytes = 0

    while True:
        chunk = source.read(64 * 1024)
        if not chunk:
            break
        receipt.observed_bytes += len(chunk)
        offset = 0
        while True:
            newline = chunk.find(b"\n", offset)
            if newline < 0:
                append(chunk[offset:])
                break
            append(chunk[offset:newline + 1])
            flush()
            offset = newline + 1
    flush()


def _store_raw_line(raw_prefix: bytes, observed_line_bytes: int, destination: BinaryIO, budget: CaptureBudget, receipt: CaptureReceipt) -> None:
    receipt.lines += 1
    if receipt.lines > budget.max_lines:
        receipt.truncated = True
        receipt.line_limit_reached = True
        receipt.discarded_bytes += observed_line_bytes
        return
    raw = redact(raw_prefix.decode("utf-8", errors="replace")).encode("utf-8", errors="replace")
    if observed_line_bytes > len(raw_prefix):
        receipt.discarded_bytes += observed_line_bytes - len(raw_prefix)
        marker = b"\n[LINE_TRUNCATED]\n"
        raw = raw[: max(0, budget.max_single_line_bytes - len(marker))] + marker
        receipt.truncated = True
    remaining = budget.max_spool_bytes - receipt.stored_bytes
    if remaining <= 0:
        receipt.discarded_bytes += len(raw)
        receipt.truncated = True
        return
    stored = raw[:remaining]
    destination.write(stored)
    receipt.stored_bytes += len(stored)
    if len(stored) < len(raw):
        receipt.discarded_bytes += len(raw) - len(stored)
        receipt.truncated = True


def start_capture_thread(source: BinaryIO, destination: BinaryIO, budget: CaptureBudget, receipt: CaptureReceipt) -> threading.Thread:
    thread = threading.Thread(target=pump_bounded, args=(source, destination, budget, receipt), daemon=True)
    thread.start()
    return thread


def read_page(path: Path, offset: int = 0, max_bytes: int = 64 * 1024) -> dict[str, object]:
    offset = max(0, offset)
    max_bytes = min(max(1, max_bytes), 256 * 1024)
    size = path.stat().st_size
    with path.open("rb") as stream:
        stream.seek(min(offset, size))
        raw = stream.read(max_bytes)
    return {
        "offset": offset,
        "returned_bytes": len(raw),
        "next_offset": offset + len(raw) if offset + len(raw) < size else None,
        "total_bytes": size,
        "content": raw.decode("utf-8", errors="replace"),
    }
