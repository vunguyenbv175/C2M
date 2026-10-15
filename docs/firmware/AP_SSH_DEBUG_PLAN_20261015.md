# Owner-approved AP SSH debug channel — 2026-10-15

## Purpose and current state

Owner requested faster Wi-Fi debugging instead of repeated SD/flash cycles,
then explicitly approved creating a dedicated C2M SSH key. This is an owner-
private developer build, not an unauthenticated production remote shell.

Current camera access is HTTP/CGI/status only; no working SSH/Telnet login is
established. Stock firmware contains dormant OpenSSH 5.6p1, which is too old
to enable with its default configuration/shared stock keys. The proposed
new debug bundle uses pinned **Dropbear 2026.94** instead.

Source/build/package/tests have passed on source `d5bb236`:
- General CI `38755971989`: SUCCESS.
- Native real SSH `38756257980`: SUCCESS.
- Private firmware CI `38756253160`: SUCCESS, including actual ARM/QEMU SSH
  exec/binary roundtrip, wrong-key/no-key/password/cross-UID rejection and
  authenticated forwarding rejection, then deep validation/preservation.

Nothing here means the camera already has a new listener, has been flashed,
or has accepted SSH. Camera Wi-Fi remains disconnected; ask before a
hardware session.

## Dedicated owner key

Owner-approved local key:
`C:\Users\DrVu\.ssh\c2m_debug_ed25519_20261015`.
The private key stays on the laptop, protected by its user ACL; it is never
copied to firmware, a repository, a release, a report, or CI. It is an
unencrypted dedicated developer key, not the owner's GitHub key.

Only its normalized LF public-key file is held in private vault asset
`assets/debug/debug_owner.pub`. Its SHA-256 pin is
`08517bcf7b737d76ff1dcc2c5ef0fc8f2005bf2d12a475f5be606e53a924f36d`.
Client public-key fingerprint:
`SHA256:wmezIeFclcvv76KNyTscnou8MLfikFic25ShKRv8MvU`.
This is the **client key** fingerprint, not the future camera host key.

## Device scope

- Separate native `c2m-debug` supervisor and low-priority boot launcher.
- Dropbear server and key generator installed only as explicit allowlisted
  `/customer/c2m` assets; no stock SSH, passwd, shadow or calibration edits.
- Listen only on verified stock AP `wlan0`, IPv4 `192.168.1.1`, port2222;
  bind both address and interface. No wildcard/WAN/STA listener, route,
  firewall, AP/STA mode change, or inbound tunnel.
- The stock rootfs lacks `libnss_files.so.2`, which glibc2.30 needs for
  normal passwd/group lookups. Copy its exact existing customer-image bytes
  to the protected debug asset directory as0644; pin SHA-256
  `381a2aa8348259f1722aa09a90c4345a4460a94350d60b1df6782b3dc23ebffd`.
  Set only the fixed loader path `/customer/c2m:/lib`, never the writable
  stock SSH library directory. No custom account parser or auth bypass.
- Public-key-only authentication; password/PAM and forwarding compiled out.
  A restrictive same-UID source patch prevents the owner key from authorizing
  other accounts; normal Linux multi-user kernel support remains enabled.
  Upstream key-file checks accept only the supervisor's exact known `/tmp`
  ancestor policy, never arbitrary writable parents or a writable key file.
- Stock-directory trust is explicitly limited to fixed vendor paths/UIDs:
  hash-verified EN rootfs CPIO records `tmp`, `var`, `customer` as
  `0775 1001:1001`; rebuilt customer root may be `0755 1001:1001`. These
  vendor UIDs are trusted as part of existing root-run firmware, not treated
  as hostile multi-user accounts. Private debug leaf directories must still
  be root-owned0700, and `/customer/c2m` exact `0755 1001:1001`; no global
  stock-directory chmod or ownership rewrite is used to make debug work.
- Host key generated once into a new private config directory. Do not use
  fleet-shared stock host keys. Pin its real cryptographic fingerprint at
  first owner-controlled connection; the supervisor's short FNV correlation
  value is not a cryptographic host-key pin.
- Boot debug window is finite. Listener shutdown does not guarantee killing
  owner commands that detach themselves; do not launch uncontrolled daemons.
- No camera `:8080` diagnostic WebSocket connection while M4 is attached.
  Receiving another client's stream there can disrupt M4's native status.

The root debug shell is intentionally powerful for the owner. Authentication
and AP scoping do not make arbitrary shell commands harmless. Agent defaults
remain read-only: inventory/logs, then bounded reviewed RAM tests. Do not
format storage, rewrite firmware/config, change GPS UART ownership, suppress
ADAS, or inject M4 warnings/audio as a shortcut.

## One flash, then RAM iteration

1. Build ARM loader/ABI-gated debug assets and execute exact stock-rootfs
   QEMU self-tests/key generation. Run native real SSH positive/negative
   authentication and fixture-supervisor tests on loopback only.
2. Private firmware workflow must pin the public owner key and include exactly
   five debug service files (including the byte-pinned stock glibc NSS module)
   plus that public key. Preserve EN core, C audio,
   D3.1 Wi-Fi protections, D4 advisory scope and Bluetooth V2 inventory.
3. Deep-validate and final-extract the actual updater payload before staging.
   CI stock-token packages are not flash-ready. Reidentify the updater card;
   never put updater files on the MINIEYE recording card.
4. Owner performs the single approved flash. With camera stationary, join its
   AP, bind laptop requests to the camera-facing interface, verify stock UUID,
   and verify/pin SSH host identity before sending commands.
5. Use SSH exec/stdin/stdout to upload a small trusted executable to `/tmp`,
   check its hash, run with timeout/low priority, and retrieve results. SFTP/SCP
   is not assumed available; an SSH stream is sufficient and avoids adding a
   file-server subsystem.
6. Keep each RAM test independent from stock recorder/ADAS processes. Use
   results to resolve nl80211 capability parsing and M4/TSR routing before
   proposing persistent changes. Bluetooth remains passive until a separate
   transport is proven safe.

## Local preparation evidence (not staged, not hardware accepted)

- Private vault release: `deliverables/20261015-d4-debug-r38756253160`,
  vault commit `6889a85`; source/public evidence pinned to `d5bb236`.
- Retrieved TAR and all ten release-member SHA-256 checks passed locally.
- Reserved local updater token `20261015000001` applied with the fail-closed
  version-only repacker; all payloads, commands, padding/footer and stock
  second-stage script unchanged. Four local payload files read back exactly.
- Local final package in `build/candidate-d4-debug-final-r38756253160/`:
  TAR SHA-256 `b1843c57e852827e26446215df17c79b84c4add66f4a63c3acc456d86d45a3d3`;
  inner SHA-256 `4aec53d0b64d5e54aad6b7ddd6c4fe932f21872f102c9fcc746b2bb0f8f797be`.
- Final local deep validator: VALID,33/33. Customer re-extracted from that
  exact inner image; all227 stock paths checked with zero unallowlisted
  changes. Directory size/mtime are documented rebuild artifacts; identity
  mode/uid/gid still checked. Fourteen runtime assets directly extracted.
- All eight VI WAVs, `/minieye/adas/md5sum.txt` and the experimental TSR boot
  profile remain byte-identical to the prior D3.1 reference. EN cardv/ADAS
  protected hashes remain fixed. D3 boot is unchanged; probe expands toV2.
- No firmware copied to any card, no camera connection, no flash. Reidentify
  the distinct updater media before writing; never stage on MINIEYE.

## Promotion criteria

A successful CI build is not a physical SSH/AP, Bluetooth, M4 or STA test.
Before calling this channel usable: correct camera identity; modern SSH
handshake and verified host fingerprint; dedicated key accepted, wrong key
rejected; password auth/forwarding unavailable; bounded RAM roundtrip; AP/
recording/GPS/ADAS still healthy; listener expiry/AP-loss behavior observed.
