# tools/wifi — isolated read-only nl80211 probe

`c2m_nlprobe.c` is a standalone diagnostic, not the production controller
(`fw/d3/wifi_control.c` untouched). Fixed `wlan0` only.

Validation status: `linux_live_validated=no`. Portable `--self-test` only is
validated on this host. The Linux live path is NOT validated here and is NOT
hardware-ready. Linux compile/self-test CI
(`.github/workflows/nlprobe-linux.yml`) must pass, followed by exact target ARM
ABI gates and pure stock-userspace/QEMU tests before any `/tmp` RAM use.
Host compilation is not validation of live nl80211 behavior.

## Allowed commands only

* `CTRL_CMD_GETFAMILY` (`nl80211` resolve)
* `NL80211_CMD_GET_INTERFACE` (fixed `wlan0` ifindex)
* `NL80211_CMD_GET_WIPHY` (single non-dump, or explicit dump)

No `NEW/SET/DEL_INTERFACE` sends, no scan, no VIF create/delete, no state
ioctls, no supplicant, no routes/firewall/config writes.

## Modes (explicit)

* `--get-interface` — non-dump interface query
* `--get-wiphy` — non-dump wiphy query (single reply + ACK)
* `--get-wiphy-dump` — dump query (`NLM_F_DUMP`, multi-reply + DONE)
* `--get-wiphy-split-dump` — dump with `SPLIT_WIPHY_DUMP` flag (enum, used
  directly; no `#ifdef` on the enum)
* `--all` — family + interface + single wiphy only (never a dump)
* `--self-test` — pure fixtures, no socket/files/clock
* `--help`

Single vs dump vs split-dump print distinct `mode=` lines so behavioural
differences stay observable. Single replies always emit granular
`stage=`/`detail=` (missing maxnum/channels/limits, duplicates, truncation,
wrong phy, bi-match, freq) plus pre-summary counters and bounded combo
output even on failure.

## Privacy and verdict rule

Namespace-aware structural metadata only. Numeric values print ONLY inside
their known hierarchy (top `WIPHY`, combo `MAXNUM`/`NUM_CHANNELS`, limit
`MAX`). Other nested blobs (bands, supported-commands, etc.) are summarized
as `value=redacted`, never recursed, never `u32`-printed even on type-number
collision (notably 1/2). Known combo containers parse by schema even if an
old driver omits `NLA_F_NESTED`; arbitrary blobs never parse by flag alone.

Absent, truncated, or malformed combinations always print
`concurrency=unknown_not_inferred`. Never support conclusions.

## Bounds

recv 65536, send 4096, timeout 1500 ms, attrs 128/level, depth 4,
replies 1 single / 64 dump, combos 64, limits 32, output 200 lines /
8192 bytes. Wiphy output is top headers plus combo subtree only; a final
`combos_summary` is always emitted.

## Host build/test (no firmware, no camera)

```sh
sh tools/wifi/build_nlprobe.sh --out /tmp/nlprobe-host
python3 tools/wifi/test_c2m_nlprobe.py
```

Tests never run `--get-*`. Linux CI compiles the actual Linux code path but
executes only pure fixtures, so it does not establish live netlink behavior.
Portable ABI constants are cross-checked at compile time against Linux build
headers; reference: Linux v4.9
[`include/uapi/linux/nl80211.h`](https://github.com/torvalds/linux/blob/v4.9/include/uapi/linux/nl80211.h).
Notably `INTERFACE_COMBINATIONS=120`, `SPLIT_WIPHY_DUMP=174`,
`SUPPORTED_COMMANDS=50`, `SSID=52`; fixture IDs must not merely agree with
incorrect self-defined constants.

## Later on-camera RAM use (delayed)

Do not run until stationary plus recording/app/audio confirmation via the
normal status routes.

When approved, use only the existing AP SSH exec/stdin/stdout channel:

1. Build the actual ARMv7 hard-float ELF with stock loader/glibc gates; do not
   upload the Windows or Linux x86 host self-test binary.
2. Reverify camera UUID, source interface and pinned SSH host key. Confirm
   stationary vehicle and recording/app/audio health.
3. Create a fresh random, private `0700` directory on `/tmp` using exclusive
   creation; never reuse a predictable path or follow existing links.
4. Stream the checked binary into that directory, verify length/SHA-256 before
   granting execute permission, then run pure `--self-test` first.
5. Run `timeout -t 10 nice -n 10 "$private_dir/c2m-nlprobe" --get-interface`,
   then `--get-wiphy`; request dump/split-dump separately only if needed.
6. Stream results back to the owner laptop. A trap must remove only the exact
   files created by this test and its private directory; verify cleanup.
   Never use broad deletion such as `/tmp/nlprobe*.txt`.
7. Recheck AP and recording health. Do not extend/restart the finite debug
   listener or create an extra cardv `:8080` observer to continue testing.

`/tmp` only. Keep `wlan0` AP up. No persistent install.
