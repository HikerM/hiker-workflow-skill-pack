from __future__ import annotations

import ctypes
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any


IDENTITY_VERSION = "pid-start-v1"


def pid_presence(pid: int) -> bool | None:
    """Return True/False only when process presence can be proved."""
    pid = int(pid)
    if pid <= 0:
        return False
    if os.name == "nt":
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False if ctypes.get_last_error() in {87, 1168} else None
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return None
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None


def process_identity(pid: int) -> dict[str, Any] | None:
    """Capture PID reuse-safe identity without persisting command lines or source."""
    pid = int(pid)
    if pid <= 0:
        return None
    start_marker = ""
    executable_marker = ""
    if os.name == "nt":
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

        process_query_limited_information = 0x1000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
        )
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return None
        try:
            creation = FILETIME()
            exit_time = FILETIME()
            kernel = FILETIME()
            user = FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return None
            start_marker = str((int(creation.high) << 32) | int(creation.low))
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                executable_marker = buffer.value.casefold()
        finally:
            kernel32.CloseHandle(handle)
    else:
        stat = Path(f"/proc/{pid}/stat")
        if stat.is_file():
            raw = stat.read_text(encoding="utf-8", errors="replace")
            end_name = raw.rfind(")")
            fields = raw[end_name + 2 :].split() if end_name >= 0 else []
            if len(fields) < 20:
                return None
            start_marker = fields[19]
            try:
                executable_marker = str(Path(f"/proc/{pid}/exe").resolve())
            except OSError:
                executable_marker = ""
        else:
            probe = subprocess.run(
                ["ps", "-p", str(pid), "-o", "lstart=", "-o", "comm="],
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            marker = probe.stdout.strip()
            if probe.returncode != 0 or not marker:
                return None
            start_marker, executable_marker = marker, marker
    fingerprint = hashlib.sha256(
        f"{pid}|{start_marker}|{executable_marker}".encode("utf-8", errors="replace")
    ).hexdigest()
    return {
        "identity_version": IDENTITY_VERSION,
        "pid": pid,
        "process_fingerprint": fingerprint,
    }


def owner_status(owner: dict[str, Any]) -> str:
    """Classify a lock owner without treating age as evidence of death."""
    try:
        pid = int(owner.get("pid") or 0)
    except (TypeError, ValueError):
        return "DAMAGED"
    if pid <= 0:
        return "DAMAGED"
    presence = pid_presence(pid)
    if presence is False:
        return "DEAD"
    expected = owner.get("runtime_identity")
    if isinstance(expected, dict) and expected.get("process_fingerprint"):
        current = process_identity(pid)
        if current is not None and current != expected:
            return "IDENTITY_CHANGED"
        if current == expected:
            return "ALIVE"
    if presence is True:
        return "ALIVE_UNVERIFIED"
    return "UNKNOWN"
