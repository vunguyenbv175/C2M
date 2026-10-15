#ifndef C2M_DEBUG_SUPERVISOR_H
#define C2M_DEBUG_SUPERVISOR_H

/* Dedicated native low-priority SSH debug supervisor for Dropbear 2026.94.
 *
 * Production CLI (camera, ARM glibc 2.30, root only):
 *   /customer/c2m/c2m-debug --serve
 * Fixed production paths (no overrides accepted without --loopback-test):
 *   NSS module  /customer/c2m/libnss_files.so.2 (stock glibc-2.30 bytes,
 *              mutator-pinned; read-only, 0644, single link)
 *   dropbear    /customer/c2m/dropbear
 *   dropbearkey /customer/c2m/dropbearkey
 *   owner pub   /customer/c2m/debug_owner.pub   (ssh-ed25519, one line)
 *   run dir     /tmp/c2m-debug                  (0700 root, authorized_keys 0600)
 *   config dir  /customer/minieye/config/.c2m-debug   (0700 root, new dir only)
 *   hostkey     <config dir>/host_ed25519       (persistent, first-boot only)
 *   status      /tmp/c2m_debug_status           (0600, atomic, fail-closed)
 *   bind        192.168.1.1:2222 on wlan0 only (-p addr:port plus -l wlan0).
 * ANY path/bind/window/poll override flag, including --ap-state-file, is
 * rejected with exit 2 unless --loopback-test is also present, regardless
 * of flag order. Production therefore has no AP bypass path.
 *
 * Build (host test):
 *   cc -std=c99 -O2 -Wall -Wextra -Werror fw/debug/supervisor.c -o c2m-debug
 * Build (camera ARM glibc 2.30, separate build agent):
 *   arm-linux-gnueabihf-gcc -std=c99 -Os -Wall -Wextra \
 *     fw/debug/supervisor.c -o c2m-debug
 * Do not add time64 (_TIME_BITS), libnl, crypto, or shell dependencies.
 * Portable: --help and --self-test compile on Windows (C99, no I/O, and
 *   safe_dir/serve are compiled out there); --serve is Linux-only and
 *   prints unsupported on _WIN32.
 *
 * Dropbear build requirement (parent build agent, NOT this file):
 *   keep DROPBEAR_SVR_MULTIUSER=1 (normal Linux kernel support), and apply
 *   tools/fw/patch_debug_dropbear.py to restrict logins to the server UID
 *   (root). Without that restrictive patch, -D <rundir> could authorize
 *   the owner key for other accounts. No account/key checks are bypassed.
 *   Also disable forwarding in the Dropbear build (no -j/-k reliance alone)
 *   and ship key-only auth (runtime still passes -s -j -k for depth).
 *   Requires a valid root passwd entry/shell (read-only, never modified).
 *
 * Hostkey decision: persistent hostkey in the NEW private config dir only
 * (first boot generates via dropbearkey, later boots reuse atomically with
 * no overwrite). A per-boot tmp hostkey would break SSH TOFU and force a
 * new fingerprint every boot; persistent + fingerprint report in status is
 * the robust operator tradeoff. Temp names are unique per
 * pid+time+counter with up to 32 attempts; a pre-existing temp name is
 * skipped, never unlinked (only the unique name this call reserved is
 * ever removed). Never touches stock hostkeys or /etc/passwd|shadow|ssh.
 *
 * Stock-ancestor trust policy (actual EN rootfs cpio facts, parent doc:
 *   /tmp, /var, /customer at 0775 1001:1001; / has no entry so kernel
 *   default 0755 root:root; customer UBIFS flashes /customer as 0755):
 *   exact known paths /, /tmp, /var, /customer, /customer/minieye,
 *   /customer/minieye/config: /tmp,/var,/customer accept 0775 1001:1001
 *   or 0755 root; /customer additionally 0755 known set (UBIFS fact);
 *   minieye/config 0755/0775 known set; plus the exact package path
 *   /customer/c2m with uid/gid exactly 1001:1001 and mode exactly 0755
 *   (dropbear/dropbearkey/owner-pub install dir; no group/other writes).
 *   These stock UIDs run all
 *   vendor code and are trusted exactly like root-run vendor code here;
 *   they are NOT a security boundary against an arbitrary uid-1001
 *   process: package-asset checks (dropbear/dropbearkey/owner pub) stay
 *   exact (uid 0, euid, or the exact 1000:1000 / 1001:1001 pair, single
 *   link, regular, no group/other writes). Ancestors are always walked
 *   with O_NOFOLLOW (safe_dir, also applied to asset/key parent dirs);
 *   ancestors are never chmodded and intermediate ancestors never created.
 *   The private leaf itself is exactly 0700 owned by euid (root in
 *   production). The supervisor creates only its own leaf dirs.
 *
 * Status honesty (no false active):
 *   starting = owned child forked, listener NOT yet proven (reason
 *     process_running_listener_unverified). active is published ONLY after
 *   the kernel proves OUR child holds the bound listener: /proc/net/tcp
 *   shows bind-addr:port LISTEN and /proc/<childpid>/fd contains that
 *   socket inode. No TCP connect probe is used (no auth-session overhead,
 *   no interference with Dropbear, and a foreign listener on the same
 *   port cannot satisfy the owned-PID fd check). Startup AP readiness is
 *   retried up to 60 s inside the same overall 20-minute cap.
 *
 * Lifetime/limits (documented, not over-promised):
 *   - Supervisor enforces a 20-minute (1200 s) window from serve start
 *     (startup retries included), then SIGTERMs its OWN dropbear process
 *     group (no pkill/killall) and publishes expired. Dropbear -M600
 *     additionally bounds idle sessions.
 *   - Group signals go to -childpid only after verifying, on our still-
 *     unreaped child (no PID reuse possible), that getpgid(child)==child;
 *     otherwise only the single PID is signaled. The supervisor can only
 *     guarantee its owned listener stops. Client commands that
 *     double-fork/setsid out of the group are NOT killed; explicit limit.
 *   - AP gate re-checked during serve; AP loss stops the owned listener
 *     (failed). No routes/firewall changes are ever made.
 *   - dropbear stderr (with -E) goes to /dev/null; no bounded/unbounded
 *     log file is kept and no private key bytes are ever logged.
 *     Supervisor state lives only in the status file; the SSH owner
 *     retrieves their own process output over their session.
 *
 * Test-only overrides (Linux fixtures, never used in production):
 *   --dropbear PATH --dropbearkey PATH --owner-pub PATH --run-dir DIR
 *   --config-dir DIR --status-file FILE --bind ADDR --port N
 *   --window-sec N --poll-ms N --ap-state-file PATH --loopback-test
 * --loopback-test binds 127.0.0.1 (default port 2222, overridable) without
 * touching wlan0/radio, permits non-root (fixtures own their temp dirs),
 * and omits -l wlan0. --ap-state-file contains "up" (valid) or anything
 * else (invalid) to simulate AP change with no radio; it also requires
 * --loopback-test.
 */

#define C2M_DEBUG_DROPBEAR "/customer/c2m/dropbear"
#define C2M_DEBUG_DROPBEARKEY "/customer/c2m/dropbearkey"
#define C2M_DEBUG_NSS_MODULE "/customer/c2m/libnss_files.so.2"
#define C2M_DEBUG_LIBRARY_ENV "LD_LIBRARY_PATH=/customer/c2m:/lib"
#define C2M_DEBUG_NSS_BYTES 361400
#define C2M_DEBUG_OWNER_PUB "/customer/c2m/debug_owner.pub"
#define C2M_DEBUG_RUN_DIR "/tmp/c2m-debug"
#define C2M_DEBUG_CONFIG_DIR "/customer/minieye/config/.c2m-debug"
#define C2M_DEBUG_HOSTKEY_NAME "host_ed25519"
#define C2M_DEBUG_STATUS_FILE "/tmp/c2m_debug_status"
#define C2M_DEBUG_BIND_ADDR "192.168.1.1"
#define C2M_DEBUG_BIND_PORT 2222
#define C2M_DEBUG_IFACE "wlan0"
#define C2M_DEBUG_LOOPBACK_ADDR "127.0.0.1"
#define C2M_DEBUG_WINDOW_SEC 1200
#define C2M_DEBUG_POLL_MS 1000
#define C2M_DEBUG_STARTUP_AP_MS 60000
#define C2M_DEBUG_PROOF_MS 5000
#define C2M_DEBUG_HOSTKEY_TMP_RETRIES 32
#define C2M_DEBUG_OWNER_MAX 2048
#define C2M_DEBUG_STATUS_MAX 8192

int c2m_debug_self_test(void);
/* Pure helper: validate one-line "ssh-ed25519 <base64> [comment]".
 * On success writes 16 lowercase hex FNV-1a of the 32-byte raw key
 * (operator correlation only, never a full key) and returns 0. */
int c2m_debug_parse_owner(const char *line, char fp_out[17]);
/* Pure CLI gate: production (loopback==0) accepts zero overrides; any
 * override flag without --loopback-test is invalid regardless of order.
 * No filesystem or network I/O. Returns nonzero when valid. */
int c2m_debug_cli_valid(int loopback, int any_override, const char *bind,
                        int port, int window_sec, int poll_ms);
/* Pure stock-ancestor table: exact path + uid/gid/mode integers (0755 and
 * 0775 passed as octal literals). Returns nonzero when the ancestor is a
 * known stock fact: / at 0755 root; /tmp,/var at 0775 1001:1001 (actual
 * cpio) or 0755 root; /customer at 0775 1001:1001 (actual cpio) or 0755
 * (UBIFS flash fact + legacy set); minieye/config at 0755/0775 known set;
 * /customer/c2m exact 1001:1001 0755. No filesystem I/O. */
int c2m_debug_stock_path_ok(const char *path, unsigned uid, unsigned gid,
                            unsigned mode);

#endif
