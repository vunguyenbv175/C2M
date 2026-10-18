"""Offline source-contract regressions, not a Linux/device integration test.

Run: python -B fw/diag/test_diag_contract.py
No production logger, network, card, shell or compiler is invoked here.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "continuous_diag.c").read_text(encoding="utf-8")
CORE = (ROOT / "diag_core.h").read_text(encoding="utf-8")
BOOT = (ROOT / "continuous_diag_boot.sh").read_text(encoding="utf-8")
BUILD = (ROOT / "build.ps1").read_text(encoding="utf-8")


def between(start, end):
    return SOURCE.split(start, 1)[1].split(end, 1)[0]


class DiagnosticContract(unittest.TestCase):
    def test_no_network_execution_control_or_unbounded_allocation(self):
        forbidden = (
            "system", "popen", "fork", "vfork", "execve", "execv", "execvp",
            "execl", "execlp", "posix_spawn", "socket", "socketpair", "connect",
            "bind", "listen", "accept", "sendto", "kill", "killpg", "ptrace",
            "ioctl", "mount", "umount", "reboot", "sync", "syncfs", "syscall",
            "shmget", "msgget", "semget", "malloc", "calloc", "realloc",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertNotRegex(SOURCE + CORE, rf"\b{name}\s*\(")
        self.assertNotIn('"/proc/kmsg"', SOURCE)
        self.assertNotIn('"/dev/kmsg"', SOURCE)
        self.assertEqual(re.findall(r"\bklogctl\s*\(\s*(\d+)", SOURCE), ["3"])
        self.assertIn("stopping=1;", between("static void stop_handler", "static int plain"))

    def test_fixed_paths_cli_singleton_and_status(self):
        self.assertIn('#define CARD "/mnt/mmc/C2M_DIAG/continuous"', SOURCE)
        self.assertIn('#define RAM "/tmp/c2m-continuous-diag"', SOURCE)
        main = SOURCE.split("int main(", 1)[1]
        self.assertIn('argc!=2', main)
        self.assertIn('strcmp(argv[1],"--once")', main)
        self.assertIn('strcmp(argv[1],"--run")', main)
        self.assertIn('geteuid()!=0', main)
        self.assertIn('LOCK_EX|LOCK_NB', SOURCE)
        self.assertIn('s.st_uid!=geteuid()', SOURCE)
        self.assertIn('(s.st_mode&0777)!=0600', SOURCE)
        self.assertIn('status.new",O_WRONLY|O_CREAT|O_EXCL', SOURCE)
        self.assertNotIn('unlinkat(d,"lock"', SOURCE)

    def test_card_mount_and_free_space_gate_precede_creation(self):
        append = between("static int append_sample", "static void status_write")
        self.assertLess(append.index("if(!valid_mount())"), append.index('owned_dir(base,"C2M_DIAG"'))
        self.assertLess(append.index("fstatvfs(base"), append.index('owned_dir(base,"C2M_DIAG"'))
        self.assertIn("v.f_bavail*v.f_frsize<32ull*1024*1024", append)
        self.assertEqual(append.count("valid_mount()"), 2)
        self.assertIn('"/proc/%ld/mounts"', SOURCE)
        self.assertIn('a.st_rdev==b.st_dev', SOURCE)
        self.assertIn('S_ISBLK(a.st_mode)', SOURCE)
        self.assertIn('strcmp(path,"/mnt/mmc")', CORE)
        self.assertIn('strcmp(dev,"/dev/mmcblk0")&&strcmp(dev,"/dev/mmcblk0p1")', CORE)
        self.assertIn('!strncmp(opts,"rw,",3)||!strcmp(opts,"rw")', CORE)

    def test_no_follow_regular_single_link_and_namespace_ownership(self):
        self.assertIn('openat(fd,p,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW)', SOURCE)
        self.assertIn('S_ISREG(s.st_mode) && s.st_nlink==1', SOURCE)
        namespace = between("static int namespace_ok", "static int rotate")
        self.assertIn('if(entries)return 0;', namespace)
        self.assertIn('!slot_name(de->d_name)||log_header(dir,de->d_name)!=1', namespace)
        self.assertIn('"owner.v1",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW', namespace)
        self.assertIn('!strcmp(buf,DIAG_MAGIC)', namespace)

    def test_readdir_errno_is_reset_for_every_namespace_iteration(self):
        # Helper calls inside the loop may leave errno nonzero even on success.
        # Clearing once before the loop falsely rejects a valid namespace at EOF.
        namespace = between("static int namespace_ok", "static int rotate")
        self.assertRegex(namespace, r'for\s*\(;;\)\s*\{\s*errno=0;\s*de=readdir\(dp\);\s*if\(!de\)\{if\(errno\)bad=1;break;\}')
        self.assertNotRegex(namespace, r'closedir\(dp\);\s*if\(errno\)')

    def test_bounded_128_mib_rotation_before_append(self):
        self.assertIn('#define DIAG_SLOT_BYTES (8u * 1024u * 1024u)', CORE)
        self.assertIn('for(i=1;i<=15;i++)', SOURCE)
        self.assertEqual(16 * 8 * 1024 * 1024, 128 * 1024 * 1024)
        rotate = between("static int rotate", "static int append_sample")
        self.assertEqual(re.findall(r'unlinkat\(dir,"([^"]+)"', rotate), ["log15.log"])
        self.assertIn('for(i=14;i>=1;i--)', rotate)
        self.assertIn('renameat(dir,"current.log",dir,"log01.log")', rotate)
        append = between("static int append_sample", "static void status_write")
        self.assertLess(append.index("namespace_ok(dir)"), append.index("rotate(dir)"))
        self.assertLess(append.index("needs_rotation("), append.index("write_all(fd,b->s,b->n)"))
        self.assertIn('size>DIAG_SLOT_BYTES || n>DIAG_SLOT_BYTES || size>DIAG_SLOT_BYTES-n', CORE)

    def test_bounded_reads_samples_and_period(self):
        self.assertIn('#define DIAG_CAP 15000u', CORE)
        self.assertIn('#define MAXPROC 128', SOURCE)
        for limit in ('scanned++<4096', 'fdcount<4096', 'rows++<8192', 'char buf[65537]', 'pread(fd,buf,16384,offset)', 'mono+5000'):
            self.assertIn(limit, SOURCE)
        self.assertIn('lines++<64', CORE)
        # Bounds are checked without allocating.
        self.assertIn('(size_t)n >= sizeof(b->s)-b->n', CORE)
        self.assertIn('if(n!=0){close(fd);return -1;}', SOURCE)
        self.assertIn('fsync(fd)', SOURCE)

    def test_privacy_outputs_are_selected_not_raw(self):
        config = between("static void configs", "static void statuses")
        self.assertIn('crc32:%08x,%lld,%lld', config)
        self.assertNotRegex(config, r'add\([^;]*%s')
        recording = between("static void recording_counts", "static long long milliseconds")
        self.assertIn('rec_log_counts=', recording)
        self.assertNotRegex(recording, r'add\([^;]*,buf\b')
        self.assertNotIn('"cmdline"', SOURCE)
        for key in ('"latitude"', '"longitude"', '"speed"', '"sta_ssid"', '"sta_ipv4"', '"key_fp"', '"bind"'):
            self.assertNotIn(key, CORE)
        self.assertIn('numeric&&number(eq,&v)&&v<=UINT32_MAX', CORE)

    def test_launcher_is_owner_opt_in_one_shot_and_passive(self):
        for guard in ('[ -d "$_cfg" ] && [ ! -L "$_cfg" ]', '[ -f "$_cfg/disabled" ] && exit 0', '[ ! -L "$_cfg/disabled" ]', '[ ! -e "$_once" ] && [ ! -L "$_once" ]', 'mkdir "$_once" 2>/dev/null || exit 0'):
            self.assertIn(guard, BOOT)
        self.assertIn('"$_bin" --run </dev/null >/dev/null 2>&1 &', BOOT)
        commands = "\n".join(line for line in BOOT.splitlines() if not line.startswith("#"))
        self.assertNotRegex(commands, r'\b(while|until|kill|killall|reboot|wget|curl|ssh|telnet|nc)\b')
        self.assertNotIn('boot.sh', BOOT)

    def test_exact_zig_target_no_download_or_packaging(self):
        self.assertIn("'0.14.1'", BUILD)
        self.assertIn('-target arm-linux-musleabihf', BUILD)
        self.assertIn('-mcpu=cortex_a5-d32-neon-fp16-vfp4-vfp4d16-vfp4d16sp-vfp4sp-vfp3-vfp3sp+vfp3d16+vfp3d16sp', BUILD)
        self.assertIn('-static -Os -Wall -Wextra -Werror', BUILD)
        self.assertNotRegex(BUILD, r'https?://|Invoke-WebRequest|Start-Process')


if __name__ == "__main__":
    unittest.main(verbosity=2)
