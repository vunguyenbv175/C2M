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
import os
import re
from pathlib import Path

DEFAULT_HOOK_LINE = "/customer/c2m/c2m-idle &"


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def md5_bytes(d: bytes) -> str:
    return hashlib.md5(d).hexdigest()


# Stock ADAS warning encoding (checked on adas_activated.wav: RIFF/WAVE,
# PCM16, mono, 24000 Hz). Replacements with any other encoding are BLOCKED:
# the on-device player path is reverse-engineered, not negotiated.
def check_wav(data: bytes, what: str) -> None:
    if not (len(data) > 44 and data[0:4] == b"RIFF" and data[8:12] == b"WAVE"):
        raise ValueError(f"wav rejected (not RIFF/WAVE): {what}")
    import struct
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
    ap.add_argument("--out-manifest", type=Path, required=True)
    args = ap.parse_args()

    d3_assets: dict[str, bytes] = {}
    if args.d3_services_dir is not None:
        if not args.tsr_experiment:
            ap.error("D3 requires --tsr-experiment, not legacy C patch")
        for name in ("boot.sh", "connectivity_probe.sh", "c2m-web", "c2m-wifi", "wpa_supplicant"):
            source = args.d3_services_dir / name
            if not source.is_file() or source.is_symlink():
                ap.error(f"missing/nonregular D3 service {name}")
            data = source.read_bytes()
            if name.endswith(".sh"):
                if b"\r" in data or not data.startswith(b"#!/bin/sh\n"):
                    ap.error(f"D3 shell must be LF: {name}")
            elif (len(data) < 52 or data[:6] != b"\x7fELF\x01\x01"
                  or int.from_bytes(data[18:20], "little") != 40):
                ap.error(f"D3 service must be ELF32 little-endian ARM: {name}")
            d3_assets[name] = data

    stock = {r["path"]: r for r in
             json.loads(args.manifest.read_text(encoding="utf-8"))["entries"]}
    hook_rel = args.hook.lstrip("/")
    hook_img_path = "/" + hook_rel
    if hook_img_path not in stock or stock[hook_img_path]["type"] != "reg":
        print(f"MUTATE-FAIL: hook {hook_img_path} not a stock regular file")
        return 1

    hook = args.tree / hook_rel
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
            block[launch_index] = cmd + " >/dev/null 2>&1 &"
            block[launch_index + 1:launch_index + 1] = [
                "/bin/sh /customer/c2m/boot.sh >/dev/null 2>&1 & ) >/dev/null 2>&1 &"]
        new_text = "\n".join(hook_lines[:last_idx] + block + hook_lines[last_idx + 1:])
        mode = "insert-before-terminal-exit"
    else:
        if args.tsr_patch or args.tsr_experiment:
            print("MUTATE-FAIL: TSR requires reachable stock terminal-exit hook shape")
            return 1
        new_text = text + args.hook_line + "\n"
        mode = "append-eof"

    idle = args.tree / "c2m" / "c2m-idle"
    if idle.exists():
        print("MUTATE-FAIL: c2m/c2m-idle already exists in tree")
        return 1
    idle.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(idle.parent, 0o755)
    idle.write_bytes(args.idle_bin.read_bytes())
    os.chmod(idle, 0o755)

    profile_path = None
    if args.tsr_experiment:
        profile_source = Path(__file__).resolve().parents[2] / "fw/tsr/tsr_profile_boot.sh"
        profile_path = args.tree / "c2m/tsr_profile_boot.sh"
        profile_bytes = profile_source.read_bytes()
        if b"\r" in profile_bytes or not profile_bytes.startswith(b"#!/bin/sh\n"):
            print("MUTATE-FAIL: D profile script must be LF shell")
            return 1
        profile_path.write_bytes(profile_bytes)
        os.chmod(profile_path, 0o755)

    d3_added = []
    for name, data in d3_assets.items():
        dest = args.tree / "c2m" / name
        if dest.exists() or dest.is_symlink():
            print(f"MUTATE-FAIL: existing D3 path {name}")
            return 1
        dest.write_bytes(data)
        os.chmod(dest, 0o755)
        d3_added.append({"path": "/c2m/" + name, "type": "reg", "mode": 0o755,
                         "mode_oct": "0o755", "size": len(data),
                         "sha256": hashlib.sha256(data).hexdigest()})

    replaced: dict[str, dict] = {}
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
        if not md5_file.is_file():
            print("MUTATE-FAIL: md5sum.txt missing in tree")
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
            if not img_path or not local or not img_path.startswith("/"):
                print(f"MUTATE-FAIL: bad audio spec: {spec!r}")
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
                wav = Path(local).read_bytes()
            except OSError as exc:
                print(f"MUTATE-FAIL: cannot read {local}: {exc}")
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
            else:
                # md5sum-listed but absent from the image (e.g. tlr wav):
                # create with a sibling wav's mode.
                sibs = sorted(target.parent.glob("*.wav")) if target.parent.is_dir() else []
                sib = next((s for s in sibs if s.is_file()), None)
                if sib is None:
                    print("MUTATE-FAIL: no sibling wav for new-file mode")
                    return 1
                import stat as _stat
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
                os.chmod(target, _stat.S_IMODE(os.stat(sib).st_mode))
                old_sha, old_size = "(absent-in-image)", 0
            target.write_bytes(wav)
            md5_lines[hits[0]] = md5_bytes(wav) + md5_lines[hits[0]][32:]
            replaced[img_path] = {"old_sha256": old_sha, "old_size": old_size,
                                  "new_sha256": hashlib.sha256(wav).hexdigest(),
                                  "new_size": len(wav)}
        new_md5 = "\n".join(md5_lines)
        if not new_md5.endswith("\n"):
            print("MUTATE-FAIL: md5sum.txt lost trailing newline")
            return 1
        md5_file.write_bytes(new_md5.encode("ascii"))
        replaced[md5_img_path] = {
            "old_sha256": stock[md5_img_path]["sha256"],
            "old_size": stock[md5_img_path]["size"],
            "new_sha256": hashlib.sha256(new_md5.encode("ascii")).hexdigest(),
            "new_size": len(new_md5)}

    hook.write_bytes(new_text.encode("utf-8"))

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
    args.out_manifest.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(json.dumps(doc, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
