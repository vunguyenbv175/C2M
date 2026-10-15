# Owner-approved AP SSH debug channel — 2026-10-15

## Purpose and current state

Owner requested faster Wi-Fi debugging instead of repeated SD/flash cycles,
then explicitly approved creating a dedicated C2M SSH key. This is an owner-
private developer build, not an unauthenticated production remote shell.

Current camera access is HTTP/CGI/status only; no working SSH/Telnet login is
established. Stock firmware contains dormant OpenSSH 5.6p1, which is too old
to enable with its default configuration/shared stock keys. The proposed
new debug bundle uses pinned **Dropbear 2026.94** instead.

Source/build/package/tests are being integrated. Nothing here means the
camera already has a new listener, has been flashed, or has accepted SSH.
Camera Wi-Fi remains disconnected; ask before a hardware session.

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
- Public-key-only authentication; password/PAM and forwarding compiled out.
  Single-UID server prevents the owner key from authorizing other accounts.
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
   four debug service files plus that public key. Preserve EN core, C audio,
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

## Promotion criteria

A successful CI build is not a physical SSH/AP, Bluetooth, M4 or STA test.
Before calling this channel usable: correct camera identity; modern SSH
handshake and verified host fingerprint; dedicated key accepted, wrong key
rejected; password auth/forwarding unavailable; bounded RAM roundtrip; AP/
recording/GPS/ADAS still healthy; listener expiry/AP-loss behavior observed.
