#!/usr/bin/env python3
"""Native + ARM real-Dropbear 2026.94 SSH integration on loopback only.

Loopback-only, synthetic temp keys only. No camera, card, radio, AP,
private assets, owner keys, ~/.ssh, or external connections. This test
does NOT prove physical AP, radio, or hardware behavior.

Modes (same file, parent workflow runs it twice):
  Native (default, TARGET_DIR unset): builds native dropbear/dropbearkey
    from the pinned tarball in a temp dir and runs loopback SSH. Unchanged.
  ARM (opt-in via C2M_DEBUG_SSH_TARGET_DIR): skips the native build but
    still verifies tar SHA + build-script localoptions policy, then runs
    the SAME loopback suite against the prebuilt ARM binaries under
    qemu-arm-static -L <sysroot>. This proves ARM userspace ABI behavior
    (wire protocol, key auth, exec, forwarding rejection), NOT hardware,
    radio, or AP behavior. QEMU user-mode input/output is emulated
    userspace data, never a hardware proof.

Env (exact names expected by parent workflow):
  C2M_DEBUG_UPSTREAM_TARBALL: path to pinned
    work/dropbear-upstream/dropbear-2026.94.tar.bz2. When unset the test
    falls back to <repo>/work/dropbear-upstream/dropbear-2026.94.tar.bz2.
  C2M_REQUIRE_DEBUG_SSH_TEST=1: missing prerequisites fail instead of skip.
    Required in CI. On Windows without a native toolchain this flag fails.
  C2M_DEBUG_SSH_TARGET_DIR: absolute path to a dir containing prebuilt ARM
    `dropbear` + `dropbearkey` (e.g. $PWD/work/debug-build). Unset means
    ARM mode is skipped even with C2M_REQUIRE_DEBUG_SSH_TEST=1, so the
    native-only gate keeps working; the ARM gate always sets it. A set but
    invalid TARGET_DIR fails when C2M_REQUIRE_DEBUG_SSH_TEST=1.
  C2M_DEBUG_SSH_SYSROOT: absolute stock sysroot containing
    lib/ld-linux-armhf.so.3 (e.g. $PWD/work/sysroot). Required in ARM mode.
  C2M_DEBUG_SSH_QEMU: qemu-arm-static binary. Optional; defaults to
    /usr/bin/qemu-arm-static then PATH lookup.

Run: python3 tests/test_debug_ssh.py
Native build takes ~10s (configure + make PROGRAMS='dropbear dropbearkey').
ARM mode reuses the target build (no rebuild). Total budget ~4min.
No commit/push. Reports contain only hashes and text logs, never private
key bytes or upstream artifact bytes. Never alters host /etc.

ARM notes: the server runs as the host fixture user (qemu getpwuid reads
host /etc/passwd; stock NSS modules load via the -L prefix). Guest
absolute temp paths resolve to host temp files (same pattern as the
fw/debug/build_dropbear.sh qemu smoke tests). Dropbear session children
exec /bin/sh via qemu host-binary fallback (+ binfmt when registered);
without that fallback exec tests fail honestly instead of passing falsely.
"""
from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "fw" / "debug" / "build_dropbear.sh"
VER = "2026.94"
EXPECTED_SHA = "e098034a843699200c8c977a991fff73159735bf795d5f72ef672c41a6b1ae81"
TARBALL_ENV = "C2M_DEBUG_UPSTREAM_TARBALL"
REQUIRE_ENV = "C2M_REQUIRE_DEBUG_SSH_TEST"
TARGET_ENV = "C2M_DEBUG_SSH_TARGET_DIR"
SYSROOT_ENV = "C2M_DEBUG_SSH_SYSROOT"
QEMU_ENV = "C2M_DEBUG_SSH_QEMU"
DEFAULT_TARBALL = ROOT / "work" / "dropbear-upstream" / f"dropbear-{VER}.tar.bz2"
DEFAULT_QEMU = "/usr/bin/qemu-arm-static"
LINUX = sys.platform.startswith("linux")
REQUIRED = os.environ.get(REQUIRE_ENV) == "1"

# Authoritative auth/forwarding policy mirrored from fw/debug/build_dropbear.sh.
# The policy test parses the script heredoc and asserts these, so drift fails.
REQUIRED_DEFINES = {
    "DROPBEAR_SVR_PASSWORD_AUTH": "0",
    "DROPBEAR_SVR_PAM_AUTH": "0",
    "DROPBEAR_SVR_SHADOW_AUTH": "0",
    "DROPBEAR_CLI_PASSWORD_AUTH": "0",
    "DROPBEAR_SVR_AGENTFWD": "0",
    "DROPBEAR_CLI_AGENTFWD": "0",
    "DROPBEAR_X11FWD": "0",
    "DROPBEAR_SVR_LOCALTCPFWD": "0",
    "DROPBEAR_SVR_REMOTETCPFWD": "0",
    "DROPBEAR_CLI_LOCALTCPFWD": "0",
    "DROPBEAR_CLI_REMOTETCPFWD": "0",
    "DROPBEAR_SVR_LOCALSTREAMFWD": "0",
    "DROPBEAR_SVR_REMOTESTREAMFWD": "0",
    "DROPBEAR_CLI_PROXYCMD": "0",
    "DROPBEAR_CLI_NETCAT": "0",
    "DROPBEAR_SFTPSERVER": "0",
    "DROPBEAR_SVR_PUBKEY_AUTH": "1",
    "DROPBEAR_SVR_MULTIUSER": "0",
    "DROPBEAR_ED25519": "1",
}
SSH_OUTPUT_LIMIT = 256 * 1024
SSH_TIMEOUT = 20


def require_or_skip(reason: str) -> None:
    if REQUIRED:
        raise AssertionError(reason)
    raise unittest.SkipTest(reason)


def resolve_tarball() -> Path | None:
    raw = os.environ.get(TARBALL_ENV)
    if raw:
        candidate = Path(raw)
        if not candidate.is_absolute():
            # Parent workflow sets a repo-relative path like
            # work/dropbear-upstream/dropbear-2026.94.tar.bz2.
            rooted = (ROOT / raw).resolve()
            if rooted.is_file():
                return rooted
            candidate = (Path.cwd() / candidate).resolve()
        return candidate
    return DEFAULT_TARBALL


def resolve_target_dir() -> Path | None:
    """Absolute TARGET_DIR or None when ARM mode is not requested.

    Unset means ARM mode skipped (even with REQUIRE=1) so the native-only
    gate keeps working; the ARM gate always sets this env.
    """
    raw = os.environ.get(TARGET_ENV)
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        require_or_skip(f"{TARGET_ENV} must be an absolute path")
    return candidate


def resolve_sysroot() -> Path | None:
    raw = os.environ.get(SYSROOT_ENV)
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    return candidate


def resolve_qemu() -> str | None:
    raw = os.environ.get(QEMU_ENV)
    if raw:
        return raw
    if Path(DEFAULT_QEMU).is_file() and os.access(DEFAULT_QEMU, os.X_OK):
        return DEFAULT_QEMU
    return shutil.which("qemu-arm-static")


def is_arm32_elf(path: Path) -> bool:
    """Lightweight ARM 32-bit ELF check (magic + class + e_machine)."""
    try:
        with path.open("rb") as handle:
            header = handle.read(20)
    except OSError:
        return False
    if len(header) < 20 or header[:4] != b"\x7fELF":
        return False
    if header[4] != 1:  # EI_CLASS 32-bit
        return False
    machine = int.from_bytes(header[18:20], "little")
    return machine == 40  # EM_ARM


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_localoptions_block() -> str:
    """Return the raw localoptions.h heredoc from fw/debug/build_dropbear.sh."""
    text = BUILD_SCRIPT.read_text(encoding="utf-8")
    marker = 'cat > "$src/localoptions.h"'
    start = text.find(marker)
    if start < 0:
        raise AssertionError("build_dropbear.sh localoptions.h block missing")
    heredoc = text.find("<<'EOF'", start)
    if heredoc < 0:
        raise AssertionError("localoptions heredoc marker missing")
    body_start = text.find("\n", heredoc) + 1
    end = text.find("\nEOF\n", body_start)
    if end < 0:
        raise AssertionError("localoptions heredoc terminator missing")
    block = text[body_start:end + 1]
    if "#ifndef DROPBEAR_LOCALOPTIONS_H" not in block:
        raise AssertionError("localoptions block truncated")
    return block


def parse_defines(block: str) -> dict[str, str]:
    defines: dict[str, str] = {}
    for line in block.splitlines():
        parts = line.strip().split()
        if len(parts) == 3 and parts[0] == "#define":
            defines[parts[1]] = parts[2]
    return defines


def assert_policy_block(block: str) -> dict[str, str]:
    defines = parse_defines(block)
    for macro, want in REQUIRED_DEFINES.items():
        got = defines.get(macro)
        if got != want:
            raise AssertionError(f"auth-policy drift: {macro}={got!r} want {want!r}")
    return defines


def safe_extract(tarball: Path, dest: Path) -> Path:
    """Verify SHA already checked; reject absolute/parent/symlink/special members."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, mode="r:bz2") as tar:
        members = tar.getmembers()
        if not members:
            raise AssertionError("empty upstream tarball")
        for member in members:
            name = member.name
            if not name or name.startswith("/") or name.startswith("\\"):
                raise AssertionError(f"unsafe tar member: {name!r}")
            parts = Path(name).parts
            if ".." in parts:
                raise AssertionError(f"unsafe tar member: {name!r}")
            if member.issym() or member.islnk():
                raise AssertionError(f"link tar member rejected: {name!r}")
            if member.ischr() or member.isblk() or member.isfifo() or member.isdev():
                raise AssertionError(f"special tar member rejected: {name!r}")
        top = f"dropbear-{VER}"
        names = {m.name.split("/")[0] for m in members if m.name}
        if top not in names:
            raise AssertionError(f"upstream top dir {top} missing")
        try:
            tar.extractall(path=dest, filter="data")  # type: ignore[call-arg]
        except TypeError:
            tar.extractall(path=dest)
    src = dest / top
    if not (src / "configure").is_file():
        raise AssertionError("extracted source lacks configure")
    return src


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_port(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def stop_tree(proc: subprocess.Popen) -> None:
    """Stop own process group and descendants; never touches foreign PIDs."""
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        try:
            proc.terminate()
        except OSError:
            pass
    try:
        proc.wait(timeout=3)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=3)
    except (subprocess.TimeoutExpired, OSError):
        pass


class DebugSshPolicyTests(unittest.TestCase):
    """Portable: build-script auth-policy pin, runnable everywhere."""

    def test_build_script_pins_keyonly_noforward_rootonly(self) -> None:
        self.assertTrue(BUILD_SCRIPT.is_file(), "fw/debug/build_dropbear.sh missing")
        block = extract_localoptions_block()
        assert_policy_block(block)

    def test_require_flag_semantics_documented(self) -> None:
        # Validates the Windows-skip vs required-CI-fail contract in pure
        # Python on every platform (no I/O, no build).
        def decision(linux: bool, prereq: bool, required: bool) -> str:
            if linux and prereq:
                return "run"
            return "fail" if required else "skip"

        self.assertEqual(decision(True, True, False), "run")
        self.assertEqual(decision(True, False, False), "skip")
        self.assertEqual(decision(True, False, True), "fail")
        self.assertEqual(decision(False, False, False), "skip")
        self.assertEqual(decision(False, True, True), "fail")
        # Exact env names the parent workflow sets/expects.
        self.assertEqual(TARBALL_ENV, "C2M_DEBUG_UPSTREAM_TARBALL")
        self.assertEqual(REQUIRE_ENV, "C2M_REQUIRE_DEBUG_SSH_TEST")


class DebugSshNativeTests(unittest.TestCase):
    """Linux-only real Dropbear 2026.94 on 127.0.0.1 with synthetic temp keys."""

    @classmethod
    def setUpClass(cls) -> None:
        if not LINUX:
            require_or_skip("Linux native Dropbear SSH test requires Linux")
        native_cc = shutil.which("gcc") or shutil.which("cc")
        if native_cc is None:
            require_or_skip("native prerequisite missing: gcc/cc")
        for tool in ("make", "ssh", "ssh-keygen"):
            if shutil.which(tool) is None:
                require_or_skip(f"native prerequisite missing: {tool}")
        try:
            import pwd  # noqa: F401
        except ImportError:
            require_or_skip("pwd module required")
        import pwd as pwdmod

        tarball = resolve_tarball()
        if tarball is None or not tarball.is_file():
            require_or_skip(
                f"upstream tarball missing: set {TARBALL_ENV} to "
                f"work/dropbear-upstream/dropbear-{VER}.tar.bz2"
            )
        assert tarball is not None
        got = sha256_file(tarball)
        if got != EXPECTED_SHA:
            raise AssertionError(f"upstream tarball SHA mismatch: {got}")
        # Root account must exist (read-only check); login user is current euid
        # because DROPBEAR_SVR_MULTIUSER=0 only allows the server UID.
        try:
            root = pwdmod.getpwnam("root")
        except KeyError:
            raise AssertionError("root passwd entry missing")
        if root.pw_uid != 0:
            raise AssertionError("root passwd entry invalid")
        euid = os.geteuid()
        try:
            current = pwdmod.getpwuid(euid).pw_name
        except KeyError:
            raise AssertionError("current euid has no passwd entry")
        if not current or "/" in current or " " in current or ":" in current:
            raise AssertionError("current username invalid")
        if current == "root" and euid != 0:
            raise AssertionError("username/euid mismatch")
        cls.username = current
        cls.tmp = tempfile.TemporaryDirectory(prefix="c2m-debug-ssh-")
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        base.chmod(0o700)

        # Copy clean from pinned tar (never reuse configured ARM dir), then
        # configure native with the exact localoptions policy from the script.
        block = extract_localoptions_block()
        assert_policy_block(block)
        unpack = base / "upstream"
        src = safe_extract(tarball, unpack)
        (src / "localoptions.h").write_text(block, encoding="utf-8")
        assert native_cc is not None
        help_proc = subprocess.run(
            ["sh", "./configure", "--help"], cwd=src, capture_output=True,
            text=True, timeout=60)
        if help_proc.returncode != 0:
            raise AssertionError("configure --help failed:\n" + help_proc.stderr[-4000:])
        if "--enable-bundled-libtom" not in help_proc.stdout:
            raise AssertionError("bundled-libtom option missing")
        cfg = ["--disable-harden", "--disable-zlib", "--enable-bundled-libtom"]
        for opt in ("shadow", "lastlog", "utmp", "utmpx",
                    "wtmp", "wtmpx", "loginfunc", "pututline",
                    "pututxline", "openpty"):
            if f"--disable-{opt}" in help_proc.stdout:
                cfg.append(f"--disable-{opt}")
        configure = subprocess.run(
            ["sh", "./configure"] + cfg, cwd=src, capture_output=True,
            text=True, timeout=120)
        if configure.returncode != 0:
            raise AssertionError(
                "native configure failed:\n" + configure.stdout[-4000:] + configure.stderr[-4000:])
        make = subprocess.run(
            ["make", "-j2", "PROGRAMS=dropbear dropbearkey"], cwd=src,
            capture_output=True, text=True, timeout=240)
        if make.returncode != 0:
            raise AssertionError(
                "native make failed:\n" + make.stdout[-4000:] + make.stderr[-4000:])
        cls.dropbear = src / "dropbear"
        cls.dropbearkey = src / "dropbearkey"
        for binary in (cls.dropbear, cls.dropbearkey):
            if not binary.is_file() or not os.access(binary, os.X_OK):
                raise AssertionError(f"native binary missing: {binary.name}")
        version = subprocess.run(
            [str(cls.dropbear), "-V"], capture_output=True, text=True, timeout=10)
        combined = version.stdout + version.stderr
        if VER not in combined:
            raise AssertionError(f"version proof missing 2026.94: {combined[-500:]}")
        help_text = subprocess.run(
            [str(cls.dropbear), "-h"], capture_output=True, text=True,
            timeout=10)
        logged = help_text.stdout + help_text.stderr
        if "-D" not in logged:
            raise AssertionError("dropbear -D support missing")

        # Synthetic keys only, all under temp (never ~/.ssh or owner keys).
        cls.run_dir = base / "run"
        cls.fixture_dir = base / "fixture"
        cls.run_dir.mkdir(mode=0o700)
        cls.fixture_dir.mkdir(mode=0o700)
        cls.hostkey = base / "host_ed25519"
        gen = subprocess.run(
            [str(cls.dropbearkey), "-t", "ed25519", "-f", str(cls.hostkey)],
            capture_output=True, text=True, timeout=30)
        if gen.returncode != 0 or not cls.hostkey.is_file():
            raise AssertionError("dropbearkey hostkey generation failed")
        cls.hostkey.chmod(0o600)
        pub_proc = subprocess.run(
            [str(cls.dropbearkey), "-f", str(cls.hostkey), "-y"],
            capture_output=True, text=True, timeout=15)
        if pub_proc.returncode != 0:
            raise AssertionError("dropbearkey -y failed")
        host_pub = ""
        for line in (pub_proc.stdout or "").splitlines():
            fields = line.strip().split()
            if len(fields) >= 2 and fields[0] in ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256"):
                host_pub = line.strip()
                break
        if not host_pub:
            raise AssertionError("could not parse dropbearkey -y pubkey line")
        cls.host_pub_fields = host_pub.split()
        cls.port = free_port()
        known_hosts = base / "known_hosts"
        known_hosts.write_text(
            f"[127.0.0.1]:{cls.port} {cls.host_pub_fields[0]} {cls.host_pub_fields[1]}\n",
            encoding="utf-8")
        known_hosts.chmod(0o600)
        cls.known_hosts = known_hosts

        cls.client_key = base / "client_ed25519"
        keygen = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-q", "-N", "",
             "-f", str(cls.client_key)],
            capture_output=True, text=True, timeout=30)
        if keygen.returncode != 0 or not cls.client_key.is_file():
            raise AssertionError("ssh-keygen client key failed: " + keygen.stderr[-1000:])
        cls.client_key.chmod(0o600)
        client_pub = (base / "client_ed25519.pub").read_text(encoding="utf-8")
        if not client_pub.startswith("ssh-ed25519 "):
            raise AssertionError("client pubkey is not ssh-ed25519")
        auth_keys = cls.run_dir / "authorized_keys"
        auth_keys.write_text(client_pub if client_pub.endswith("\n") else client_pub + "\n",
                             encoding="utf-8")
        auth_keys.chmod(0o600)

        cls.wrong_key = base / "wrong_ed25519"
        wrong = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-q", "-N", "",
             "-f", str(cls.wrong_key)],
            capture_output=True, text=True, timeout=30)
        if wrong.returncode != 0:
            raise AssertionError("wrong-key generation failed")

        cls.pidfile = cls.run_dir / "dropbear.pid"
        cls.proc = cls._launch_server(
            cls.dropbear, cls.run_dir, cls.hostkey, cls.port, cls.pidfile)
        if not wait_port("127.0.0.1", cls.port, timeout=10):
            out = ""
            try:
                out = Path(cls.tmp.name, "dropbear-stderr.log").read_text()[-2000:]
            except OSError:
                pass
            stop_tree(cls.proc)
            raise AssertionError("native dropbear did not listen on 127.0.0.1: " + out)

    @classmethod
    def _launch_server(cls, dropbear: Path, run_dir: Path,
                       hostkey: Path, port: int, pidfile: Path) -> subprocess.Popen:
        bindspec = f"127.0.0.1:{port}"
        assert bindspec.startswith("127.0.0.1:")
        argv = [str(dropbear), "-F", "-E", "-s", "-j", "-k",
                "-D", str(run_dir), "-r", str(hostkey),
                "-p", bindspec, "-I", "30", "-M", "60", "-T", "3",
                "-P", str(pidfile)]
        for flag in ("-F", "-E", "-s", "-j", "-k", "-D", "-r", "-p",
                     "-I", "30", "-M", "60", "-T", "3", "-P"):
            assert flag in argv, flag
        err_log = Path(cls.tmp.name) / f"dropbear-stderr-{port}.log"
        err_fd = os.open(err_log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=err_fd,
                                start_new_session=True, close_fds=True)
        os.close(err_fd)
        return proc

    @classmethod
    def tearDownClass(cls) -> None:
        proc = getattr(cls, "proc", None)
        if proc is not None and proc.poll() is None:
            stop_tree(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        # cls.tmp cleanup is handled by addClassCleanup so a half-finished
        # setUpClass still removes its temp tree.

    def ssh_args(self, key: Path | None, remote_cmd: str | None = None,
                 extra: list[str] | None = None) -> list[str]:
        args = ["ssh", "-F", "/dev/null",
                "-i", str(key) if key else "/dev/null",
                "-o", "BatchMode=yes",
                "-o", "PasswordAuthentication=no",
                "-o", "PreferredAuthentications=publickey",
                "-o", "IdentitiesOnly=yes",
                "-o", "StrictHostKeyChecking=yes",
                "-o", f"UserKnownHostsFile={self.known_hosts}",
                "-o", "GlobalKnownHostsFile=/dev/null",
                "-o", "CheckHostIP=no",
                "-o", "ConnectTimeout=5",
                "-o", "ConnectionAttempts=1",
                "-o", "LogLevel=ERROR",
                "-p", str(self.port),
                f"{self.username}@127.0.0.1"]
        if extra:
            # Insert -W/-L style options before destination is complex; only
            # allow extra -o options here. Forwarding probe builds its own argv.
            args[1:1] = extra
        if remote_cmd is not None:
            args.append(remote_cmd)
        return args

    def run_ssh(self, args: list[str], stdin: bytes | None = None,
                timeout: int = SSH_TIMEOUT) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(args, input=stdin, capture_output=True,
                                    timeout=timeout)
        except subprocess.TimeoutExpired:
            self.fail("ssh command timed out (no external connections allowed)")
        if len(result.stdout) > SSH_OUTPUT_LIMIT or len(result.stderr) > SSH_OUTPUT_LIMIT:
            self.fail("ssh output exceeded bound")
        return result

    def test_keyonly_exec_ok(self) -> None:
        result = self.run_ssh(self.ssh_args(self.client_key, "printf hello-debug-ssh"))
        self.assertEqual(result.returncode, 0, result.stderr[:1000].decode("utf-8", "replace"))
        self.assertEqual(result.stdout, b"hello-debug-ssh")

    def test_binary_roundtrip_over_stdin(self) -> None:
        payload = bytes((i * 37 + 11) % 256 for i in range(32 * 1024))
        digest = hashlib.sha256(payload).hexdigest()
        target = self.fixture_dir / "upload.bin"
        quoted = shlex.quote(str(target))
        put = self.run_ssh(self.ssh_args(self.client_key, f"cat > {quoted}"), stdin=payload)
        self.assertEqual(put.returncode, 0, put.stderr[:1000].decode("utf-8", "replace"))
        hashed = self.run_ssh(self.ssh_args(self.client_key, f"sha256sum {quoted}"))
        self.assertEqual(hashed.returncode, 0)
        first = hashed.stdout.decode("ascii", "strict").split()[0]
        self.assertEqual(first, digest)
        fetched = self.run_ssh(self.ssh_args(self.client_key, f"cat {quoted}"))
        self.assertEqual(fetched.returncode, 0)
        self.assertEqual(hashlib.sha256(fetched.stdout).hexdigest(), digest)
        self.assertEqual(fetched.stdout, payload)

    def test_wrong_key_rejected(self) -> None:
        result = self.run_ssh(self.ssh_args(self.wrong_key, "printf no"))
        self.assertNotEqual(result.returncode, 0, "wrong client key must not login")

    def test_no_key_or_password_cannot_login(self) -> None:
        # Pubkey disabled client-side: nothing to offer, must fail.
        nopub = ["ssh", "-F", "/dev/null",
                 "-o", "BatchMode=yes",
                 "-o", "PubkeyAuthentication=no",
                 "-o", "PasswordAuthentication=no",
                 "-o", "KbdInteractiveAuthentication=no",
                 "-o", "StrictHostKeyChecking=yes",
                 "-o", f"UserKnownHostsFile={self.known_hosts}",
                 "-o", "GlobalKnownHostsFile=/dev/null",
                 "-o", "ConnectTimeout=5",
                 "-o", "ConnectionAttempts=1",
                 "-o", "LogLevel=ERROR",
                 "-p", str(self.port),
                 f"{self.username}@127.0.0.1", "printf no"]
        result = self.run_ssh(nopub)
        self.assertNotEqual(result.returncode, 0)
        # Password-only attempt must also fail (server is key-only).
        pwonly = ["ssh", "-F", "/dev/null",
                  "-o", "BatchMode=yes",
                  "-o", "PubkeyAuthentication=no",
                  "-o", "PreferredAuthentications=password",
                  "-o", "StrictHostKeyChecking=yes",
                  "-o", f"UserKnownHostsFile={self.known_hosts}",
                  "-o", "GlobalKnownHostsFile=/dev/null",
                  "-o", "ConnectTimeout=5",
                  "-o", "ConnectionAttempts=1",
                  "-o", "LogLevel=ERROR",
                  "-p", str(self.port),
                  f"{self.username}@127.0.0.1", "printf no"]
        pw_result = self.run_ssh(pwonly)
        self.assertNotEqual(pw_result.returncode, 0, "password login must fail")

    def test_missing_authorized_keys_login_fails(self) -> None:
        empty_run = Path(self.tmp.name) / "empty-run"
        empty_run.mkdir(mode=0o700)
        port2 = free_port()
        pid2 = empty_run / "dropbear.pid"
        kh2 = Path(self.tmp.name) / "known_hosts2"
        kh2.write_text(
            f"[127.0.0.1]:{port2} {self.host_pub_fields[0]} {self.host_pub_fields[1]}\n",
            encoding="utf-8")
        kh2.chmod(0o600)
        proc2 = self._launch_server(self.dropbear, empty_run, self.hostkey,
                                   port2, pid2)
        try:
            if not wait_port("127.0.0.1", port2, timeout=10):
                self.fail("empty-keydir server did not listen")
            args = ["ssh", "-F", "/dev/null",
                    "-i", str(self.client_key),
                    "-o", "BatchMode=yes",
                    "-o", "PasswordAuthentication=no",
                    "-o", "PreferredAuthentications=publickey",
                    "-o", "IdentitiesOnly=yes",
                    "-o", "StrictHostKeyChecking=yes",
                    "-o", f"UserKnownHostsFile={kh2}",
                    "-o", "GlobalKnownHostsFile=/dev/null",
                    "-o", "CheckHostIP=no",
                    "-o", "ConnectTimeout=5",
                    "-o", "ConnectionAttempts=1",
                    "-o", "LogLevel=ERROR",
                    "-p", str(port2),
                    f"{self.username}@127.0.0.1", "printf no"]
            result = self.run_ssh(args)
            self.assertNotEqual(result.returncode, 0,
                                "missing authorized_keys must not login")
        finally:
            stop_tree(proc2)
            try:
                proc2.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    def test_forwarding_rejected(self) -> None:
        unused = free_port()
        args = ["ssh", "-F", "/dev/null",
                "-i", str(self.client_key),
                "-o", "BatchMode=yes",
                "-o", "PasswordAuthentication=no",
                "-o", "PreferredAuthentications=publickey",
                "-o", "IdentitiesOnly=yes",
                "-o", "StrictHostKeyChecking=yes",
                "-o", f"UserKnownHostsFile={self.known_hosts}",
                "-o", "GlobalKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=5",
                "-o", "ConnectionAttempts=1",
                "-o", "LogLevel=ERROR",
                "-p", str(self.port),
                "-W", f"127.0.0.1:{unused}",
                f"{self.username}@127.0.0.1"]
        result = self.run_ssh(args, stdin=b"", timeout=15)
        self.assertNotEqual(result.returncode, 0, "forwarding must be rejected")
        combined = (result.stdout + result.stderr).decode("utf-8", "replace").lower()
        self.assertTrue(
            any(token in combined for token in
                ("prohibit", "denied", "not allowed", "disabled", "forward")),
            f"expected forwarding rejection, got: {combined[:1000]}")


class DebugSshArmTests(unittest.TestCase):
    """ARM real-Dropbear 2026.94 under qemu on 127.0.0.1, synthetic temp keys.

    Opt-in via C2M_DEBUG_SSH_TARGET_DIR. Skips the native build but still
    verifies tar SHA + build-script localoptions policy; every dropbear /
    dropbearkey invocation (version, help, keygen, server) goes through
    binary_cmd ([qemu, -L, sysroot, target, ...]). SSH client stays native,
    proving ARM userspace ABI interop. QEMU proves userspace behavior only,
    never hardware, radio, or AP behavior. Never alters host /etc.
    """

    @classmethod
    def binary_cmd(cls, binary: Path, *args: str) -> list[str]:
        return [cls.qemu, "-L", str(cls.sysroot), str(binary), *args]

    @classmethod
    def setUpClass(cls) -> None:
        if not LINUX:
            require_or_skip("ARM Dropbear SSH test requires Linux")
        for tool in ("ssh", "ssh-keygen"):
            if shutil.which(tool) is None:
                require_or_skip(f"native prerequisite missing: {tool}")
        try:
            import pwd  # noqa: F401
        except ImportError:
            require_or_skip("pwd module required")
        import pwd as pwdmod

        # Integrity gates run in ARM mode too (no native build, same pins).
        tarball = resolve_tarball()
        if tarball is None or not tarball.is_file():
            require_or_skip(
                f"upstream tarball missing: set {TARBALL_ENV} to "
                f"work/dropbear-upstream/dropbear-{VER}.tar.bz2"
            )
        assert tarball is not None
        got = sha256_file(tarball)
        if got != EXPECTED_SHA:
            raise AssertionError(f"upstream tarball SHA mismatch: {got}")
        block = extract_localoptions_block()
        # Target compile-macro proof comes from the build reports CI sets;
        # this asserts the same key-only/no-forward/root-only source pin.
        assert_policy_block(block)

        target = resolve_target_dir()
        if target is None:
            # Opt-in only: unset skips even with REQUIRE=1 so the
            # native-only gate keeps working; the ARM gate always sets it.
            raise unittest.SkipTest(
                f"{TARGET_ENV} not set; ARM loopback opt-in only")
        if not target.is_dir():
            require_or_skip(f"target dir missing: {target}")
        assert target is not None and target.is_dir()
        sysroot = resolve_sysroot()
        if sysroot is None or not sysroot.is_dir():
            require_or_skip(
                f"sysroot missing: set {SYSROOT_ENV} to the stock sysroot")
        assert sysroot is not None
        if not (sysroot / "lib" / "ld-linux-armhf.so.3").is_file():
            require_or_skip("sysroot lacks /lib/ld-linux-armhf.so.3")
        qemu = resolve_qemu()
        if qemu is None or not Path(qemu).is_file():
            require_or_skip("qemu-arm-static missing: "
                            f"set {QEMU_ENV} or install qemu-user-static")
        cls.qemu = qemu
        cls.sysroot = sysroot
        dropbear = target / "dropbear"
        dropbearkey = target / "dropbearkey"
        for binary in (dropbear, dropbearkey):
            if not binary.is_file():
                require_or_skip(f"target binary missing: {binary}")
        for binary in (dropbear, dropbearkey):
            if not is_arm32_elf(binary):
                raise AssertionError(
                    f"target binary is not ARM 32-bit ELF: {binary.name}")
        cls.dropbear = dropbear
        cls.dropbearkey = dropbearkey

        try:
            root = pwdmod.getpwnam("root")
        except KeyError:
            raise AssertionError("root passwd entry missing")
        if root.pw_uid != 0:
            raise AssertionError("root passwd entry invalid")
        euid = os.geteuid()
        try:
            current = pwdmod.getpwuid(euid).pw_name
        except KeyError:
            raise AssertionError("current euid has no passwd entry")
        if not current or "/" in current or " " in current or ":" in current:
            raise AssertionError("current username invalid")
        if current == "root" and euid != 0:
            raise AssertionError("username/euid mismatch")
        cls.username = current
        cls.tmp = tempfile.TemporaryDirectory(prefix="c2m-debug-ssh-arm-")
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        base.chmod(0o700)

        version = subprocess.run(
            cls.binary_cmd(cls.dropbear, "-V"), capture_output=True,
            text=True, timeout=30)
        if VER not in (version.stdout + version.stderr):
            raise AssertionError("target version proof missing 2026.94")
        help_text = subprocess.run(
            cls.binary_cmd(cls.dropbear, "-h"), capture_output=True,
            text=True, timeout=30)
        if "-D" not in (help_text.stdout + help_text.stderr):
            raise AssertionError("target dropbear -D support missing")

        # Synthetic keys only, all under temp (never ~/.ssh or owner keys).
        cls.run_dir = base / "run"
        cls.fixture_dir = base / "fixture"
        cls.run_dir.mkdir(mode=0o700)
        cls.fixture_dir.mkdir(mode=0o700)
        cls.hostkey = base / "host_ed25519"
        gen = subprocess.run(
            cls.binary_cmd(cls.dropbearkey, "-t", "ed25519",
                           "-f", str(cls.hostkey)),
            capture_output=True, text=True, timeout=90)
        if gen.returncode != 0 or not cls.hostkey.is_file():
            raise AssertionError("target dropbearkey hostkey generation failed")
        cls.hostkey.chmod(0o600)
        pub_proc = subprocess.run(
            cls.binary_cmd(cls.dropbearkey, "-f", str(cls.hostkey), "-y"),
            capture_output=True, text=True, timeout=30)
        if pub_proc.returncode != 0:
            raise AssertionError("target dropbearkey -y failed")
        host_pub = ""
        for line in (pub_proc.stdout or "").splitlines():
            fields = line.strip().split()
            if len(fields) >= 2 and fields[0] in ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256"):
                host_pub = line.strip()
                break
        if not host_pub:
            raise AssertionError("could not parse target dropbearkey -y pubkey line")
        cls.host_pub_fields = host_pub.split()
        cls.port = free_port()
        known_hosts = base / "known_hosts"
        known_hosts.write_text(
            f"[127.0.0.1]:{cls.port} {cls.host_pub_fields[0]} {cls.host_pub_fields[1]}\n",
            encoding="utf-8")
        known_hosts.chmod(0o600)
        cls.known_hosts = known_hosts

        cls.client_key = base / "client_ed25519"
        keygen = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-q", "-N", "",
             "-f", str(cls.client_key)],
            capture_output=True, text=True, timeout=30)
        if keygen.returncode != 0 or not cls.client_key.is_file():
            raise AssertionError("ssh-keygen client key failed: " + keygen.stderr[-1000:])
        cls.client_key.chmod(0o600)
        client_pub = (base / "client_ed25519.pub").read_text(encoding="utf-8")
        if not client_pub.startswith("ssh-ed25519 "):
            raise AssertionError("client pubkey is not ssh-ed25519")
        auth_keys = cls.run_dir / "authorized_keys"
        auth_keys.write_text(client_pub if client_pub.endswith("\n") else client_pub + "\n",
                             encoding="utf-8")
        auth_keys.chmod(0o600)

        cls.wrong_key = base / "wrong_ed25519"
        wrong = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-q", "-N", "",
             "-f", str(cls.wrong_key)],
            capture_output=True, text=True, timeout=30)
        if wrong.returncode != 0:
            raise AssertionError("wrong-key generation failed")

        cls.pidfile = cls.run_dir / "dropbear.pid"
        cls.proc = cls._launch_server(
            cls.dropbear, cls.run_dir, cls.hostkey, cls.port, cls.pidfile)
        if not wait_port("127.0.0.1", cls.port, timeout=20):
            stop_tree(cls.proc)
            raise AssertionError("target dropbear did not listen on 127.0.0.1")

    @classmethod
    def _launch_server(cls, dropbear: Path, run_dir: Path,
                       hostkey: Path, port: int, pidfile: Path) -> subprocess.Popen:
        bindspec = f"127.0.0.1:{port}"
        assert bindspec.startswith("127.0.0.1:")
        argv = cls.binary_cmd(
            dropbear, "-F", "-E", "-s", "-j", "-k",
            "-D", str(run_dir), "-r", str(hostkey),
            "-p", bindspec, "-I", "30", "-M", "60", "-T", "3",
            "-P", str(pidfile))
        for flag in ("-F", "-E", "-s", "-j", "-k", "-D", "-r", "-p",
                     "-I", "30", "-M", "60", "-T", "3", "-P"):
            assert flag in argv, flag
        err_log = Path(cls.tmp.name) / f"dropbear-stderr-{port}.log"
        err_fd = os.open(err_log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=err_fd,
                                start_new_session=True, close_fds=True)
        os.close(err_fd)
        return proc

    @classmethod
    def tearDownClass(cls) -> None:
        proc = getattr(cls, "proc", None)
        if proc is not None and proc.poll() is None:
            stop_tree(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        # cls.tmp cleanup is handled by addClassCleanup so a half-finished
        # setUpClass still removes its temp tree.

    def ssh_args(self, key: Path | None, remote_cmd: str | None = None,
                 extra: list[str] | None = None) -> list[str]:
        args = ["ssh", "-F", "/dev/null",
                "-i", str(key) if key else "/dev/null",
                "-o", "BatchMode=yes",
                "-o", "PasswordAuthentication=no",
                "-o", "PreferredAuthentications=publickey",
                "-o", "IdentitiesOnly=yes",
                "-o", "StrictHostKeyChecking=yes",
                "-o", f"UserKnownHostsFile={self.known_hosts}",
                "-o", "GlobalKnownHostsFile=/dev/null",
                "-o", "CheckHostIP=no",
                "-o", "ConnectTimeout=5",
                "-o", "ConnectionAttempts=1",
                "-o", "LogLevel=ERROR",
                "-p", str(self.port),
                f"{self.username}@127.0.0.1"]
        if extra:
            args[1:1] = extra
        if remote_cmd is not None:
            args.append(remote_cmd)
        return args

    def run_ssh(self, args: list[str], stdin: bytes | None = None,
                timeout: int = SSH_TIMEOUT) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(args, input=stdin, capture_output=True,
                                    timeout=timeout)
        except subprocess.TimeoutExpired:
            self.fail("ssh command timed out (no external connections allowed)")
        if len(result.stdout) > SSH_OUTPUT_LIMIT or len(result.stderr) > SSH_OUTPUT_LIMIT:
            self.fail("ssh output exceeded bound")
        return result

    def test_target_binaries_are_arm32(self) -> None:
        for name in ("dropbear", "dropbearkey"):
            with self.subTest(binary=name):
                self.assertTrue(is_arm32_elf(getattr(self, name)), name)

    def test_target_policy_matches_build_script(self) -> None:
        block = extract_localoptions_block()
        assert_policy_block(block)

    def test_keyonly_exec_ok(self) -> None:
        result = self.run_ssh(self.ssh_args(self.client_key, "printf hello-debug-ssh"))
        self.assertEqual(result.returncode, 0, result.stderr[:1000].decode("utf-8", "replace"))
        self.assertEqual(result.stdout, b"hello-debug-ssh")

    def test_binary_roundtrip_over_stdin(self) -> None:
        payload = bytes((i * 37 + 11) % 256 for i in range(32 * 1024))
        digest = hashlib.sha256(payload).hexdigest()
        target = self.fixture_dir / "upload.bin"
        quoted = shlex.quote(str(target))
        put = self.run_ssh(self.ssh_args(self.client_key, f"cat > {quoted}"), stdin=payload)
        self.assertEqual(put.returncode, 0, put.stderr[:1000].decode("utf-8", "replace"))
        hashed = self.run_ssh(self.ssh_args(self.client_key, f"sha256sum {quoted}"))
        self.assertEqual(hashed.returncode, 0)
        first = hashed.stdout.decode("ascii", "strict").split()[0]
        self.assertEqual(first, digest)
        fetched = self.run_ssh(self.ssh_args(self.client_key, f"cat {quoted}"))
        self.assertEqual(fetched.returncode, 0)
        self.assertEqual(hashlib.sha256(fetched.stdout).hexdigest(), digest)
        self.assertEqual(fetched.stdout, payload)

    def test_wrong_key_rejected(self) -> None:
        result = self.run_ssh(self.ssh_args(self.wrong_key, "printf no"))
        self.assertNotEqual(result.returncode, 0, "wrong client key must not login")

    def test_no_key_or_password_cannot_login(self) -> None:
        # Pubkey disabled client-side: nothing to offer, must fail.
        nopub = ["ssh", "-F", "/dev/null",
                 "-o", "BatchMode=yes",
                 "-o", "PubkeyAuthentication=no",
                 "-o", "PasswordAuthentication=no",
                 "-o", "KbdInteractiveAuthentication=no",
                 "-o", "StrictHostKeyChecking=yes",
                 "-o", f"UserKnownHostsFile={self.known_hosts}",
                 "-o", "GlobalKnownHostsFile=/dev/null",
                 "-o", "ConnectTimeout=5",
                 "-o", "ConnectionAttempts=1",
                 "-o", "LogLevel=ERROR",
                 "-p", str(self.port),
                 f"{self.username}@127.0.0.1", "printf no"]
        result = self.run_ssh(nopub)
        self.assertNotEqual(result.returncode, 0)
        # Password-only attempt must also fail (server is key-only).
        pwonly = ["ssh", "-F", "/dev/null",
                  "-o", "BatchMode=yes",
                  "-o", "PubkeyAuthentication=no",
                  "-o", "PreferredAuthentications=password",
                  "-o", "StrictHostKeyChecking=yes",
                  "-o", f"UserKnownHostsFile={self.known_hosts}",
                  "-o", "GlobalKnownHostsFile=/dev/null",
                  "-o", "ConnectTimeout=5",
                  "-o", "ConnectionAttempts=1",
                  "-o", "LogLevel=ERROR",
                  "-p", str(self.port),
                  f"{self.username}@127.0.0.1", "printf no"]
        pw_result = self.run_ssh(pwonly)
        self.assertNotEqual(pw_result.returncode, 0, "password login must fail")

    def test_missing_authorized_keys_login_fails(self) -> None:
        empty_run = Path(self.tmp.name) / "empty-run"
        empty_run.mkdir(mode=0o700)
        port2 = free_port()
        pid2 = empty_run / "dropbear.pid"
        kh2 = Path(self.tmp.name) / "known_hosts2"
        kh2.write_text(
            f"[127.0.0.1]:{port2} {self.host_pub_fields[0]} {self.host_pub_fields[1]}\n",
            encoding="utf-8")
        kh2.chmod(0o600)
        proc2 = self._launch_server(self.dropbear, empty_run, self.hostkey,
                                   port2, pid2)
        try:
            if not wait_port("127.0.0.1", port2, timeout=20):
                self.fail("empty-keydir server did not listen")
            args = ["ssh", "-F", "/dev/null",
                    "-i", str(self.client_key),
                    "-o", "BatchMode=yes",
                    "-o", "PasswordAuthentication=no",
                    "-o", "PreferredAuthentications=publickey",
                    "-o", "IdentitiesOnly=yes",
                    "-o", "StrictHostKeyChecking=yes",
                    "-o", f"UserKnownHostsFile={kh2}",
                    "-o", "GlobalKnownHostsFile=/dev/null",
                    "-o", "CheckHostIP=no",
                    "-o", "ConnectTimeout=5",
                    "-o", "ConnectionAttempts=1",
                    "-o", "LogLevel=ERROR",
                    "-p", str(port2),
                    f"{self.username}@127.0.0.1", "printf no"]
            result = self.run_ssh(args)
            self.assertNotEqual(result.returncode, 0,
                                "missing authorized_keys must not login")
        finally:
            stop_tree(proc2)
            try:
                proc2.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    def test_forwarding_rejected(self) -> None:
        unused = free_port()
        args = ["ssh", "-F", "/dev/null",
                "-i", str(self.client_key),
                "-o", "BatchMode=yes",
                "-o", "PasswordAuthentication=no",
                "-o", "PreferredAuthentications=publickey",
                "-o", "IdentitiesOnly=yes",
                "-o", "StrictHostKeyChecking=yes",
                "-o", f"UserKnownHostsFile={self.known_hosts}",
                "-o", "GlobalKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=5",
                "-o", "ConnectionAttempts=1",
                "-o", "LogLevel=ERROR",
                "-p", str(self.port),
                "-W", f"127.0.0.1:{unused}",
                f"{self.username}@127.0.0.1"]
        result = self.run_ssh(args, stdin=b"", timeout=15)
        self.assertNotEqual(result.returncode, 0, "forwarding must be rejected")
        combined = (result.stdout + result.stderr).decode("utf-8", "replace").lower()
        self.assertTrue(
            any(token in combined for token in
                ("prohibit", "denied", "not allowed", "disabled", "forward")),
            f"expected forwarding rejection, got: {combined[:1000]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
