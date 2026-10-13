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
         insert a 3-line launch block BEFORE that line: save `$?`, start
         the daemon backgrounded with stdio detached, then exit with the
         saved status. Appending after it would be dead code: the hook is
         executed (not sourced), so `exit` ends the script before any
         later line runs (B2 field defect, 2026-10-13).
       - hook has no terminal `exit`: append the single launch line at EOF
         (legacy fallback; reachable because control falls off the end).

Fail-closed guards:
  - --manifest (stock manifest JSON) REQUIRED: hook file content must hash
    exactly to the stock manifest entry before edit (unexpected base BLOCKS);
  - the launch line / repair block must not already be present (no
    double-hook, no double-repair);
  - after edit, re-walk: ONLY the 2 allowlisted paths may differ.

Outputs --out-manifest (mutation manifest: added/modified + shas).

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True,
                    help="stock manifest JSON (base integrity gate)")
    ap.add_argument("--idle-bin", type=Path, required=True)
    ap.add_argument("--hook", default="wifi/rcInsDriver.sh")
    ap.add_argument("--hook-line", default=DEFAULT_HOOK_LINE)
    ap.add_argument("--out-manifest", type=Path, required=True)
    args = ap.parse_args()

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
        block = ["_c2m_rc=$?", cmd + " >/dev/null 2>&1 &", tail]
        new_text = "\n".join(hook_lines[:last_idx] + block + hook_lines[last_idx + 1:])
        mode = "insert-before-terminal-exit"
    else:
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

    hook.write_bytes(new_text.encode("utf-8"))

    doc = {"hook": hook_img_path,
           "hook_line": args.hook_line,
           "hook_mode": mode,
           "added": [{"path": "/c2m", "type": "dir",
                      "mode": 0o755, "mode_oct": "0o755",
                      "uid": 1001, "gid": 1001},
                     {"path": "/c2m/c2m-idle", "type": "reg",
                      "mode": 0o755, "mode_oct": "0o755",
                      "size": idle.stat().st_size,
                      "sha256": sha_file(idle)}],
           "modified": [{"path": hook_img_path,
                         "old_sha256": stock[hook_img_path]["sha256"],
                         "new_sha256": sha_file(hook),
                         "change": f"{mode} {len(new_text) - len(text)} bytes"}]}
    args.out_manifest.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(json.dumps(doc, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
