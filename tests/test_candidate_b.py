#!/usr/bin/env python3
"""Synthetic (no-vendor) tests for the Candidate-B pipeline logic.

Covers, without any firmware:
  - ubifs manifest --compare (identical / content / mode / add / remove);
  - mutate_customer guards (wrong base, double-hook, success shape);
  - verify_b_manifest (OK + violation);
  - candidate_diff allowlist (OK + kernel-tamper + tail + deep verdict);
  - assemble_inner layout mode (round-trip + overlap rejection);
  - tar_assemble golden + package modes on a synthetic TAR.
Run: python3 tests/test_candidate_b.py
"""
from __future__ import annotations
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sh(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_py(tool: str, *argv: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, f"tools/fw/{tool}", *argv],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)[-3000:]


def manifest(entries: list[dict]) -> dict:
    return {"image": "synth", "image_bytes": 1, "node_count": 1,
            "entry_count": len(entries), "entries": entries}


def reg(path: str, data: bytes, mode: int = 0o755, mtime: int = 1691062662) -> dict:
    return {"path": path, "inode": 1, "type": "reg", "mode": mode,
            "mode_oct": oct(mode), "uid": 1001, "gid": 1001,
            "size": len(data), "mtime": mtime, "sha256": sh(data)}


def mini_contract(customer_size: int, cust_off: int, misc_off: int,
                  kernel_sha: str, tail_hex: str = "001122",
                  script_extra: str = "") -> dict:
    fat = (f"fatload mmc 0 0x21000000 $(SdUpgradeImage) {hex(0x100)} 0x4000\n"
           f"fatload mmc 0 0x21000000 $(SdUpgradeImage) {hex(customer_size)} {hex(cust_off)}\n"
           f"fatload mmc 0 0x21000000 $(SdUpgradeImage) {hex(0x200)} {hex(misc_off)}\n")
    ubi = (f"ubi write 0x21000000 customer {hex(customer_size)}\n"
           f"ubi write 0x21000000 misc 0x200\n")
    script = ("# File Partition: kernel.es\n" + fat.splitlines()[0] +
              "\n# File Partition: customer.es\n" + fat.splitlines()[1] +
              "\n# File Partition: misc.es\n" + fat.splitlines()[2] +
              "\n% <- this is end of script symbol" + script_extra)
    return {
        "outer_order": ["SigmastarUpgradeSD_SSC8838G.bin", "sysVer.txt",
                        "minieye_firmware.md5", "adas_upgrade.sh"],
        "outer_members": [
            {"name": "SigmastarUpgradeSD_SSC8838G.bin", "size": 9, "sha256": sh(b"inner")},
            {"name": "sysVer.txt", "size": 3, "sha256": sh(b"sys")},
            {"name": "minieye_firmware.md5", "size": 4, "sha256": sh(b"md5x")},
            {"name": "adas_upgrade.sh", "size": 4, "sha256": sh(b"adas")},
        ],
        "inner_sha256": sh(b"inner"),
        "upgrade_script_text": script,
        "loads": [
            {"section": "kernel.es", "load_index": 0, "offset": 0x4000,
             "end": 0x4100, "size": 0x100, "sha256": kernel_sha, "within_image": True},
            {"section": "customer.es", "load_index": 0, "offset": cust_off,
             "end": cust_off + customer_size, "size": customer_size,
             "sha256": sh(b"c" * customer_size), "within_image": True},
            {"section": "misc.es", "load_index": 0, "offset": misc_off,
             "end": misc_off + 0x200, "size": 0x200,
             "sha256": sh(b"m" * 0x200), "within_image": True},
        ],
        "tail_unknown": {"offset": misc_off + 0x200, "len": 3, "hex": tail_hex},
    }


def main() -> int:
    fails: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # 1. manifest compare
        a = manifest([reg("/f", b"hello"), reg("/g", b"world")])
        (tmp / "a.json").write_text(json.dumps(a))
        (tmp / "b.json").write_text(json.dumps(a))
        rc, _ = run_py("ubifs_manifest.py", "--compare", str(tmp / "a.json"), str(tmp / "b.json"))
        if rc != 0:
            fails.append("manifest identical not OK")
        b2 = manifest([reg("/f", b"HELLO"), reg("/g", b"world")])
        (tmp / "b2.json").write_text(json.dumps(b2))
        rc, out = run_py("ubifs_manifest.py", "--compare", str(tmp / "a.json"), str(tmp / "b2.json"))
        if rc == 0 or "CHANGED /f" not in out:
            fails.append("manifest content diff missed")
        b3 = manifest([reg("/f", b"hello", mode=0o644), reg("/g", b"world")])
        (tmp / "b3.json").write_text(json.dumps(b3))
        rc, _ = run_py("ubifs_manifest.py", "--compare", str(tmp / "a.json"), str(tmp / "b3.json"))
        if rc == 0:
            fails.append("manifest mode diff missed")
        b4 = manifest([reg("/f", b"hello")])
        (tmp / "b4.json").write_text(json.dumps(b4))
        rc, out = run_py("ubifs_manifest.py", "--compare", str(tmp / "a.json"), str(tmp / "b4.json"))
        if rc == 0 or "REMOVED /g" not in out:
            fails.append("manifest removal missed")

        # 2. mutate guards + success
        tree = tmp / "tree"
        (tree / "wifi").mkdir(parents=True)
        hook_bytes = b"#!/bin/sh\necho hi\nsleep 1\n"
        (tree / "wifi" / "rcInsDriver.sh").write_bytes(hook_bytes)
        (tmp / "idle.bin").write_bytes(b"ARMFAKE")
        stock = manifest([dict(reg("/wifi/rcInsDriver.sh", hook_bytes),
                               sha256=sh(hook_bytes),
                               size=len(hook_bytes))])
        (tmp / "stock.json").write_text(json.dumps(stock))
        rc, _ = run_py("mutate_customer.py", "--tree", str(tree),
                       "--manifest", str(tmp / "stock.json"),
                       "--idle-bin", str(tmp / "idle.bin"),
                       "--out-manifest", str(tmp / "mut.json"))
        if rc != 0:
            fails.append("mutate clean tree failed")
        else:
            mut = json.loads((tmp / "mut.json").read_text())
            hook_new = (tree / "wifi" / "rcInsDriver.sh").read_bytes()
            if not hook_new.endswith(b"/customer/c2m/c2m-idle &\n"):
                fails.append("hook line not appended")
            if not (tree / "c2m" / "c2m-idle").is_file():
                fails.append("idle binary not placed")
            # double-hook must fail
            rc, _ = run_py("mutate_customer.py", "--tree", str(tree),
                           "--manifest", str(tmp / "stock.json"),
                           "--idle-bin", str(tmp / "idle.bin"),
                           "--out-manifest", str(tmp / "mut2.json"))
            if rc == 0:
                fails.append("double-hook not rejected")
            # verify_b_manifest OK on actual (dir entry carries no sha by design)
            actual = manifest([
                reg("/wifi/rcInsDriver.sh", hook_new),
                {"path": "/c2m", "inode": 9, "type": "dir", "mode": 0o755,
                 "mode_oct": "0o755", "uid": 1001, "gid": 1001,
                 "size": 96, "mtime": 1691062662},
                reg("/c2m/c2m-idle", b"ARMFAKE", mode=0o755),
            ])
            (tmp / "actual.json").write_text(json.dumps(actual))
            r = subprocess.run(
                [sys.executable, "tools/fw/verify_b_manifest.py", "--stock",
                 str(tmp / "stock.json"), "--mut", str(tmp / "mut.json"),
                 "--actual", str(tmp / "actual.json")],
                cwd=ROOT, capture_output=True, text=True)
            if r.returncode != 0:
                fails.append("verify_b_manifest OK case failed: " + r.stdout[-500:])
            # violation: unexpected extra path
            actual_bad = manifest([
                reg("/wifi/rcInsDriver.sh", hook_new),
                {"path": "/c2m", "inode": 9, "type": "dir", "mode": 0o755,
                 "mode_oct": "0o755", "uid": 1001, "gid": 1001,
                 "size": 96, "mtime": 1691062662},
                reg("/c2m/c2m-idle", b"ARMFAKE", mode=0o755),
                reg("/evil", b"x"),
            ])
            (tmp / "actualbad.json").write_text(json.dumps(actual_bad))
            r = subprocess.run(
                [sys.executable, "tools/fw/verify_b_manifest.py", "--stock",
                 str(tmp / "stock.json"), "--mut", str(tmp / "mut.json"),
                 "--actual", str(tmp / "actualbad.json")],
                cwd=ROOT, capture_output=True, text=True)
            if r.returncode == 0:
                fails.append("verify_b_manifest extra path not BLOCKED")
            # F2 regression: /c2m omitted from the allowlist must BLOCK
            # (this is exactly the shipped-bug shape the review caught).
            mut_nodir = json.loads((tmp / "mut.json").read_text())
            mut_nodir["added"] = [a for a in mut_nodir["added"] if a["path"] != "/c2m"]
            (tmp / "mut_nodir.json").write_text(json.dumps(mut_nodir))
            r = subprocess.run(
                [sys.executable, "tools/fw/verify_b_manifest.py", "--stock",
                 str(tmp / "stock.json"), "--mut", str(tmp / "mut_nodir.json"),
                 "--actual", str(tmp / "actual.json")],
                cwd=ROOT, capture_output=True, text=True)
            if r.returncode == 0 or "UNEXPECTED-PATHS" not in (r.stdout + r.stderr):
                fails.append("missing /c2m from allowlist not BLOCKED")
            # F2 regression: unexpected extra DIRECTORY must BLOCK.
            actual_baddir = manifest(actual["entries"] + [
                {"path": "/c2m/oops", "inode": 10, "type": "dir", "mode": 0o755,
                 "mode_oct": "0o755", "uid": 1001, "gid": 1001,
                 "size": 64, "mtime": 1691062662},
            ])
            (tmp / "actualbaddir.json").write_text(json.dumps(actual_baddir))
            r = subprocess.run(
                [sys.executable, "tools/fw/verify_b_manifest.py", "--stock",
                 str(tmp / "stock.json"), "--mut", str(tmp / "mut.json"),
                 "--actual", str(tmp / "actualbaddir.json")],
                cwd=ROOT, capture_output=True, text=True)
            if r.returncode == 0:
                fails.append("unexpected extra directory not BLOCKED")
        # wrong base manifest must fail
        tree2 = tmp / "tree2"
        (tree2 / "wifi").mkdir(parents=True)
        (tree2 / "wifi" / "rcInsDriver.sh").write_bytes(b"#!/bin/sh\necho EVIL\n")
        rc, _ = run_py("mutate_customer.py", "--tree", str(tree2),
                       "--manifest", str(tmp / "stock.json"),
                       "--idle-bin", str(tmp / "idle.bin"),
                       "--out-manifest", str(tmp / "mut3.json"))
        if rc == 0:
            fails.append("mutate with tampered base not rejected")

        # 2b. terminal-exit hook (stock shape): launch must be INSERTED
        # BEFORE the exit, preserving the exit status. The shipped B2 defect
        # was the launch line AFTER `exit` (dead code — hook is executed,
        # not sourced).
        treeE = tmp / "treeE"
        (treeE / "wifi").mkdir(parents=True)
        exit_hook = b"#!/bin/sh\necho hi\nsleep 1\nexit $?\n"
        (treeE / "wifi" / "rcInsDriver.sh").write_bytes(exit_hook)
        stockE = manifest([dict(reg("/wifi/rcInsDriver.sh", exit_hook),
                                sha256=sh(exit_hook),
                                size=len(exit_hook))])
        (tmp / "stockE.json").write_text(json.dumps(stockE))
        rc, _ = run_py("mutate_customer.py", "--tree", str(treeE),
                       "--manifest", str(tmp / "stockE.json"),
                       "--idle-bin", str(tmp / "idle.bin"),
                       "--out-manifest", str(tmp / "mutE.json"))
        if rc != 0:
            fails.append("mutate terminal-exit hook failed")
        else:
            mutE = json.loads((tmp / "mutE.json").read_text())
            if mutE.get("hook_mode") != "insert-before-terminal-exit":
                fails.append("hook_mode not insert-before-terminal-exit")
            hx = (treeE / "wifi" / "rcInsDriver.sh").read_bytes()
            hxt = hx.decode("ascii")
            stripped = [ln.strip(" \t") for ln in hxt.split("\n")]
            nonempty = [ln for ln in stripped if ln]
            if nonempty[-1] != "exit $_c2m_rc":
                fails.append("repaired hook must end with preserved exit")
            exits = [i for i, ln in enumerate(stripped) if ln.startswith("exit")]
            launches = [i for i, ln in enumerate(stripped)
                        if "/customer/c2m/c2m-idle" in ln]
            if not launches or not exits or max(launches) > min(exits):
                fails.append("launch line not before terminal exit "
                             "(dead-code shape present?)")
            # exact expectation: only the launch block inserted, stock
            # bytes otherwise identical
            want = (exit_hook.decode().rsplit("exit $?\n", 1)[0]
                    + "_c2m_rc=$?\n"
                      "( _c2m_n=0\n"
                      "while [ $_c2m_n -lt 30 ]; do\n"
                      "grep -qs ' /mnt/mmc ' /proc/mounts && break\n"
                      "sleep 2\n"
                      "_c2m_n=$(($_c2m_n + 1))\n"
                      "done\n"
                      "/customer/c2m/c2m-idle >/dev/null 2>&1 & ) >/dev/null 2>&1 &\n"
                      "exit $_c2m_rc\n")
            if hxt != want:
                fails.append("repaired hook bytes differ beyond inserted block")
            # double-repair (manifest pinned to repaired hook) must fail
            stockE2 = manifest([dict(reg("/wifi/rcInsDriver.sh", hx),
                                     sha256=sh(hx), size=len(hx))])
            (tmp / "stockE2.json").write_text(json.dumps(stockE2))
            rc, out = run_py("mutate_customer.py", "--tree", str(treeE),
                             "--manifest", str(tmp / "stockE2.json"),
                             "--idle-bin", str(tmp / "idle.bin"),
                             "--out-manifest", str(tmp / "mutE2.json"))
            if rc == 0 or "double-repair" not in out:
                fails.append("double-repair not rejected")

        # 2c. the repaired hook must actually EXECUTE the launch (the old
        # shape never ran it): run mutated hooks under sh with a fake
        # daemon, check exit-status preservation, backgrounding (no
        # foreground wait) and failure isolation (missing binary).
        def await_file(path: Path, timeout: float = 5.0) -> bool:
            # Background launch is asynchronous by design: poll instead
            # of asserting immediacy (no sleep in the hook itself).
            start = time.monotonic()
            while time.monotonic() - start < timeout:
                if path.is_file():
                    return True
                time.sleep(0.1)
            return False

        def sh_path(path: Path) -> str:
            # MSYS/Git sh splits PATH on ':' too, so a 'C:/...' entry would
            # shatter into garbage: use the '/c/...' form inside sh.
            s = path.as_posix()
            if len(s) > 2 and s[1] == ":":
                s = "/" + s[0].lower() + s[2:]
            return s

        def run_hook(sh_bin: str, hook_path: Path, stubdir: Path):
            # Git/MSYS sh prefers its own /usr/bin over inherited PATH, so
            # stubs for stock tool names (sleep/grep) must take precedence
            # via an INNER export; unique stub names need no such help.
            # Device behavior is unchanged (fixed command names either way).
            cmd = ("export PATH='%s:$PATH'; exec '%s'"
                   % (sh_path(stubdir), sh_path(hook_path)))
            return subprocess.run([sh_bin, "-c", cmd], capture_output=True,
                                  text=True, timeout=30)

        sh_bin = shutil.which("sh")
        if not sh_bin:
            fails.append("sh missing for hook execution test")
        else:
            execdir = tmp / "exec"
            execdir.mkdir()
            # Stubs: instant sleep + never-mounted card, so the bounded
            # mount wait expires in milliseconds on the test machine.
            wstub = execdir / "wstub"
            wstub.mkdir()
            (wstub / "sleep").write_text("#!/bin/sh\nexit 0\n")
            (wstub / "grep").write_text("#!/bin/sh\nexit 1\n")
            os.chmod(wstub / "sleep", 0o755)
            os.chmod(wstub / "grep", 0o755)
            sentinel = execdir / "launched"
            fake = execdir / "fake-idle"
            fake.write_text("#!/bin/sh\necho launched > \"%s\"\nsleep 20\n"
                            % sentinel.as_posix())
            os.chmod(fake, 0o755)
            for code, tail in ((0, "exit 0\n"), (3, "exit 3\n")):
                hx_tree = execdir / f"hx{code}"
                (hx_tree / "wifi").mkdir(parents=True)
                sbytes = ("#!/bin/sh\necho hi\n" + tail).encode()
                (hx_tree / "wifi" / "rcInsDriver.sh").write_bytes(sbytes)
                sm = manifest([dict(reg("/wifi/rcInsDriver.sh", sbytes),
                                     sha256=sh(sbytes), size=len(sbytes))])
                (execdir / f"stock{code}.json").write_text(json.dumps(sm))
                rc, out = run_py(
                    "mutate_customer.py", "--tree", str(hx_tree),
                    "--manifest", str(execdir / f"stock{code}.json"),
                    "--idle-bin", str(tmp / "idle.bin"),
                    "--hook-line", fake.as_posix() + " &",
                    "--out-manifest", str(execdir / f"m{code}.json"))
                if rc != 0:
                    fails.append(f"mutate exec hook code={code} failed")
                    continue
                if sentinel.exists():
                    sentinel.unlink()
                t0 = time.monotonic()
                try:
                    r = run_hook(sh_bin, hx_tree / "wifi" / "rcInsDriver.sh",
                                 wstub)
                except subprocess.TimeoutExpired:
                    fails.append(f"hook code={code} hung (launch foregrounded?)")
                    continue
                dt = time.monotonic() - t0
                if r.returncode != code:
                    fails.append(f"hook exit {r.returncode} != stock {code}")
                if not await_file(sentinel):
                    fails.append(f"background launch did not run (code={code})")
                if dt >= 10:
                    fails.append(f"hook blocked on launch ({dt:.1f}s)")
            # missing binary: stock status must survive, hook must not hang
            hx_tree = execdir / "hxmiss"
            (hx_tree / "wifi").mkdir(parents=True)
            sbytes = b"#!/bin/sh\necho hi\nexit 0\n"
            (hx_tree / "wifi" / "rcInsDriver.sh").write_bytes(sbytes)
            sm = manifest([dict(reg("/wifi/rcInsDriver.sh", sbytes),
                                 sha256=sh(sbytes), size=len(sbytes))])
            (execdir / "stockmiss.json").write_text(json.dumps(sm))
            rc, _ = run_py(
                "mutate_customer.py", "--tree", str(hx_tree),
                "--manifest", str(execdir / "stockmiss.json"),
                "--idle-bin", str(tmp / "idle.bin"),
                "--hook-line", (execdir / "no-such-binary").as_posix() + " &",
                "--out-manifest", str(execdir / "mmiss.json"))
            if rc != 0:
                fails.append("mutate missing-binary hook failed")
            else:
                try:
                    r = run_hook(sh_bin, hx_tree / "wifi" / "rcInsDriver.sh",
                                 wstub)
                except subprocess.TimeoutExpired:
                    fails.append("missing-binary hook hung")
                    r = None
                if r is not None and r.returncode != 0:
                    fails.append("missing binary changed hook exit status")

        # 2d. stock Wi-Fi-OFF branch shape: stub nvconf to report Wi-Fi
        # disabled; the repaired hook must still launch the daemon and
        # exit with the stock status.
        if sh_bin is None:
            fails.append("sh missing for wifi-branch execution test")
        else:
            stubdir = tmp / "stubbin"
            stubdir.mkdir()
            (stubdir / "nvconf").write_text("#!/bin/sh\necho 0\n")
            (stubdir / "sleep").write_text("#!/bin/sh\nexit 0\n")
            (stubdir / "grep").write_text("#!/bin/sh\nexit 1\n")
            os.chmod(stubdir / "nvconf", 0o755)
            os.chmod(stubdir / "sleep", 0o755)
            os.chmod(stubdir / "grep", 0o755)
            sentinel_b = tmp / "launched_off"
            fake_b = tmp / "fake-idle-off"
            fake_b.write_text("#!/bin/sh\necho launched > \"%s\"\n"
                              % sentinel_b.as_posix())
            os.chmod(fake_b, 0o755)
            off_hook = (b"#!/bin/sh\n"
                        b"WIFIFUNC=`nvconf get 0 Camera.Menu.WifiConf`\n"
                        b"if [ $WIFIFUNC = \"0\" ]; then\n"
                        b"echo \"wifi disable by default.\"\n"
                        b"else\n"
                        b"echo \"wifi on (unstubbed path)\"\n"
                        b"fi\n"
                        b"exit $?\n")
            treeO = tmp / "treeO"
            (treeO / "wifi").mkdir(parents=True)
            (treeO / "wifi" / "rcInsDriver.sh").write_bytes(off_hook)
            stockO = manifest([dict(reg("/wifi/rcInsDriver.sh", off_hook),
                                     sha256=sh(off_hook),
                                     size=len(off_hook))])
            (tmp / "stockO.json").write_text(json.dumps(stockO))
            rc, out = run_py(
                "mutate_customer.py", "--tree", str(treeO),
                "--manifest", str(tmp / "stockO.json"),
                "--idle-bin", str(tmp / "idle.bin"),
                "--hook-line", fake_b.as_posix() + " &",
                "--out-manifest", str(tmp / "mutO.json"))
            if rc != 0:
                fails.append("mutate wifi-off hook failed")
            else:
                try:
                    r = run_hook(sh_bin, treeO / "wifi" / "rcInsDriver.sh",
                                 stubdir)
                except subprocess.TimeoutExpired:
                    fails.append("wifi-off hook hung")
                    r = None
                if r is not None:
                    if r.returncode != 0:
                        fails.append("wifi-off hook exit != stock 0")
                    if not await_file(sentinel_b):
                        fails.append("wifi-off branch did not launch daemon")

        # 2e. mount-gated launch: the daemon must start only AFTER the
        # /mnt/mmc mount appears, but must still start when it never does
        # (bounded wait, never gates the daemon forever).
        if sh_bin is None:
            fails.append("sh missing for mount-wait execution test")
        else:
            mdir = tmp / "mountwait"
            mdir.mkdir()
            # NOTE: the inner PATH export mangles the inherited Windows
            # PATH (drive-letter colons), so stubs must use shell builtins
            # ONLY (no wc/cat/ls). The poll counter is a token dir:
            # one empty file per grep call, counted via glob + $#.
            tokens = mdir / "tokens"
            tokens.mkdir()
            sent_m = mdir / "sent_mounted"
            fake_m = mdir / "fake-idle"
            fake_m.write_text("#!/bin/sh\nset -- \"%s\"/*\n"
                              "[ -e \"$1\" ] && echo $# > \"%s\"\n"
                              % (tokens.as_posix(), sent_m.as_posix()))
            os.chmod(fake_m, 0o755)
            mstub = mdir / "mstub"
            mstub.mkdir()
            # grep stub: mount "appears" on the 3rd poll.
            (mstub / "grep").write_text(
                "#!/bin/sh\ni=0\n"
                "while [ -e \"%s/$i\" ]; do i=$((i + 1)); done\n"
                ": > \"%s/$i\"\n"
                "[ \"$i\" -ge 2 ]\n" % (tokens.as_posix(),
                                        tokens.as_posix()))
            (mstub / "sleep").write_text("#!/bin/sh\nexit 0\n")
            os.chmod(mstub / "grep", 0o755)
            os.chmod(mstub / "sleep", 0o755)
            mtree = mdir / "hx"
            (mtree / "wifi").mkdir(parents=True)
            mbytes = b"#!/bin/sh\nexit 0\n"
            (mtree / "wifi" / "rcInsDriver.sh").write_bytes(mbytes)
            mm = manifest([dict(reg("/wifi/rcInsDriver.sh", mbytes),
                                 sha256=sh(mbytes), size=len(mbytes))])
            (mdir / "stockm.json").write_text(json.dumps(mm))
            rc, _ = run_py(
                "mutate_customer.py", "--tree", str(mtree),
                "--manifest", str(mdir / "stockm.json"),
                "--idle-bin", str(tmp / "idle.bin"),
                "--hook-line", fake_m.as_posix() + " &",
                "--out-manifest", str(mdir / "mm.json"))
            if rc != 0:
                fails.append("mutate mount-wait hook failed")
            else:
                t0 = time.monotonic()
                r = run_hook(sh_bin, mtree / "wifi" / "rcInsDriver.sh", mstub)
                dt = time.monotonic() - t0
                if r.returncode != 0:
                    fails.append("mount-wait hook exit != 0")
                if dt >= 10:
                    fails.append(f"mount-wait hook blocked ({dt:.1f}s)")
                if not await_file(sent_m):
                    fails.append("mount-gated launch did not run")
                else:
                    try:
                        polls = int(sent_m.read_text().strip().split()[0])
                    except ValueError:
                        polls = -1
                    if polls < 3:
                        fails.append(f"daemon launched before mount "
                                    f"(polls={polls})")
            # expiry: mount never appears -> daemon still launches.
            mstub2 = mdir / "mstub2"
            mstub2.mkdir()
            (mstub2 / "grep").write_text("#!/bin/sh\nexit 1\n")
            (mstub2 / "sleep").write_text("#!/bin/sh\nexit 0\n")
            os.chmod(mstub2 / "grep", 0o755)
            os.chmod(mstub2 / "sleep", 0o755)
            sent_x = mdir / "sent_expired"
            fake_x = mdir / "fake-idle-x"
            fake_x.write_text("#!/bin/sh\necho launched > \"%s\"\n"
                              % sent_x.as_posix())
            os.chmod(fake_x, 0o755)
            mtree2 = mdir / "hx2"
            (mtree2 / "wifi").mkdir(parents=True)
            (mtree2 / "wifi" / "rcInsDriver.sh").write_bytes(mbytes)
            mm2 = manifest([dict(reg("/wifi/rcInsDriver.sh", mbytes),
                                  sha256=sh(mbytes), size=len(mbytes))])
            (mdir / "stockm2.json").write_text(json.dumps(mm2))
            rc, _ = run_py(
                "mutate_customer.py", "--tree", str(mtree2),
                "--manifest", str(mdir / "stockm2.json"),
                "--idle-bin", str(tmp / "idle.bin"),
                "--hook-line", fake_x.as_posix() + " &",
                "--out-manifest", str(mdir / "mm2.json"))
            if rc != 0:
                fails.append("mutate wait-expiry hook failed")
            else:
                r = run_hook(sh_bin, mtree2 / "wifi" / "rcInsDriver.sh",
                             mstub2)
                if r.returncode != 0:
                    fails.append("wait-expiry hook exit != 0")
                if not await_file(sent_x):
                    fails.append("daemon missing after wait expiry")

        # 2f. audio replacement (wav swap + md5sum refresh + md5sum-listed
        # addition) + TSR flag patch in the hook block.
        def fake_wav(nframes: int, rate: int = 24000) -> bytes:
            payload = b"\x01\x02" * nframes
            return (struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(payload),
                                b"WAVE", b"fmt ", 16, 1, 1, rate, rate * 2,
                                2, 16, b"data", len(payload)) + payload)

        adir = tmp / "au"
        (adir / "wifi").mkdir(parents=True)
        (adir / "minieye" / "adas" / "audios").mkdir(parents=True)
        au_hook = b"#!/bin/sh\necho hi\nexit $?\n"
        (adir / "wifi" / "rcInsDriver.sh").write_bytes(au_hook)
        old_a = fake_wav(100)
        (adir / "minieye" / "adas" / "audios" / "A.wav").write_bytes(old_a)
        md5_lines = ["%s  ./audios/A.wav" % hashlib.md5(old_a).hexdigest(),
                     "8e320b19d08eaec12a573bd446fd92c5  ./audios/tlr_green_on.wav",
                     "deadbeefdeadbeefdeadbeefdeadbeef  ./run.sh"]
        # NOTE: binary write — text mode would CRLF-convert on Windows and
        # break the base-integrity hash (same rule as firmware artifacts).
        (adir / "minieye" / "adas" / "md5sum.txt").write_bytes(
            ("\n".join(md5_lines) + "\n").encode("ascii"))
        au_stock = manifest([
            reg("/wifi/rcInsDriver.sh", au_hook),
            reg("/minieye/adas/audios/A.wav", old_a),
            reg("/minieye/adas/md5sum.txt",
                ("\n".join(md5_lines) + "\n").encode()),
        ])
        (tmp / "au_stock.json").write_text(json.dumps(au_stock))
        new_a, new_t = fake_wav(150), fake_wav(80)
        (tmp / "newA.wav").write_bytes(new_a)
        (tmp / "newT.wav").write_bytes(new_t)
        au_map = [{"path": "/minieye/adas/audios/A.wav",
                   "file": str(tmp / "newA.wav")},
                  {"path": "/minieye/adas/audios/tlr_green_on.wav",
                   "file": str(tmp / "newT.wav")}]
        (tmp / "au_map.json").write_text(json.dumps(au_map))
        rc, out = run_py(
            "mutate_customer.py", "--tree", str(adir),
            "--manifest", str(tmp / "au_stock.json"),
            "--idle-bin", str(tmp / "idle.bin"),
            "--audio-replacements", str(tmp / "au_map.json"),
            "--tsr-patch", "--out-manifest", str(tmp / "au_mut.json"))
        if rc != 0:
            fails.append("mutate audio+tsr failed: " + out[-300:])
        else:
            if (adir / "minieye" / "adas" / "audios" / "A.wav").read_bytes() != new_a:
                fails.append("wav swap not applied")
            tlr = adir / "minieye" / "adas" / "audios" / "tlr_green_on.wav"
            if not tlr.is_file() or tlr.read_bytes() != new_t:
                fails.append("md5sum-listed addition not created")
            got = (adir / "minieye" / "adas" / "md5sum.txt").read_text().split("\n")
            if (got[0] != "%s  ./audios/A.wav" % hashlib.md5(new_a).hexdigest()
                    or got[1] != "%s  ./audios/tlr_green_on.wav" % hashlib.md5(new_t).hexdigest()
                    or not got[2].startswith("deadbeef")):
                fails.append("md5sum.txt lines not refreshed exactly")
            hx = (adir / "wifi" / "rcInsDriver.sh").read_text()
            if "c2m_adas_de.tmp" not in hx or "--enable_tsr=" not in hx:
                fails.append("tsr patch missing from hook block")
            if hx.index("c2m_adas_de.tmp") > hx.index("/customer/c2m/c2m-idle"):
                fails.append("tsr patch not before daemon launch")
            mut = json.loads((tmp / "au_mut.json").read_text())
            if not mut.get("tsr_patch") or len(mut.get("replaced", {})) != 3:
                fails.append("mutation manifest missing audio/tsr record")
            # verify_b_manifest accepts exactly this shape.
            actual_entries = [
                reg("/wifi/rcInsDriver.sh",
                    (adir / "wifi" / "rcInsDriver.sh").read_bytes()),
                reg("/minieye/adas/audios/A.wav", new_a),
                reg("/minieye/adas/md5sum.txt",
                    (adir / "minieye" / "adas" / "md5sum.txt").read_bytes()),
                {"path": "/c2m", "inode": 9, "type": "dir", "mode": 0o755,
                 "mode_oct": "0o755", "uid": 1001, "gid": 1001,
                 "size": 96, "mtime": 1691062662},
                reg("/c2m/c2m-idle", b"ARMFAKE", mode=0o755),
                reg("/minieye/adas/audios/tlr_green_on.wav", new_t),
            ]
            (tmp / "au_actual.json").write_text(json.dumps(manifest(actual_entries)))
            r = subprocess.run(
                [sys.executable, "tools/fw/verify_b_manifest.py", "--stock",
                 str(tmp / "au_stock.json"), "--mut", str(tmp / "au_mut.json"),
                 "--actual", str(tmp / "au_actual.json")],
                cwd=ROOT, capture_output=True, text=True)
            if r.returncode != 0:
                fails.append("verify_b_manifest replaced-shape failed: "
                             + r.stdout[-400:])
        # 2f-dir: existing-directory size/mtime drift is a rebuild artifact
        # (an allowlisted addition changes both) and must not BLOCK.
        dirstock = manifest([
            reg("/f", b"hello"),
            {"path": "/d", "inode": 2, "type": "dir", "mode": 0o755,
             "mode_oct": "0o755", "uid": 1001, "gid": 1001,
             "size": 96, "mtime": 1691062662}])
        diractual = manifest([
            reg("/f", b"hello"),
            {"path": "/d", "inode": 2, "type": "dir", "mode": 0o755,
             "mode_oct": "0o755", "uid": 1001, "gid": 1001,
             "size": 128, "mtime": 1791947527}])
        (tmp / "dirstock.json").write_text(json.dumps(dirstock))
        (tmp / "diractual.json").write_text(json.dumps(diractual))
        (tmp / "dir_mut.json").write_text(json.dumps(
            {"hook": "/f", "added": [],
             "modified": [{"path": "/f", "new_sha256": sh(b"hello")}]}))
        r = subprocess.run(
            [sys.executable, "tools/fw/verify_b_manifest.py", "--stock",
             str(tmp / "dirstock.json"), "--mut", str(tmp / "dir_mut.json"),
             "--actual", str(tmp / "diractual.json")],
            cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            fails.append("directory size/mtime drift wrongly BLOCKED: "
                         + r.stdout[-300:])

        # 2g. TSR patch LOGIC with real base64/sed/grep: run the verbatim
        # block lines with only the device prefix substituted (device paths
        # are uncreatable on the test machine). Proves decode/flip/re-encode
        # consistency + idempotency, i.e. run.sh will observe no md5 drift.
        if sh_bin is None:
            fails.append("sh missing for tsr logic test")
        else:
            sys.path.insert(0, str(ROOT / "tools" / "fw"))
            import mutate_customer as _mc
            sys.path.pop(0)
            troot = tmp / "tsr"
            cfg = troot / "customer" / "minieye" / "config"
            cfg.mkdir(parents=True)
            flag_src = b"--enable_vehicle=true\n--enable_tsr=false\n--enable_lane=true\n"
            import base64 as _b64
            (cfg / "adas.flag").write_bytes(_b64.encodebytes(flag_src))
            blk = "\n".join(_mc.TSR_PATCH_LINES)
            blk = blk.replace("/customer/minieye/config",
                              (cfg.as_posix()))
            blk = blk.replace("/tmp/c2m_adas_de.tmp",
                              (tmp / "c2m_adas_de.tmp").as_posix())
            tscript = tmp / "tsr_block.sh"
            tscript.write_text("#!/bin/sh\n" + blk + "\n")
            # plain env: real base64/sed/grep must resolve (no stub PATH).
            r1 = subprocess.run([sh_bin, str(tscript)], capture_output=True,
                                text=True, timeout=30)
            de = (cfg / "adas_de.flag").read_bytes()
            if r1.returncode != 0 or b"--enable_tsr=true\n" not in de:
                fails.append("tsr block did not flip the flag")
            if _b64.decodebytes((cfg / "adas.flag").read_bytes()) != de:
                fails.append("tsr rewrite broke adas.flag/adas_de.flag sync")
            if b"--enable_vehicle=true\n--enable_lane=true\n" not in de.replace(
                    b"--enable_tsr=true\n", b""):
                fails.append("tsr rewrite disturbed other flags")
            snap = (cfg / "adas.flag").read_bytes(), de
            r2 = subprocess.run([sh_bin, str(tscript)], capture_output=True,
                                text=True, timeout=30)
            if r2.returncode != 0 or (cfg / "adas.flag").read_bytes() != snap[0] \
                    or (cfg / "adas_de.flag").read_bytes() != snap[1]:
                fails.append("tsr patch not idempotent")
            # sh -n syntax gate on a real mutated hook with the TSR block.
            hx = (adir / "wifi" / "rcInsDriver.sh").read_bytes()
            (tmp / "syntax_hook.sh").write_bytes(hx)
            r3 = subprocess.run([sh_bin, "-n", str(tmp / "syntax_hook.sh")],
                                capture_output=True, text=True, timeout=30)
            if r3.returncode != 0:
                fails.append("mutated hook sh -n failed: " + r3.stderr[-300:])

        # negative: wrong wav encoding rejected on a FRESH stock tree
        # (isolates the format gate from base-integrity).
        adir2 = tmp / "au2"
        (adir2 / "wifi").mkdir(parents=True)
        (adir2 / "minieye" / "adas" / "audios").mkdir(parents=True)
        (adir2 / "wifi" / "rcInsDriver.sh").write_bytes(au_hook)
        (adir2 / "minieye" / "adas" / "audios" / "A.wav").write_bytes(old_a)
        (adir2 / "minieye" / "adas" / "md5sum.txt").write_bytes(
            ("\n".join(md5_lines) + "\n").encode("ascii"))
        bad_rate = fake_wav(100, rate=8000)
        (tmp / "bad.wav").write_bytes(bad_rate)
        (tmp / "bad_map.json").write_text(json.dumps(
            [{"path": "/minieye/adas/audios/A.wav",
              "file": str(tmp / "bad.wav")}]))
        rc, out = run_py(
            "mutate_customer.py", "--tree", str(adir2),
            "--manifest", str(tmp / "au_stock.json"),
            "--idle-bin", str(tmp / "idle.bin"),
            "--audio-replacements", str(tmp / "bad_map.json"),
            "--out-manifest", str(tmp / "au_mut_bad.json"))
        if rc == 0 or "wav rejected" not in out:
            fails.append("bad wav encoding not rejected")

        # 3. candidate_diff allowlist
        ksha = sh(b"k" * 0x100)
        base = mini_contract(0x300, 0x5000, 0x6000, ksha)
        (tmp / "base.json").write_text(json.dumps(base))
        cand = mini_contract(0x340, 0x5000, 0x6040, ksha)  # +0x40 delta
        cand["outer_members"][0]["sha256"] = sh(b"inner2")
        cand["inner_sha256"] = sh(b"inner2")
        cand["outer_members"][2]["sha256"] = sh(b"md5y")
        cand["loads"][1]["sha256"] = sh(b"c" * 0x340)
        (tmp / "cand.json").write_text(json.dumps(cand))
        deep = {"verdict": "VALID",
                "checks": [{"check": "protected.cardv", "result": "PASS"},
                           {"check": "protected.adas", "result": "PASS"}]}
        (tmp / "deep.json").write_text(json.dumps(deep))
        r = subprocess.run(
            [sys.executable, "tools/fw/candidate_diff.py", "--base", str(tmp / "base.json"),
             "--cand", str(tmp / "cand.json"), "--deep-report", str(tmp / "deep.json"),
             "--out", str(tmp / "diff.json")], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            fails.append("allowlist OK case BLOCKED: " + r.stdout[-600:] + " ERR:" + r.stderr[-600:])
        # delta=0 variant: same customer SIZE, changed bytes (fits in UBIFS
        # slack — the real-Linux shape). Must also be ALLOWLIST-OK.
        cand0 = mini_contract(0x300, 0x5000, 0x6000, ksha)
        cand0["outer_members"][0]["sha256"] = sh(b"inner3")
        cand0["inner_sha256"] = sh(b"inner3")
        cand0["outer_members"][2]["sha256"] = sh(b"md5z")
        cand0["loads"][1]["sha256"] = sh(b"C" * 0x300)
        (tmp / "cand0.json").write_text(json.dumps(cand0))
        r = subprocess.run(
            [sys.executable, "tools/fw/candidate_diff.py", "--base", str(tmp / "base.json"),
             "--cand", str(tmp / "cand0.json"), "--deep-report", str(tmp / "deep.json"),
             "--out", str(tmp / "diff0.json")], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            fails.append("allowlist delta=0 OK case BLOCKED: " + r.stdout[-600:])
        # kernel tamper -> BLOCK
        cand2 = json.loads((tmp / "cand.json").read_text())
        cand2["loads"][0]["sha256"] = sh(b"evil")
        (tmp / "cand2.json").write_text(json.dumps(cand2))
        r = subprocess.run(
            [sys.executable, "tools/fw/candidate_diff.py", "--base", str(tmp / "base.json"),
             "--cand", str(tmp / "cand2.json"), "--deep-report", str(tmp / "deep.json"),
             "--out", str(tmp / "diff2.json")], cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            fails.append("kernel payload tamper not BLOCKED")
        # tail change -> BLOCK
        cand3 = json.loads((tmp / "cand.json").read_text())
        cand3["tail_unknown"]["hex"] = "ffffff"
        (tmp / "cand3.json").write_text(json.dumps(cand3))
        r = subprocess.run(
            [sys.executable, "tools/fw/candidate_diff.py", "--base", str(tmp / "base.json"),
             "--cand", str(tmp / "cand3.json"), "--deep-report", str(tmp / "deep.json"),
             "--out", str(tmp / "diff3.json")], cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            fails.append("tail change not BLOCKED")
        # bad deep verdict -> BLOCK
        deep_bad = {"verdict": "INVALID", "checks": []}
        (tmp / "deepbad.json").write_text(json.dumps(deep_bad))
        r = subprocess.run(
            [sys.executable, "tools/fw/candidate_diff.py", "--base", str(tmp / "base.json"),
             "--cand", str(tmp / "cand.json"), "--deep-report", str(tmp / "deepbad.json"),
             "--out", str(tmp / "diff4.json")], cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            fails.append("bad deep verdict not BLOCKED")

        # 4. assemble_inner layout round-trip + overlap rejection
        layout = {"script_text": "HDR\n% <- this is end of script symbol\n",
                  "payloads": [{"section": "a.es", "load_index": 0, "offset": 0x100,
                                "size": 4, "file": "p0.bin"}],
                  "tail_hex": "aa", "tail_offset": 0x104, "total_size": 0x105}
        (tmp / "layout.json").write_text(json.dumps(layout))
        (tmp / "p0.bin").write_bytes(b"DATA")
        rc, _ = run_py("assemble_inner.py", "--mode", "layout",
                       "--layout-json", str(tmp / "layout.json"),
                       "--payload-dir", str(tmp), "--out", str(tmp / "inner.bin"))
        if rc != 0:
            fails.append("assemble layout failed")
        else:
            d = (tmp / "inner.bin").read_bytes()
            if d[0x100:0x104] != b"DATA" or d[-1:] != b"\xaa" or d[0x40] != 0xFF:
                fails.append("assemble layout bytes wrong")
        bad_layout = dict(layout, payloads=[
            {"section": "a.es", "load_index": 0, "offset": 0x10, "size": 4, "file": "p0.bin"}])
        (tmp / "badlayout.json").write_text(json.dumps(bad_layout))
        rc, _ = run_py("assemble_inner.py", "--mode", "layout",
                       "--layout-json", str(tmp / "badlayout.json"),
                       "--payload-dir", str(tmp), "--out", str(tmp / "inner2.bin"))
        if rc == 0:
            fails.append("assemble overlap not rejected")

        # 5. tar_assemble on a synthetic TAR
        star = tmp / "synth.tar"
        members = [("SigmastarUpgradeSD_SSC8838G.bin", b"1" * 100),
                   ("sysVer.txt", b"sys"), ("minieye_firmware.md5", b"md5x"),
                   ("adas_upgrade.sh", b"adas")]
        with tarfile.open(star, "w", format=tarfile.USTAR_FORMAT) as t:
            for name, data in members:
                ti = tarfile.TarInfo(name)
                ti.size = len(data)
                ti.mode = 0o775 if name.endswith(".sh") else 0o664
                ti.mtime = 1691062673
                t.addfile(ti, io.BytesIO(data))
        scontract = {"outer_order": [n for n, _ in members],
                     "outer_members": [{"name": n, "size": len(d), "sha256": sh(d)}
                                       for n, d in members]}
        (tmp / "scontract.json").write_text(json.dumps(scontract))
        rc, _ = run_py("tar_assemble.py", "--mode", "golden", "--tar", str(star),
                       "--contract", str(tmp / "scontract.json"),
                       "--out", str(tmp / "repro.tar"))
        if rc != 0 or (tmp / "repro.tar").read_bytes() != star.read_bytes():
            fails.append("tar golden round-trip failed")
        (tmp / "new_inner.bin").write_bytes(b"2" * 120)
        (tmp / "sys_blob").write_bytes(b"sys")
        (tmp / "md5_blob").write_bytes(b"md5x")
        (tmp / "adas_blob").write_bytes(b"adas")
        (tmp / "members.json").write_text(json.dumps([
            {"name": "SigmastarUpgradeSD_SSC8838G.bin", "file": str(tmp / "new_inner.bin")},
            {"name": "sysVer.txt", "file": str(tmp / "sys_blob")},
            {"name": "minieye_firmware.md5", "file": str(tmp / "md5_blob")},
            {"name": "adas_upgrade.sh", "file": str(tmp / "adas_blob")},
        ]))
        rc, _ = run_py("tar_assemble.py", "--mode", "package", "--tar", str(star),
                       "--contract", str(tmp / "scontract.json"),
                       "--members-json", str(tmp / "members.json"),
                       "--out", str(tmp / "pkg.tar"))
        if rc != 0:
            fails.append("tar package mode failed")
        else:
            orig = star.read_bytes()
            new = (tmp / "pkg.tar").read_bytes()
            oh, nh = orig[:512], new[:512]
            if oh[:124] != nh[:124] or oh[136:148] != nh[136:148] or oh[156:] != nh[156:]:
                fails.append("tar package header changed outside size/chksum")
            if oh[124:136] == nh[124:136]:
                fails.append("tar package size field not updated")
            with tarfile.open(tmp / "pkg.tar", "r") as tf:
                if tf.extractfile("SigmastarUpgradeSD_SSC8838G.bin").read() != b"2" * 120:
                    fails.append("tar package member bytes wrong")

    if fails:
        print("CANDIDATE-B SYNTHETIC FAILURES:")
        for f in fails:
            print(" -", f)
        return 1
    print("candidate-b synthetic: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
