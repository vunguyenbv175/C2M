#!/usr/bin/env python3
"""Host-only review/preparation of a narrow stock TSR flag change.

No device access, serial/IPC writes, credentials or automatic deployment.
Input must be a private owner-provided adas.flag (strict base64) or decoded
adas_de.flag snapshot. Output is a private staged pair and hash-only report.
This is NOT a runtime enable/recognition proof. Never use a post-C snapshot
as a pre-C backup. The C hook may re-enable TSR on a later reboot.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import math
import re
from pathlib import Path

KEYS = {
    "enable_tsr": ("bool", None, None),
    "tsrw_interval": ("number", 0, 3600),
    "tsrw_sli_over_min_ratio": ("number", 0, 100),
    "tsrw_sli_over_min_thresh": ("number", 0, 200),
    "tsrw_sli_speed_min_thresh": ("number", 0, 200),
    "tsrw_sli_speed_max_thresh": ("number", 0, 200),
    "tsrw_sli_host_speed_min_thresh": ("number", 0, 200),
    "tsrw_sli_host_speed_max_thresh": ("number", 0, 200),
}
# Numeric bounds are host review policy, not recovered detector/model limits.
MAX_BYTES = 256 * 1024
LINE = re.compile(rb"^([ \t]*)--([A-Za-z_][A-Za-z_0-9]*)=([^ \t\r\n#]+)([ \t]*)$")
NUMBER = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_value(key: str, value: str) -> None:
    if key not in KEYS:
        raise ValueError("profile contains a non-TSR key")
    kind, low, high = KEYS[key]
    if kind == "bool":
        if value not in ("true", "false"):
            raise ValueError("invalid TSR boolean")
        return
    if not NUMBER.fullmatch(value):
        raise ValueError("invalid TSR numeric value")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError("TSR numeric value outside host review policy")


def decode_source(data: bytes, encoded: bool) -> bytes:
    if not data or len(data) > MAX_BYTES:
        raise ValueError("config empty or exceeds input bound")
    if encoded:
        # Stock wraps base64 with LF; only ASCII whitespace may be removed.
        compact = re.sub(rb"[ \t\r\n]", b"", data)
        try:
            data = base64.b64decode(compact, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("invalid base64 config") from None
    if not data or len(data) > MAX_BYTES or b"\x00" in data or b"\r" in data:
        raise ValueError("decoded config invalid, non-LF or exceeds bound")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("decoded config is not UTF-8") from None
    if not data.endswith(b"\n"):
        raise ValueError("decoded config lacks final LF")
    return data


def inspect(data: bytes) -> dict[str, str]:
    """Only inspect active TSR keys; do not emit unrelated config fields."""
    found: dict[str, str] = {}
    for raw in data.splitlines():
        stripped = raw.strip(b" \t")
        if not stripped or stripped.startswith(b"#"):
            continue
        match = LINE.fullmatch(raw)
        # Reject ambiguous formatting ONLY for relevant keys; unrelated stock
        # content is preserved verbatim, not interpreted by this tool.
        if not match:
            if any(re.search(rb"--" + key.encode() + rb"\b", stripped)
                   for key in KEYS):
                raise ValueError("ambiguous active TSR config line")
            continue
        key = match[2].decode("ascii")
        if key not in KEYS:
            continue
        if key in found:
            raise ValueError("duplicate active TSR key")
        value = match[3].decode("ascii")
        validate_value(key, value)
        found[key] = value
    return found


def apply_profile(data: bytes, profile: dict[str, str]) -> tuple[bytes, dict]:
    if not isinstance(profile, dict) or not profile:
        raise ValueError("profile must be a nonempty object")
    for key, value in profile.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("profile keys/values must be strings")
        validate_value(key, value)
    before = inspect(data)
    if set(profile) - set(before):
        raise ValueError("requested TSR key absent: no implicit insertion")
    after = {**before, **profile}
    for low, high in (("tsrw_sli_speed_min_thresh", "tsrw_sli_speed_max_thresh"),
                      ("tsrw_sli_host_speed_min_thresh", "tsrw_sli_host_speed_max_thresh")):
        if low in after and high in after and float(after[low]) > float(after[high]):
            raise ValueError("TSR minimum exceeds maximum")
    output = []
    changes = []
    for line in data.splitlines(keepends=True):
        raw = line[:-1]
        match = LINE.fullmatch(raw)
        key = match[2].decode("ascii") if match else None
        if key in profile:
            value = profile[key].encode("ascii")
            output.append(match[1] + b"--" + match[2] + b"=" + value + match[4] + b"\n")
            if before[key] != profile[key]:
                changes.append({"key": key, "old": before[key], "new": profile[key]})
        else:
            output.append(line)
    result = b"".join(output)
    # Independent invariant: removing authorized lines leaves exactly the same
    # original bytes, including comments, ordering, whitespace and other flags.
    def outside(blob: bytes) -> bytes:
        return b"".join(line for line in blob.splitlines(keepends=True)
                        if not (m := LINE.fullmatch(line[:-1]))
                        or m[2].decode("ascii") not in profile)
    if outside(data) != outside(result) or inspect(result) != after:
        raise ValueError("non-TSR byte-preservation invariant failed")
    encoded = base64.encodebytes(result)
    if base64.b64decode(encoded, validate=False) != result:
        raise ValueError("encoded/decoded consistency failed")
    report = {"verdict": "HOST_STAGED_ONLY", "source_decoded_sha256": sha(data),
              "output_decoded_sha256": sha(result), "output_encoded_sha256": sha(encoded),
              "outside_authorized_keys_unchanged": True, "changes": changes,
              "device_access": False, "runtime_verified": False,
              "warning": "C hook may re-enable false on boot; no deploy/rollback authorization implied."}
    return result, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--encoded", action="store_true", help="source is base64 adas.flag")
    ap.add_argument("--profile", type=Path, help="JSON object of existing TSR keys => string values")
    ap.add_argument("--out-dir", type=Path, help="PRIVATE staging dir, must not already exist")
    args = ap.parse_args()
    try:
        data = decode_source(args.source.read_bytes(), args.encoded)
        found = inspect(data)
        if args.profile is None:
            if args.out_dir is not None:
                raise ValueError("out-dir requires a profile")
            # Output only the reviewed TSR subset. Never dump config body.
            print(json.dumps({"verdict": "HOST_INSPECTED_ONLY", "tsr_keys": found,
                              "missing_keys": sorted(set(KEYS) - set(found)),
                              "decoded_sha256": sha(data), "runtime_verified": False}, indent=2))
        else:
            if args.out_dir is None:
                raise ValueError("profile requires private out-dir")
            profile = json.loads(args.profile.read_text(encoding="utf-8"))
            decoded, report = apply_profile(data, profile)
            args.out_dir.mkdir(parents=True, exist_ok=False)
            (args.out_dir / "adas_de.flag").write_bytes(decoded)
            (args.out_dir / "adas.flag").write_bytes(base64.encodebytes(decoded))
            (args.out_dir / "review.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2))
    except (OSError, ValueError, UnicodeError):
        # Private input/path/config may contain sensitive data. Avoid echoing it.
        print("TSR-PROFILE: BLOCK (invalid input/profile or output path; no deployment performed)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
