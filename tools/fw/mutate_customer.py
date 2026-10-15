#!/usr/bin/env python3
"""P2: apply the narrow Candidate-B mutation to an extracted customer tree.

Mutation (exactly):
  1. add directory `c2m/` (mode 0755);
  2. add `c2m/c2m-idle` (mode 0755) from --idle-bin (ARM binary built by the
     product-CI arm-dyn path);
  3. install ONE background launch of the idle binary into the stock hook
     script (default `wifi/rcInsDriver.sh`, i.e. on-device
     /customer/wifi/rcInsDriver.sh) on a REACHABLE path that preserves the
     stock exit status:
       - hook ends with a terminal `exit ...` line (the stock shape):
         insert a launch block BEFORE that line: save `$?`, wait bounded
         (30x2s, backgrounded subshell) for the `/mnt/mmc` recording-card
         mount, start the daemon backgrounded with stdio detached, then
         exit with the saved status. Appending after it would be dead code:
         the hook is executed (not sourced), so `exit` ends the script
         before any later line runs (B2 field defect, 2026-10-13). The
         mount wait fixes the 2026-10-14 field finding (daemon START at
         uptime=6 on the flash card, no logs on recording-card boots).
       - hook has no terminal `exit`: append the single launch line at EOF
         (legacy fallback; reachable because control falls off the end).
  4. (optional `--audio-replacements` JSON): swap ADAS wav assets with
     format-validated replacements (RIFF/WAVE, PCM16, mono, 24 kHz) and
     refresh exactly the matching `md5sum.txt` lines; everything else
     byte-identical. Missing-image files with an md5sum line (e.g. the
     stock-absent `tlr_green_on.wav`) may be ADDED with a sibling's mode.
  5. (optional `--tsr-patch`): prepend an idempotent TSR flag patch to the
     launch block — decode device `adas.flag`, flip the first
     `--enable_tsr=false` to `true` once, rewrite both flag files
     consistently (so `run.sh` observes no md5 drift), using only
     base64/grep/sed/rm already present on device. Skips silently when the
     flag file is absent or already patched.
  6. (optional `--d3-services-dir`, requires `--tsr-experiment`): install
     isolated D3 services; launch boot.sh detached after the idle daemon.
  7. (optional D4, requires D3 + checked TSR): install exactly c2m-signs,
     d4_boot.sh and SHA256-pinned private signs-d4.bin; only directional
     R.420/R.421 records are permitted. Launch d4_boot.sh detached after
     D3 boot in the same bounded background mount-wait block. Database
     reports contain only count/hash, never coordinates, labels or bytes.

Fail-closed guards:
  - --manifest (stock manifest JSON) REQUIRED: hook file content must hash
    exactly to the stock manifest entry before edit (unexpected base BLOCKS);
  - the launch line / repair block must not already be present (no
    double-hook, no double-repair);
  - audio targets must exist in the stock manifest (or be md5sum-listed
    additions); replacement wavs must pass format validation;
  - after edit, re-walk: ONLY the allowlisted paths may differ
    (added /c2m*, hook, replaced audios + md5sum.txt).

Outputs --out-manifest (mutation manifest: added/modified/replaced + shas).

Usage (tree paths are image-relative, no /customer prefix):
  python3 tools/fw/mutate_customer.py --tree <dir> --manifest <stock.json> \\
      --idle-bin <c2m-idle> --hook wifi/rcInsDriver.sh \\
      --hook-line '/customer/c2m/c2m-idle &' --out-manifest mut.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import re
import stat
import struct
import unicodedata
from pathlib import Path

DEFAULT_HOOK_LINE = "/customer/c2m/c2m-idle &"
D4_RECORD = struct.Struct("<ddf16s64s")
D4_MAX_BYTES = 12 + 40000 * D4_RECORD.size
# A reviewed 12,708-record subset fits; never stage the whole source DB.
D4_MAX_OUTPUT_BYTES = 1_300_000
D4_MODES = {"c2m-signs": 0o755, "d4_boot.sh": 0o755, "signs-d4.bin": 0o644}
DEBUG_MODES = {"c2m-debug": 0o755, "dropbear": 0o755,
               "dropbearkey": 0o755, "debug_boot.sh": 0o755,
               "debug_owner.pub": 0o644}
DEBUG_NAMES = ("c2m-debug", "dropbear", "dropbearkey", "debug_boot.sh")
DEBUG_ELF_NAMES = ("c2m-debug", "dropbear", "dropbearkey")
DEBUG_MAX_SUPERVISOR = 256 * 1024
DEBUG_MAX_DROPBEAR = 2 * 1024 * 1024
DEBUG_MAX_SHELL = 64 * 1024
DEBUG_OWNER_COMMENT = "c2m-debug-owner"
DEBUG_OWNER_MAX_BYTES = 1024


def has_symlink(path: Path) -> bool:
    # Check parents too: a regular leaf reached through a link is not a safe
    # source or destination. Do not resolve first (that would hide the link).
    absolute = path.absolute()
    return any(p.is_symlink() or (getattr(p, "is_junction", lambda: False)())
               for p in (absolute, *absolute.parents))


def check_d4_database(data: bytes, expected_sha256: str) -> dict:
    """Gate an already filtered private subset; never echo records or labels."""
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError("D4 database needs an exact 64-hex SHA256 pin")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256.lower():
        raise ValueError("D4 database SHA256 mismatch")
    if len(data) < 12 or len(data) > D4_MAX_BYTES or data[:8] != b"C2MSDB01":
        raise ValueError("invalid D4 database header/size")
    count = struct.unpack_from("<I", data, 8)[0]
    if not 1 <= count <= 40000 or len(data) != 12 + count * D4_RECORD.size:
        raise ValueError("invalid D4 database count/length")

    def text_field(raw: bytes) -> str:
        prefix, separator, padding = raw.partition(b"\0")
        if not separator or any(padding):
            raise ValueError("noncanonical D4 database string")
        try:
            value = prefix.decode("utf-8", "strict")
        except UnicodeError:
            raise ValueError("invalid D4 database UTF-8") from None
        if any(unicodedata.category(c) == "Cc" for c in value):
            raise ValueError("control character in D4 database string")
        return value

    for offset in range(12, len(data), D4_RECORD.size):
        lat, lon, heading, kind_raw, label_raw = D4_RECORD.unpack_from(data, offset)
        if not all(math.isfinite(v) for v in (lat, lon, heading)):
            raise ValueError("nonfinite D4 database number")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("D4 database coordinate outside range")
        # The producer may normalize 360 to zero; the install gate must not
        # silently repair an unreviewed input, nor accept unknown headings.
        if not 0 <= heading < 360:
            raise ValueError("D4 database requires known heading in [0, 360)")
        if text_field(kind_raw) not in ("R.420", "R.421"):
            raise ValueError("D4 database permits only R.420/R.421")
        text_field(label_raw)
    return {"count": count, "sha256": digest}


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_debug_owner_key(data: bytes, expected_sha256: str) -> dict:
    """Gate the AP-only debug owner Ed25519 public key; never echo key bytes."""
    import base64 as _b64
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError("Debug owner key needs an exact 64-hex SHA256 pin")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256.lower():
        raise ValueError("Debug owner key SHA256 mismatch")
    if len(data) == 0 or len(data) > DEBUG_OWNER_MAX_BYTES:
        raise ValueError("invalid debug owner key length")
    if b"\r" in data:
        raise ValueError("invalid debug owner key line ending")
    if not data.endswith(b"\n") or data.count(b"\n") != 1:
        raise ValueError("debug owner key must be exactly one line")
    try:
        text = data.decode("ascii", "strict")
    except UnicodeError:
        raise ValueError("debug owner key must be ASCII") from None
    if any(ord(c) < 32 or ord(c) == 127 for c in text if c != "\n"):
        raise ValueError("control character in debug owner key")
    body = text[:-1]
    parts = body.split(" ")
    if len(parts) != 3 or any(not p for p in parts):
        raise ValueError("debug owner key must be one OpenSSH line without options")
    keytype, b64, comment = parts
    if keytype != "ssh-ed25519":
        raise ValueError("debug owner key must be ssh-ed25519")
    if comment != DEBUG_OWNER_COMMENT:
        raise ValueError("invalid debug owner key comment")
    if "PRIVATE" in body or "BEGIN" in body:
        raise ValueError("private key material rejected")
    if not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", b64):
        raise ValueError("noncanonical debug owner key base64")
    try:
        blob = _b64.b64decode(b64, validate=True)
    except Exception:
        raise ValueError("noncanonical debug owner key base64") from None
    if _b64.b64encode(blob).decode("ascii") != b64:
        raise ValueError("noncanonical debug owner key base64")
    if len(blob) != 51:
        raise ValueError("truncated debug owner key blob")
    if (int.from_bytes(blob[0:4], "big") != 11 or blob[4:15] != b"ssh-ed25519"
            or int.from_bytes(blob[15:19], "big") != 32 or len(blob[19:]) != 32):
        raise ValueError("invalid debug owner key blob")
    return {"sha256": digest}


def md5_bytes(d: bytes) -> str:
    return hashlib.md5(d).hexdigest()


# Stock ADAS warning encoding (checked on adas_activated.wav: RIFF/WAVE,
# PCM16, mono, 24000 Hz). Replacements with any other encoding are BLOCKED:
# the on-device player path is reverse-engineered, not negotiated.
def check_wav(data: bytes, what: str) -> None:
    if not (len(data) > 44 and data[0:4] == b"RIFF" and data[8:12] == b"WAVE"):
        raise ValueError(f"wav rejected (not RIFF/WAVE): {what}")
    fmt, ch, rate, bits = (struct.unpack("<H", data[20:22])[0],
                           struct.unpack("<H", data[22:24])[0],
                           struct.unpack("<I", data[24:28])[0],
                           struct.unpack("<H", data[34:36])[0])
    if (fmt, ch, rate, bits) != (1, 1, 24000, 16):
        raise ValueError(
            f"wav rejected (want PCM16/mono/24kHz, got fmt={fmt} ch={ch} "
            f"rate={rate} bits={bits}): {what}")
    if len(data) > (1 << 20):
        raise ValueError(f"wav rejected (over 1MB): {what}")


TSR_PATCH_LINES = [
    'if [ -f /customer/minieye/config/adas.flag ]; then',
    'base64 -d /customer/minieye/config/adas.flag > /tmp/c2m_adas_de.tmp',
    'if grep -q -e "--enable_tsr=false" /tmp/c2m_adas_de.tmp; then',
    'sed -e s/--enable_tsr=false/--enable_tsr=true/ /tmp/c2m_adas_de.tmp > /customer/minieye/config/adas_de.flag',
    'base64 /customer/minieye/config/adas_de.flag > /customer/minieye/config/adas.flag',
    'fi',
    'rm -f /tmp/c2m_adas_de.tmp',
    'fi',
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True,
                    help="stock manifest JSON (base integrity gate)")
    ap.add_argument("--idle-bin", type=Path, required=True)
    ap.add_argument("--hook", default="wifi/rcInsDriver.sh")
    ap.add_argument("--hook-line", default=DEFAULT_HOOK_LINE)
    ap.add_argument("--audio-replacements", type=Path, default=None,
                    help="JSON list of {path (image-absolute), file (local wav)}")
    tsr = ap.add_mutually_exclusive_group()
    tsr.add_argument("--tsr-patch", action="store_true",
                     help="legacy C literal TSR flag patch (frozen behavior)")
    tsr.add_argument("--tsr-experiment", action="store_true",
                     help="D experimental checked TSR profile + private backup/status")
    ap.add_argument("--d3-services-dir", type=Path,
                    help="D3 isolated boot/probe/web/WiFi binaries (requires checked TSR)")
    ap.add_argument("--d4-services-dir", type=Path,
                    help="D4 c2m-signs + d4_boot.sh only (requires D3 and checked TSR)")
    ap.add_argument("--d4-database", type=Path,
                    help="private, prefiltered directional R.420/R.421 database")
    ap.add_argument("--d4-database-sha256",
                    help="mandatory exact 64-hex SHA256 of the D4 database")
    ap.add_argument("--debug-services-dir", type=Path,
                    help="debug supervisor/dropbear/boot (requires D3 and checked TSR)")
    ap.add_argument("--debug-owner-key", type=Path,
                    help="AP-only Ed25519 owner public key OpenSSH line")
    ap.add_argument("--debug-owner-key-sha256",
                    help="mandatory exact 64-hex SHA256 of the owner public key")
    ap.add_argument("--out-manifest", type=Path, required=True)
    args = ap.parse_args()

    d4_assets: dict[str, bytes] = {}
    d4_database = None
    if any(value is not None for value in
           (args.d4_services_dir, args.d4_database, args.d4_database_sha256)):
        if any(value is None for value in
               (args.d4_services_dir, args.d4_database, args.d4_database_sha256)):
            ap.error("D4 requires --d4-services-dir, --d4-database and --d4-database-sha256 together")
        if args.d3_services_dir is None or not args.tsr_experiment:
            ap.error("D4 requires --d3-services-dir and --tsr-experiment")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", args.d4_database_sha256):
            ap.error("D4 database needs an exact 64-hex SHA256 pin")
        try:
            services = args.d4_services_dir
            if has_symlink(services) or not services.is_dir():
                raise ValueError("D4 services must be a nonsymlink directory")
            if {p.name for p in services.iterdir()} != {"c2m-signs", "d4_boot.sh"}:
                raise ValueError("D4 services must contain exactly c2m-signs and d4_boot.sh")
            for name in ("c2m-signs", "d4_boot.sh"):
                source = services / name
                if has_symlink(source) or not source.is_file():
                    raise ValueError(f"missing/nonregular D4 service {name}")
                data = source.read_bytes()
                if name.endswith(".sh"):
                    if b"\r" in data or not data.startswith(b"#!/bin/sh\n"):
                        raise ValueError("D4 shell must be LF: d4_boot.sh")
                elif (len(data) < 52 or data[:6] != b"\x7fELF\x01\x01"
                      or int.from_bytes(data[18:20], "little") != 40):
                    raise ValueError("D4 service must be ELF32 little-endian ARM: c2m-signs")
                d4_assets[name] = data
            database = args.d4_database
            if has_symlink(database) or not database.is_file():
                raise ValueError("D4 database must be a nonsymlink regular file")
            if database.stat().st_size > D4_MAX_BYTES:
                raise ValueError("D4 database exceeds size bound")
            with database.open("rb") as stream:
                data = stream.read(D4_MAX_BYTES + 1)
            d4_database = check_d4_database(data, args.d4_database_sha256)
            if len(data) > D4_MAX_OUTPUT_BYTES:
                raise ValueError("D4 database exceeds private subset output bound")
            d4_assets["signs-d4.bin"] = data
        except OSError:
            ap.error("cannot read D4 inputs")
        except ValueError as exc:
            ap.error(str(exc))

    d3_assets: dict[str, bytes] = {}
    if args.d3_services_dir is not None:
        if not args.tsr_experiment:
            ap.error("D3 requires --tsr-experiment, not legacy C patch")
        for name in ("boot.sh", "connectivity_probe.sh", "c2m-web", "c2m-wifi", "wpa_supplicant"):
            source = args.d3_services_dir / name
            if not source.is_file() or has_symlink(source):
                ap.error(f"missing/nonregular D3 service {name}")
            data = source.read_bytes()
            if name.endswith(".sh"):
                if b"\r" in data or not data.startswith(b"#!/bin/sh\n"):
                    ap.error(f"D3 shell must be LF: {name}")
            elif (len(data) < 52 or data[:6] != b"\x7fELF\x01\x01"
                  or int.from_bytes(data[18:20], "little") != 40):
                ap.error(f"D3 service must be ELF32 little-endian ARM: {name}")
            d3_assets[name] = data

    debug_assets: dict[str, bytes] = {}
    debug_owner_bytes = b""
    debug_owner = None
    if any(value is not None for value in
           (args.debug_services_dir, args.debug_owner_key, args.debug_owner_key_sha256)):
        if any(value is None for value in
               (args.debug_services_dir, args.debug_owner_key, args.debug_owner_key_sha256)):
            ap.error("Debug requires --debug-services-dir, --debug-owner-key "
                     "and --debug-owner-key-sha256 together")
        if args.d3_services_dir is None or not args.tsr_experiment:
            ap.error("Debug requires --d3-services-dir and --tsr-experiment")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", args.debug_owner_key_sha256 or ""):
            ap.error("Debug owner key needs an exact 64-hex SHA256 pin")
        try:
            services = args.debug_services_dir
            if has_symlink(services) or not services.is_dir():
                raise ValueError("Debug services must be a nonsymlink directory")
            if {p.name for p in services.iterdir()} != set(DEBUG_NAMES):
                raise ValueError("Debug services must contain exactly c2m-debug, "
                                 "dropbear, dropbearkey and debug_boot.sh")
            for name in DEBUG_NAMES:
                source = services / name
                if has_symlink(source) or not source.is_file():
                    raise ValueError(f"missing/nonregular debug service {name}")
                if source.stat().st_size == 0:
                    raise ValueError(f"empty debug service {name}")
                data = source.read_bytes()
                if name.endswith(".sh"):
                    if len(data) > DEBUG_MAX_SHELL:
                        raise ValueError("debug shell exceeds size bound: debug_boot.sh")
                    if b"\r" in data or not data.startswith(b"#!/bin/sh\n"):
                        raise ValueError("debug shell must be LF: debug_boot.sh")
                else:
                    bound = (DEBUG_MAX_SUPERVISOR if name == "c2m-debug"
                             else DEBUG_MAX_DROPBEAR)
                    if len(data) > bound:
                        raise ValueError(f"debug service exceeds size bound: {name}")
                    if (len(data) < 52 or data[:6] != b"\x7fELF\x01\x01"
                            or int.from_bytes(data[18:20], "little") != 40):
                        raise ValueError(
                            f"debug service must be ELF32 little-endian ARM: {name}")
                debug_assets[name] = data
            key_path = args.debug_owner_key
            if has_symlink(key_path) or not key_path.is_file():
                raise ValueError("Debug owner key must be a nonsymlink regular file")
            if key_path.stat().st_size > DEBUG_OWNER_MAX_BYTES:
                raise ValueError("invalid debug owner key length")
            with key_path.open("rb") as stream:
                key_data = stream.read(DEBUG_OWNER_MAX_BYTES + 1)
            debug_owner = check_debug_owner_key(key_data, args.debug_owner_key_sha256)
            debug_owner_bytes = key_data
            debug_assets["debug_owner.pub"] = key_data
        except OSError:
            ap.error("cannot read Debug inputs")
        except ValueError as exc:
            ap.error(str(exc))

    stock = {r["path"]: r for r in
             json.loads(args.manifest.read_text(encoding="utf-8"))["entries"]}
    hook_rel = args.hook.lstrip("/")
    if (not hook_rel or any(part in ("", ".", "..") for part in hook_rel.split("/"))
            or "\\" in hook_rel or ":" in hook_rel or Path(hook_rel).is_absolute()):
        print("MUTATE-FAIL: invalid image-relative hook path")
        return 1
    hook_img_path = "/" + hook_rel
    if hook_img_path not in stock or stock[hook_img_path]["type"] != "reg":
        print(f"MUTATE-FAIL: hook {hook_img_path} not a stock regular file")
        return 1

    hook = args.tree / hook_rel
    if has_symlink(hook):
        print("MUTATE-FAIL: linked tree/hook path")
        return 1
    if not hook.is_file() or sha_file(hook) != stock[hook_img_path]["sha256"]:
        print(f"MUTATE-FAIL: hook tree content != stock manifest "
              f"(tree={sha_file(hook) if hook.is_file() else 'MISSING'} "
              f"stock={stock[hook_img_path]['sha256'][:16]}…)")
        return 1
    text = hook.read_bytes().decode("utf-8")  # binary I/O: no platform newline translation
    if "_c2m_rc=" in text or "exit $_c2m_rc" in text:
        print("MUTATE-FAIL: launch block already present (refusing double-repair)")
        return 1
    if args.hook_line in text:
        print("MUTATE-FAIL: launch line already present (refusing double-hook)")
        return 1
    if not text.endswith("\n"):
        print("MUTATE-FAIL: unexpected hook EOF (no trailing newline)")
        return 1
    # The hook runs as an executed script, so any line after a terminal
    # `exit` is unreachable. Insert the launch BEFORE a terminal exit line;
    # only hooks without one keep the legacy EOF append.
    hook_lines = text.split("\n")
    last_idx = len(hook_lines) - 1
    while last_idx >= 0 and hook_lines[last_idx].strip(" \t") == "":
        last_idx -= 1
    last_line = hook_lines[last_idx].strip(" \t") if last_idx >= 0 else ""
    if re.fullmatch(r"exit([ \t]+[^ \t\n].*)?", last_line):
        # Preserve a hardcoded `exit N` verbatim; bare `exit` / `exit $?`
        # mean "the status so far", i.e. the saved `_c2m_rc`.
        tail = "exit $_c2m_rc" if last_line in ("exit", "exit $?") else last_line
        # Daemon output goes to the boot console; detach it so a blocking
        # console can never stall the hook (and test pipes drain at exit).
        cmd = args.hook_line.rstrip()
        if cmd.endswith("&"):
            cmd = cmd[:-1].rstrip()
        # The hook runs seconds after boot, possibly BEFORE the recording
        # card is mounted, while the daemon initializes its SD log stream
        # once at startup (field proof 2026-10-14: START at uptime=6 on the
        # flash card, no logs on later recording-card boots). Wait for the
        # mount bounded (30x2s) inside a backgrounded subshell so the hook
        # itself still exits immediately; a never-mounted card still gets
        # the daemon after the wait expires. Only grep/sleep/$(( )).
        block = ["_c2m_rc=$?"]
        if args.tsr_patch:
            if "c2m_adas_de.tmp" in text:
                print("MUTATE-FAIL: TSR patch already present")
                return 1
            block += TSR_PATCH_LINES
        if args.tsr_experiment:
            block += ["/bin/sh /customer/c2m/tsr_profile_boot.sh >/dev/null 2>&1"]
        block += ["( _c2m_n=0",
                  "while [ $_c2m_n -lt 30 ]; do",
                  "grep -qs ' /mnt/mmc ' /proc/mounts && break",
                  "sleep 2",
                  "_c2m_n=$(($_c2m_n + 1))",
                  "done",
                  cmd + " >/dev/null 2>&1 & ) >/dev/null 2>&1 &",
                  tail]
        if args.tsr_experiment:
            launch_index = next(i for i, line in enumerate(block) if line.startswith(cmd + " >"))
            block[launch_index:launch_index] = [
                "if grep -qs ' /mnt/mmc ' /proc/mounts; then",
                "mkdir -p /mnt/mmc/C2M_DIAG",
                "cp /tmp/c2m_tsr_status.txt /mnt/mmc/C2M_DIAG/tsr-profile-D.txt",
                "fi"]
        if d3_assets:
            launch_index = next(i for i, line in enumerate(block) if line.startswith(cmd + " >"))
            # Keep idle launch as before. D3 boot runs detached AFTER that;
            # neither a probe nor server startup may delay the stock hook.
            # Debug boot runs detached after D3 (and D4 when present) inside
            # the same bounded background mount-wait block; D3 boot is
            # never altered. Standalone D3+debug (no D4) is supported.
            block[launch_index] = cmd + " >/dev/null 2>&1 &"
            boots = ["/bin/sh /customer/c2m/boot.sh >/dev/null 2>&1 &"]
            if d4_assets:
                boots.append("/bin/sh /customer/c2m/d4_boot.sh >/dev/null 2>&1 &")
            if debug_assets:
                boots.append("/bin/sh /customer/c2m/debug_boot.sh >/dev/null 2>&1 &")
            boots[-1] += " ) >/dev/null 2>&1 &"
            block[launch_index + 1:launch_index + 1] = boots
        elif debug_assets:
            print("MUTATE-FAIL: Debug requires D3 services")
            return 1
        new_text = "\n".join(hook_lines[:last_idx] + block + hook_lines[last_idx + 1:])
        mode = "insert-before-terminal-exit"
    else:
        if args.tsr_patch or args.tsr_experiment:
            print("MUTATE-FAIL: TSR requires reachable stock terminal-exit hook shape")
            return 1
        new_text = text + args.hook_line + "\n"
        mode = "append-eof"

    # Stage all inputs and check every new destination before tree mutation,
    # including legacy idle/profile/D3/D4/debug inputs when combined.
    idle = args.tree / "c2m" / "c2m-idle"
    profile_path = None
    try:
        if not args.idle_bin.is_file() or has_symlink(args.idle_bin):
            raise ValueError("idle input must be a nonsymlink regular file")
        assets = {"c2m-idle": (args.idle_bin.read_bytes(), 0o755)}
        if args.tsr_experiment:
            profile_source = Path(__file__).resolve().parents[2] / "fw/tsr/tsr_profile_boot.sh"
            profile_path = args.tree / "c2m/tsr_profile_boot.sh"
            if has_symlink(profile_source) or not profile_source.is_file():
                raise ValueError("D profile must be a nonsymlink regular file")
            profile_bytes = profile_source.read_bytes()
            if b"\r" in profile_bytes or not profile_bytes.startswith(b"#!/bin/sh\n"):
                raise ValueError("D profile script must be LF shell")
            assets["tsr_profile_boot.sh"] = (profile_bytes, 0o755)
        assets.update({name: (data, 0o755) for name, data in d3_assets.items()})
        assets.update({name: (data, D4_MODES[name]) for name, data in d4_assets.items()})
        assets.update({name: (data, DEBUG_MODES[name]) for name, data in debug_assets.items()})
        if has_symlink(idle.parent) or (idle.parent.exists() and not idle.parent.is_dir()):
            raise ValueError("c2m must be a nonsymlink directory")
        for name in assets:
            dest = idle.parent / name
            if dest.exists() or dest.is_symlink() or "/c2m/" + name in stock:
                raise ValueError(f"existing asset path c2m/{name}")
        if d4_assets or debug_assets:
            report = args.out_manifest
            if (has_symlink(report) or report.exists() or not report.parent.is_dir()
                    or report.resolve().is_relative_to(args.tree.resolve())):
                raise ValueError("D4/debug report must be a new path outside the tree")
    except OSError:
        print("MUTATE-FAIL: cannot read mutation inputs")
        return 1
    except ValueError as exc:
        print(f"MUTATE-FAIL: {exc}")
        return 1

    replaced: dict[str, dict] = {}
    audio_writes: list[tuple[Path, bytes, int]] = []
    if args.audio_replacements is not None:
        try:
            specs = json.loads(args.audio_replacements.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"MUTATE-FAIL: bad audio replacements JSON: {exc}")
            return 1
        if not isinstance(specs, list) or not specs:
            print("MUTATE-FAIL: audio replacements must be a non-empty list")
            return 1
        md5_rel = "minieye/adas/md5sum.txt"
        md5_img_path = "/minieye/adas/md5sum.txt"
        if md5_img_path not in stock or stock[md5_img_path]["type"] != "reg":
            print("MUTATE-FAIL: md5sum.txt not a stock regular file")
            return 1
        md5_file = args.tree / md5_rel
        if not md5_file.is_file() or has_symlink(md5_file):
            print("MUTATE-FAIL: md5sum.txt missing/linked in tree")
            return 1
        md5_text = md5_file.read_bytes().decode("ascii")
        if hashlib.sha256(md5_text.encode("ascii")).hexdigest() != stock[md5_img_path]["sha256"]:
            print("MUTATE-FAIL: md5sum.txt tree content != stock manifest")
            return 1
        md5_lines = md5_text.split("\n")
        seen: set[str] = set()
        # Validate all specs first (fail before touching the tree), then
        # apply existing-file swaps before additions so a new file always
        # finds a sibling wav for its mode.
        for spec in specs:
            if not isinstance(spec, dict):
                print("MUTATE-FAIL: audio spec must be an object")
                return 1
            img_path, local = spec.get("path"), spec.get("file")
            if (not isinstance(img_path, str) or not isinstance(local, str)
                    or not local or not img_path.startswith("/minieye/adas/")):
                print("MUTATE-FAIL: bad audio spec/outside /minieye/adas")
                return 1
            rel = img_path[len("/minieye/adas/"):]
            if (any(part in ("", ".", "..") for part in rel.split("/"))
                    or "\\" in rel or ":" in rel):
                print("MUTATE-FAIL: invalid audio target path")
                return 1
            if img_path in seen:
                print(f"MUTATE-FAIL: duplicate audio target: {img_path}")
                return 1
            seen.add(img_path)

        def _spec_key(spec: dict) -> tuple[int, str]:
            rel = spec["path"].split("/minieye/adas/", 1)[1] \
                if "/minieye/adas/" in spec["path"] else spec["path"]
            return (0 if (args.tree / "minieye/adas" / rel).is_file() else 1,
                    spec["path"])

        for spec in sorted(specs, key=_spec_key):
            img_path, local = spec["path"], spec["file"]
            try:
                source = Path(local)
                if has_symlink(source) or not source.is_file():
                    raise OSError("not a nonsymlink regular file")
                wav = source.read_bytes()
            except OSError:
                print("MUTATE-FAIL: cannot read audio input")
                return 1
            try:
                check_wav(wav, img_path)
            except ValueError as exc:
                print(f"MUTATE-FAIL: {exc}")
                return 1
            if "/minieye/adas/" not in img_path:
                print(f"MUTATE-FAIL: audio outside /minieye/adas: {img_path}")
                return 1
            # md5sum.txt lines are bindir-relative ("  ./audios/A.wav").
            rel = img_path.split("/minieye/adas/", 1)[1]
            want_suffix = "  ./" + rel
            hits = [i for i, ln in enumerate(md5_lines) if ln.endswith(want_suffix)]
            if len(hits) != 1:
                print(f"MUTATE-FAIL: md5sum.txt has {len(hits)} lines for {rel}")
                return 1
            target = args.tree / "minieye/adas" / rel
            if has_symlink(target) or (target.exists() and not target.is_file()):
                print("MUTATE-FAIL: linked/nonregular audio target")
                return 1
            if target.is_file():
                if img_path not in stock or stock[img_path]["type"] != "reg":
                    print(f"MUTATE-FAIL: {img_path} not a stock regular file")
                    return 1
                old_bytes = target.read_bytes()
                if hashlib.sha256(old_bytes).hexdigest() != stock[img_path]["sha256"]:
                    print(f"MUTATE-FAIL: tree {img_path} != stock manifest")
                    return 1
                old_sha = stock[img_path]["sha256"]
                old_size = stock[img_path]["size"]
                target_mode = stat.S_IMODE(target.stat().st_mode)
            else:
                # md5sum-listed but absent from the image (e.g. tlr wav):
                # create with a sibling wav's mode.
                sibs = sorted(target.parent.glob("*.wav")) if target.parent.is_dir() else []
                sib = next((s for s in sibs if s.is_file() and not has_symlink(s)), None)
                if sib is None:
                    print("MUTATE-FAIL: no sibling wav for new-file mode")
                    return 1
                target_mode = stat.S_IMODE(sib.stat().st_mode)
                old_sha, old_size = "(absent-in-image)", 0
            audio_writes.append((target, wav, target_mode))
            md5_lines[hits[0]] = md5_bytes(wav) + md5_lines[hits[0]][32:]
            replaced[img_path] = {"old_sha256": old_sha, "old_size": old_size,
                                  "new_sha256": hashlib.sha256(wav).hexdigest(),
                                  "new_size": len(wav)}
        new_md5 = "\n".join(md5_lines)
        if not new_md5.endswith("\n"):
            print("MUTATE-FAIL: md5sum.txt lost trailing newline")
            return 1
        audio_writes.append((md5_file, new_md5.encode("ascii"),
                             stat.S_IMODE(md5_file.stat().st_mode)))
        replaced[md5_img_path] = {
            "old_sha256": stock[md5_img_path]["sha256"],
            "old_size": stock[md5_img_path]["size"],
            "new_sha256": hashlib.sha256(new_md5.encode("ascii")).hexdigest(),
            "new_size": len(new_md5)}

    # Validation is complete. Only explicit allowlisted assets are installed;
    # ownership is set to stock 1001:1001 by rebuild_customer.sh, not host chown.
    idle.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(idle.parent, 0o755)
    for name, (data, asset_mode) in assets.items():
        dest = idle.parent / name
        with dest.open("xb") as stream:
            stream.write(data)
        os.chmod(dest, asset_mode)
    for target, data, target_mode in audio_writes:
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
        else:
            target.write_bytes(data)
        os.chmod(target, target_mode)
    hook.write_bytes(new_text.encode("utf-8"))

    d3_added = [{"path": "/c2m/" + name, "type": "reg", "mode": 0o755,
                 "mode_oct": "0o755", "size": len(data),
                 "sha256": hashlib.sha256(data).hexdigest()}
                for name, data in d3_assets.items()]
    d4_added = [{"path": "/c2m/" + name, "type": "reg", "mode": D4_MODES[name],
                 "mode_oct": oct(D4_MODES[name]), "uid": 1001, "gid": 1001,
                 "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                for name, data in d4_assets.items()]
    debug_added = [{"path": "/c2m/" + name, "type": "reg", "mode": DEBUG_MODES[name],
                    "mode_oct": oct(DEBUG_MODES[name]), "uid": 1001, "gid": 1001,
                    "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                   for name, data in debug_assets.items()]
    doc = {"hook": hook_img_path,
           "hook_line": args.hook_line,
           "hook_mode": mode,
           "tsr_patch": bool(args.tsr_patch),
           "tsr_experiment": bool(args.tsr_experiment),
           "added": [{"path": "/c2m", "type": "dir",
                      "mode": 0o755, "mode_oct": "0o755",
                      "uid": 1001, "gid": 1001},
                     {"path": "/c2m/c2m-idle", "type": "reg",
                      "mode": 0o755, "mode_oct": "0o755",
                      "size": idle.stat().st_size,
                      "sha256": sha_file(idle)}],
           "replaced": replaced,
           "modified": [{"path": hook_img_path,
                         "old_sha256": stock[hook_img_path]["sha256"],
                         "new_sha256": sha_file(hook),
                         "change": f"{mode} {len(new_text) - len(text)} bytes"}]}
    if profile_path is not None:
        doc["added"].append({"path": "/c2m/tsr_profile_boot.sh", "type": "reg",
                             "mode": 0o755, "mode_oct": "0o755",
                             "size": profile_path.stat().st_size,
                             "sha256": sha_file(profile_path)})
    if d3_added:
        doc["d3_services"] = True
        doc["added"].extend(d3_added)
    if d4_added:
        doc["d4_services"] = True
        doc["d4_database"] = d4_database
        doc["added"].extend(d4_added)
    if debug_added:
        doc["debug_services"] = True
        doc["debug_owner_key_sha256"] = debug_owner["sha256"]
        doc["added"].extend(debug_added)
    if d4_added or debug_added:
        with args.out_manifest.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(doc, indent=2))
    else:
        args.out_manifest.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(json.dumps(doc, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
