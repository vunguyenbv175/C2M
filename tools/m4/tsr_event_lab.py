#!/usr/bin/env python3
"""D3: summarize stock TSR MessagePack capture files (not a device daemon).

This discovers actual field shapes without guessing enum meanings, speed units
or emitting private sign values/GPS coordinates. Inputs are private
frame-*.msgpack files produced by capture_tsr_readonly.py.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

from libflow_protocol import decode_ws_binary

MAX_FRAME_BYTES = 256 * 1024
MAX_DEPTH = 4
MAX_FIELDS = 100
TSR_KEYS = frozenset({"tsr_warning", "tsr_trace_res_list"})


def field_shapes(value: Any, prefix: str = "data", depth: int = 0) -> set[str]:
    """Only output schema paths and types, never actual values."""
    if depth >= MAX_DEPTH:
        return {prefix + ":depth_limit"}
    if isinstance(value, dict):
        shapes = {prefix + ":object"}
        for key in list(value)[:MAX_FIELDS]:
            if isinstance(key, str) and key.isidentifier() and len(key) <= 64:
                shapes.update(field_shapes(value[key], prefix + "." + key, depth + 1))
            else:
                shapes.add(prefix + ":unrecognized_key")
        return shapes
    if isinstance(value, list):
        shapes = {prefix + ":array"}
        if value:
            shapes.update(field_shapes(value[0], prefix + "[]", depth + 1))
        return shapes
    if isinstance(value, bool):
        kind = "bool"
    elif isinstance(value, int):
        kind = "int"
    elif isinstance(value, float):
        kind = "float"
    elif isinstance(value, str):
        kind = "string"
    elif isinstance(value, (bytes, bytearray)):
        kind = "binary"
    elif value is None:
        kind = "null"
    else:
        kind = "other"
    return {prefix + ":" + kind}


def analyze(folder: Path) -> dict:
    files = sorted(folder.glob("frame-*.msgpack"))
    stats: Counter[str] = Counter()
    schemas: dict[str, Counter[str]] = {}
    frames = []
    for file in files:
        stats["all_frames"] += 1
        try:
            if not file.is_file() or file.stat().st_size > MAX_FRAME_BYTES:
                raise ValueError("not a bounded frame")
            decoded = decode_ws_binary(file.read_bytes())
            if decoded.outer.get("topic") != "tsr":
                stats["other_topic"] += 1
                continue
            stats["tsr_topic"] += 1
            if not isinstance(decoded.inner, dict):
                stats["unknown_inner"] += 1
                continue
            key = decoded.inner.get("key")
            if key not in TSR_KEYS:
                stats["unrecognized_tsr_key"] += 1
                continue
            data = decoded.inner.get("data")
            stats["recognized_tsr_envelopes"] += 1
            shapes = field_shapes(data)
            schemas.setdefault(key, Counter()).update(shapes)
            frames.append({
                "file": file.name, "key": key,
                "data_shape": "list" if isinstance(data, list) else
                              "dict" if isinstance(data, dict) else type(data).__name__,
                "nonempty": bool(data), "schema_fields": len(shapes),
            })
        except Exception:
            # One malformed/unexpected stock payload must not obscure the rest.
            stats["decode_error"] += 1
    return {
        "contract": "D3_STOCK_TSR_EVENT_SCHEMA_PROBE_V1",
        "status": "OBSERVED_ENVELOPES_NOT_CLASSIFIED_SIGNS",
        "disclaimer": "A TSR envelope or nonempty payload does not prove a recognized sign.",
        "stats": dict(sorted(stats.items())),
        "keys": {key: dict(sorted(fields.items())) for key, fields in sorted(schemas.items())},
        "frames": frames,
        "device_flash": False, "audio_or_ui_changed": False,
    }


def markdown(report: dict) -> str:
    stats = report["stats"]
    lines = [
        "# D3 TSR event/schema report", "",
        "Observed native message envelopes only; sign meaning and units remain unverified.", "",
        f"Frames: {stats.get('all_frames', 0)}; TSR topic: {stats.get('tsr_topic', 0)}; "
        f"known envelopes: {stats.get('recognized_tsr_envelopes', 0)}; "
        f"decode errors: {stats.get('decode_error', 0)}.", "",
    ]
    for key, paths in report["keys"].items():
        lines += [f"## {key}", ""]
        for path, n in paths.items():
            lines.append(f"- {path}: {n} frame(s)")
        lines.append("")
    lines += [
        "## Next D3 integration gate", "",
        "Verify captured field semantics, then bind verified events to the stock "
        "display/audio path. No sign value or message meaning is inferred.", "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("capture_dir", type=Path)
    ap.add_argument("--json-out", type=Path, help="optional report path")
    ap.add_argument("--md-out", type=Path, help="optional Markdown report path")
    args = ap.parse_args()
    if not args.capture_dir.is_dir():
        ap.error("capture_dir is not a directory")
    report = analyze(args.capture_dir)
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.md_out:
        args.md_out.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "stats": report["stats"],
        "keys": sorted(report["keys"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
