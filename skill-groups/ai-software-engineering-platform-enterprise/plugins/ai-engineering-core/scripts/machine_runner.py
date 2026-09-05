from __future__ import annotations

import io
import subprocess
from typing import Any

from result_fuse import CaptureBudget, CaptureReceipt, start_capture_thread


def bounded_machine_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(command, cwd=kwargs.get("cwd"), env=kwargs.get("env"), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise OSError("machine command pipes unavailable")
    stdout, stderr = io.BytesIO(), io.BytesIO()
    out_receipt, err_receipt = CaptureReceipt(), CaptureReceipt()
    out_thread = start_capture_thread(process.stdout, stdout, CaptureBudget(max_spool_bytes=512 * 1024), out_receipt)
    err_thread = start_capture_thread(process.stderr, stderr, CaptureBudget(max_spool_bytes=128 * 1024), err_receipt)
    try:
        try:
            code = process.wait(timeout=kwargs.get("timeout"))
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(); raise
        out_thread.join(timeout=5); err_thread.join(timeout=5)
        if out_thread.is_alive() or err_thread.is_alive():
            raise subprocess.SubprocessError("machine result capture did not converge")
        completed = subprocess.CompletedProcess(command, code, stdout.getvalue().decode("utf-8", errors="replace"), stderr.getvalue().decode("utf-8", errors="replace"))
        if kwargs.get("check", False) and code != 0:
            raise subprocess.CalledProcessError(code, command, output=completed.stdout, stderr=completed.stderr)
        return completed
    finally:
        if process.poll() is None: process.kill()
        process.stdout.close(); process.stderr.close()
