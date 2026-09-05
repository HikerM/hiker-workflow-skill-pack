from __future__ import annotations

import os
import io
import stat
import subprocess
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterator

from result_fuse import CaptureBudget, CaptureReceipt, start_capture_thread


RESERVED_STATE_DIRECTORY = ".ai"
DEFAULT_IGNORED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", ".idea", ".vs", ".venv", "venv",
    "node_modules", "vendor", "library", "temp", "tmp", "obj", "bin",
    "dist", "build", "coverage", "deriveddata", "pods", "__pycache__",
})


@dataclass(frozen=True)
class TraversalBudget:
    max_depth: int = 6
    max_directories: int = 2_048
    max_entries: int = 50_000
    max_files: int = 20_000
    max_observed_bytes: int = 2 * 1024 * 1024 * 1024
    max_elapsed_ms: int = 5_000
    max_entries_per_directory: int = 4_096


@dataclass
class TraversalMetrics:
    directories: int = 0
    entries: int = 0
    files: int = 0
    observed_bytes: int = 0
    elapsed_ms: float = 0.0
    reserved_state_skipped: int = 0
    reparse_points_skipped: int = 0


class TraversalLimitReached(RuntimeError):
    def __init__(self, limit: str, metrics: TraversalMetrics):
        self.limit = limit
        self.metrics = metrics
        super().__init__(f"TRAVERSAL_LIMIT_REACHED:{limit}")

    def receipt(self) -> dict[str, object]:
        return {
            "ok": False,
            "status": "TRAVERSAL_LIMIT_REACHED",
            "limit": self.limit,
            "metrics": asdict(self.metrics),
        }


def is_reparse_or_symlink(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def is_reserved_source_path(root: Path, path: Path) -> bool:
    """Return true for .ai or anything that cannot be proven to stay in source root."""
    caller_root = Path(os.path.abspath(root))
    root = caller_root.resolve()
    candidate = path if path.is_absolute() else caller_root / path
    absolute = Path(os.path.abspath(candidate))
    try:
        lexical_relative = absolute.relative_to(caller_root)
    except ValueError:
        lexical_relative = None
    try:
        relative = absolute.resolve(strict=False).relative_to(root)
    except (OSError, ValueError):
        return True
    if any(part.casefold() == RESERVED_STATE_DIRECTORY for part in relative.parts):
        return True
    if lexical_relative is not None and any(
        part.casefold() == RESERVED_STATE_DIRECTORY for part in lexical_relative.parts
    ):
        return True
    current = caller_root
    for part in (lexical_relative or relative).parts:
        current /= part
        if current.exists() and is_reparse_or_symlink(current):
            return True
    return False


def walk_source_files(
    root: Path,
    budget: TraversalBudget | None = None,
    ignored_directories: set[str] | frozenset[str] = DEFAULT_IGNORED_DIRECTORIES,
    include: Callable[[Path], bool] | None = None,
) -> tuple[list[Path], TraversalMetrics]:
    # Traverse the canonical target, but return paths under the caller's lexical
    # root. Windows may expose a temp directory through an 8.3 alias while
    # scandir returns the long name; callers must still be able to use
    # path.relative_to(their_original_root).
    caller_root = Path(os.path.abspath(root))
    root = caller_root.resolve()
    limits = budget or TraversalBudget()
    ignored = {name.casefold() for name in ignored_directories}
    ignored.add(RESERVED_STATE_DIRECTORY)
    metrics = TraversalMetrics()
    started = time.monotonic()
    queue: deque[tuple[Path, int]] = deque([(root, 0)])
    files: list[Path] = []

    def check() -> None:
        metrics.elapsed_ms = round((time.monotonic() - started) * 1000, 3)
        for name, value, maximum in (
            ("directories", metrics.directories, limits.max_directories),
            ("entries", metrics.entries, limits.max_entries),
            ("files", metrics.files, limits.max_files),
            ("observed_bytes", metrics.observed_bytes, limits.max_observed_bytes),
            ("elapsed_ms", metrics.elapsed_ms, limits.max_elapsed_ms),
        ):
            if value > maximum:
                raise TraversalLimitReached(name, metrics)

    while queue:
        current, depth = queue.popleft()
        if depth > limits.max_depth:
            continue
        if current != root and is_reparse_or_symlink(current):
            metrics.reparse_points_skipped += 1
            continue
        metrics.directories += 1
        check()
        try:
            entries = sorted(os.scandir(current), key=lambda item: item.name.casefold())
        except OSError:
            continue
        if len(entries) > limits.max_entries_per_directory:
            metrics.entries += len(entries)
            check()
            raise TraversalLimitReached("entries_per_directory", metrics)
        for entry in entries:
            metrics.entries += 1
            check()
            path = Path(entry.path)
            name = entry.name.casefold()
            if name == RESERVED_STATE_DIRECTORY:
                metrics.reserved_state_skipped += 1
                continue
            try:
                if entry.is_symlink() or is_reparse_or_symlink(path):
                    metrics.reparse_points_skipped += 1
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if name not in ignored and depth < limits.max_depth:
                        queue.append((path, depth + 1))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                metrics.files += 1
                metrics.observed_bytes += entry.stat(follow_symlinks=False).st_size
                check()
                relative = path.relative_to(root)
                caller_path = caller_root.joinpath(*relative.parts)
                if include is None or include(caller_path):
                    files.append(caller_path)
            except OSError:
                continue
    metrics.elapsed_ms = round((time.monotonic() - started) * 1000, 3)
    return files, metrics


def iter_git_nul_records(
    root: Path,
    arguments: list[str],
    *,
    max_items: int = 100_000,
    max_bytes: int = 16 * 1024 * 1024,
    max_item_bytes: int = 256 * 1024,
    max_elapsed_ms: int = 10_000,
    include_empty: bool = False,
) -> Iterator[str]:
    """Stream a NUL-delimited Git result without materializing its complete stdout."""
    process = subprocess.Popen(
        ["git", *arguments], cwd=str(root), stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )
    if process.stdout is None:
        process.kill()
        raise RuntimeError("git stdout is unavailable")
    started = time.monotonic()
    pending = bytearray()
    total = 0
    items = 0
    try:
        while True:
            chunk = process.stdout.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            elapsed = (time.monotonic() - started) * 1000
            metrics = TraversalMetrics(entries=items, observed_bytes=total, elapsed_ms=round(elapsed, 3))
            if total > max_bytes:
                raise TraversalLimitReached("git_output_bytes", metrics)
            if elapsed > max_elapsed_ms:
                raise TraversalLimitReached("git_elapsed_ms", metrics)
            pending.extend(chunk)
            if len(pending) > max_item_bytes and b"\0" not in pending:
                raise TraversalLimitReached("git_item_bytes", metrics)
            while True:
                separator = pending.find(0)
                if separator < 0:
                    break
                raw = bytes(pending[:separator])
                del pending[: separator + 1]
                if not raw and not include_empty:
                    continue
                items += 1
                if items > max_items:
                    raise TraversalLimitReached(
                        "git_items",
                        TraversalMetrics(entries=items, observed_bytes=total, elapsed_ms=round(elapsed, 3)),
                    )
                yield raw.decode("utf-8", errors="replace")
        if pending:
            items += 1
            if items > max_items or len(pending) > max_item_bytes:
                raise TraversalLimitReached(
                    "git_items",
                    TraversalMetrics(entries=items, observed_bytes=total),
                )
            yield bytes(pending).decode("utf-8", errors="replace")
        if process.wait() != 0:
            raise RuntimeError(f"git command failed: {arguments[0] if arguments else 'unknown'}")
    finally:
        if process.poll() is None:
            process.kill()
        process.stdout.close()
        process.wait()


def read_bounded_bytes(path: Path, maximum: int) -> tuple[bytes, bool]:
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    return data[:maximum], len(data) > maximum


def read_bounded_text(path: Path, maximum: int = 8 * 1024 * 1024) -> tuple[str, bool]:
    raw, truncated = read_bounded_bytes(path, maximum)
    return raw.decode("utf-8", errors="ignore"), truncated


def bounded_process_run(
    command: list[str],
    cwd: Path,
    *,
    check: bool = True,
    max_stdout_bytes: int = 1024 * 1024,
    max_stderr_bytes: int = 256 * 1024,
    timeout_seconds: float = 60.0,
) -> subprocess.CompletedProcess[str]:
    """Run a Hiker-controlled command without unbounded result materialization."""
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise OSError("bounded process pipes unavailable")
    stdout = io.BytesIO()
    stderr = io.BytesIO()
    out_receipt = CaptureReceipt()
    err_receipt = CaptureReceipt()
    out_thread = start_capture_thread(process.stdout, stdout, CaptureBudget(max_spool_bytes=max_stdout_bytes), out_receipt)
    err_thread = start_capture_thread(process.stderr, stderr, CaptureBudget(max_spool_bytes=max_stderr_bytes), err_receipt)
    try:
        try:
            return_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise
        out_thread.join(timeout=5)
        err_thread.join(timeout=5)
        if out_thread.is_alive() or err_thread.is_alive():
            raise subprocess.SubprocessError("bounded command capture did not converge")
        if out_receipt.truncated or err_receipt.truncated:
            receipt = out_receipt if out_receipt.truncated else err_receipt
            channel = "stdout" if out_receipt.truncated else "stderr"
            raise TraversalLimitReached(
                f"process_{channel}_bytes",
                TraversalMetrics(
                    entries=receipt.lines,
                    observed_bytes=receipt.observed_bytes,
                ),
            )
        output = stdout.getvalue().decode("utf-8", errors="replace")
        error = stderr.getvalue().decode("utf-8", errors="replace")
        completed = subprocess.CompletedProcess(command, return_code, output, error)
        if check and return_code != 0:
            raise subprocess.CalledProcessError(return_code, command, output=output, stderr=error)
        return completed
    finally:
        if process.poll() is None:
            process.kill()
        process.stdout.close()
        process.stderr.close()
