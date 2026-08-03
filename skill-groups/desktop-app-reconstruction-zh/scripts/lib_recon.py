#!/usr/bin/env python3
"""Shared helpers for the desktop reconstruction skill.

The module intentionally uses only the Python standard library.  Its YAML
reader supports the conservative subset emitted by this skill's templates;
it is not a general YAML implementation.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

UNKNOWN_VALUES = {
    "",
    "unknown",
    "undecided",
    "unverified",
    "not_run",
    "not run",
    "n/a",
    "na",
    "none",
    "null",
    "latest",
    "stable",
    "lts",
    "*",
    "x",
}

PASS_VALUES = {"pass", "passed", "ready", "verified", "locked", "accepted", "closed"}
FAIL_VALUES = {"fail", "failed", "missing", "blocked", "not_ready", "open"}
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
ID_SPLIT_RE = re.compile(r"[;,|\s]+")


def normalized(value: Any) -> str:
    return str(value if value is not None else "").strip().lower()


def is_unknown(value: Any) -> bool:
    text = normalized(value)
    if text in UNKNOWN_VALUES:
        return True
    return any(token in text for token in ("{{", "}}"))


def is_true(value: Any) -> bool:
    return normalized(value) in {"true", "1", "yes", "y", "是"}


def is_pass(value: Any) -> bool:
    return normalized(value) in PASS_VALUES


def split_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(split_ids(item))
        return result
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in ID_SPLIT_RE.split(text) if part.strip()]


def unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def write_csv_rows(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_path(path: Path) -> str:
    """Hash a file or a directory deterministically.

    Directory hashes include each relative path, a separator, and the file
    digest.  Metadata and timestamps are intentionally excluded.
    """

    if path.is_file():
        return sha256_file(path)
    if path.is_dir():
        digest = hashlib.sha256()
        for child in sorted(p for p in path.rglob("*") if p.is_file()):
            rel = child.relative_to(path).as_posix().encode("utf-8")
            digest.update(rel)
            digest.update(b"\0")
            digest.update(sha256_file(child).encode("ascii"))
            digest.update(b"\n")
        return digest.hexdigest()
    raise FileNotFoundError(path)


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def contains_placeholders(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError):
        return []
    return sorted(set(PLACEHOLDER_RE.findall(text)))


def nonempty_content(path: Path) -> bool:
    if path.is_file():
        return path.stat().st_size > 0
    if path.is_dir():
        return any(p.is_file() for p in path.rglob("*"))
    return False


def _strip_comment(line: str) -> str:
    """Strip an unquoted YAML comment from a simple line."""

    quote: str | None = None
    escaped = False
    for idx, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {'"', "'"}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue
        if char == "#" and quote is None and (idx == 0 or line[idx - 1].isspace()):
            return line[:idx].rstrip()
    return line.rstrip()


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in {"null", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inside = value[1:-1].strip()
        if not inside:
            return []
        # The templates use simple scalar inline lists only.
        parts: list[str] = []
        current = ""
        quote: str | None = None
        for char in inside:
            if char in {'"', "'"}:
                quote = None if quote == char else (char if quote is None else quote)
                current += char
            elif char == "," and quote is None:
                parts.append(current.strip())
                current = ""
            else:
                current += char
        if current.strip():
            parts.append(current.strip())
        return [parse_scalar(part) for part in parts]
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            pass
    if re.fullmatch(r"-?\d+\.\d+", value):
        try:
            return float(value)
        except ValueError:
            pass
    return value


@dataclass(frozen=True)
class YamlLine:
    indent: int
    text: str
    line_no: int


def _yaml_lines(path: Path) -> list[YamlLine]:
    result: list[YamlLine] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not raw.strip():
            continue
        stripped = raw.lstrip(" ")
        if stripped.startswith("#"):
            continue
        clean = _strip_comment(raw)
        if not clean.strip():
            continue
        indent = len(clean) - len(clean.lstrip(" "))
        if "\t" in clean[:indent]:
            raise ValueError(f"YAML 第 {line_no} 行使用了制表符")
        result.append(YamlLine(indent=indent, text=clean.strip(), line_no=line_no))
    return result


def parse_simple_yaml(path: Path) -> Any:
    """Parse the limited YAML subset emitted by this skill.

    Supports nested mappings, sequences of scalars/mappings, quoted scalars,
    booleans, numbers, nulls, and inline scalar lists.  Anchors, multiline
    strings, tags, and flow mappings are intentionally unsupported.
    """

    lines = _yaml_lines(path)
    if not lines:
        return {}

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(lines):
            return {}, index
        is_list = lines[index].indent == indent and lines[index].text.startswith("- ")
        container: Any = [] if is_list else {}

        while index < len(lines):
            item = lines[index]
            if item.indent < indent:
                break
            if item.indent > indent:
                raise ValueError(
                    f"YAML 第 {item.line_no} 行缩进异常：预期 {indent}，实际 {item.indent}"
                )

            if is_list:
                if not item.text.startswith("- "):
                    break
                payload = item.text[2:].strip()
                if not payload:
                    if index + 1 < len(lines) and lines[index + 1].indent > indent:
                        child, index = parse_block(index + 1, lines[index + 1].indent)
                        container.append(child)
                    else:
                        container.append(None)
                        index += 1
                    continue

                if ":" in payload:
                    key, raw_value = payload.split(":", 1)
                    entry: dict[str, Any] = {key.strip(): parse_scalar(raw_value)} if raw_value.strip() else {key.strip(): {}}
                    index += 1
                    # Consume subsequent mapping fields belonging to this list item.
                    while index < len(lines) and lines[index].indent > indent:
                        child_indent = lines[index].indent
                        child_text = lines[index].text
                        if child_text.startswith("- "):
                            # A nested list belongs to the last empty key.
                            empty_keys = [k for k, v in entry.items() if v == {}]
                            if not empty_keys:
                                raise ValueError(f"YAML 第 {lines[index].line_no} 行无法关联嵌套列表")
                            child, index = parse_block(index, child_indent)
                            entry[empty_keys[-1]] = child
                            continue
                        if ":" not in child_text:
                            raise ValueError(f"YAML 第 {lines[index].line_no} 行缺少冒号")
                        child_key, child_raw = child_text.split(":", 1)
                        child_key = child_key.strip()
                        if child_raw.strip():
                            entry[child_key] = parse_scalar(child_raw)
                            index += 1
                        else:
                            if index + 1 < len(lines) and lines[index + 1].indent > child_indent:
                                child, index = parse_block(index + 1, lines[index + 1].indent)
                                entry[child_key] = child
                            else:
                                entry[child_key] = {}
                                index += 1
                    container.append(entry)
                else:
                    container.append(parse_scalar(payload))
                    index += 1
                continue

            if item.text.startswith("- "):
                break
            if ":" not in item.text:
                raise ValueError(f"YAML 第 {item.line_no} 行缺少冒号")
            key, raw_value = item.text.split(":", 1)
            key = key.strip()
            if raw_value.strip():
                container[key] = parse_scalar(raw_value)
                index += 1
            else:
                if index + 1 < len(lines) and lines[index + 1].indent > indent:
                    child, index = parse_block(index + 1, lines[index + 1].indent)
                    container[key] = child
                else:
                    container[key] = {}
                    index += 1
        return container, index

    root, final_index = parse_block(0, lines[0].indent)
    if final_index != len(lines):
        item = lines[final_index]
        raise ValueError(f"YAML 第 {item.line_no} 行未被解析")
    return root


def get_nested(data: Any, *keys: str, default: Any = None) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def project_delivery_mode(root: Path) -> str:
    project = root / "00_control" / "PROJECT.yaml"
    if not project.is_file():
        return "analysis"
    try:
        data = parse_simple_yaml(project)
        value = get_nested(data, "project", "delivery_mode", default="analysis")
        return normalized(value) or "analysis"
    except Exception:
        return "analysis"


def iter_text_files(root: Path) -> Iterator[Path]:
    extensions = {".md", ".yaml", ".yml", ".csv", ".json", ".txt", ".toml", ".xml"}
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in extensions:
            yield path


def markdown_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    safe_headers = [str(h).replace("|", "\\|") for h in headers]
    output = ["| " + " | ".join(safe_headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        values = [str(v if v is not None else "").replace("|", "\\|").replace("\n", " ") for v in row]
        output.append("| " + " | ".join(values) + " |")
    return "\n".join(output)


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("---\n"):
        raise ValueError("缺少 YAML frontmatter 起始标记")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("缺少 YAML frontmatter 结束标记")
    header_text = text[4:end]
    body = text[end + 5 :]
    header: dict[str, str] = {}
    for line in header_text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"frontmatter 行无冒号：{line}")
        key, value = line.split(":", 1)
        header[key.strip()] = str(parse_scalar(value))
    return header, body
