# D5-VI: owner-confirmed ADAS OFF display after power cycle — 2026-10-18

## App save interaction — owner clarification

The owner clarified that this app has **no Save button**: navigating Back from the ADAS page saves the settings. Earlier instructions referring to a Save button were incorrect. References below to an owner app save describe the observed ADAS.config setter, not a separate button press. Back navigation must therefore not be treated as read-only or requested casually when the page displays incorrect OFF values. Whether every Back triggers a setter without any edits still needs direct correlation; the owner-reported behavior is sufficient to avoid such navigation during preservation.

## New observation (not a retraction of the earlier successful readback)

The owner powered the camera off and back on, then reported all ADAS selections OFF in the app. Follow-up explicitly confirmed **FCW and HMW both display Off**, with no save/re-enable performed. The earlier observation of High persisting on reopening the app remains valid for that earlier, pre-power-cycle state. This is a new reproduction boundary.

Investigative actions were read-only over the existing strictly pinned AP SSH connection and the established ADAS.config HTTP GET. No setting, service, calibration, license, driver or kernel was changed. Ongoing offline driver-lab work was deprioritized.

## Preserved evidence

Private host snapshot contains the four configuration files, HTTP response and bounded continuous log; none is committed. The initial device uptime was about146 seconds. Logger started naturally with PID1034; status running, card_result0, truncated0. Current ADAS/lane family was present. Presence alone does not establish driving warning health.

Continuous log preserves both boots:

| Boundary | Source config | Decoded config |
|---|---|---|
| Last observed prior boot |640 bytes, CRC32 dd048148 |372 bytes, CRC32 9fbf6d48 |
| New boot, monotonic8.865s |681 bytes, CRC32 64b3a9a5 |still372 bytes, CRC32 9fbf6d48 |
| New boot, monotonic18.865s |681 bytes, CRC32 64b3a9a5 |502 bytes, CRC32 2e073db5 |

Both calibration files retained the same CRCs across the boundary. Logger begins after early boot operations, so it does not timestamp the actual source rewrite itself.

Current decoded file has FCW=true/level3 and HMW=true/level3. Removing exactly the five TSR allowlisted lines from the502-byte decoded content restores372 bytes with SHA-256 `986beebd1a788db7d43f50a2ccdc6f27db617f268e656eb2b43db0d3317bc7d6`, matching the previous verified decoded config. This supports preserved non-TSR configuration, not a camera-side FCW/HMW OFF rewrite.

Installed TSR boot hook hash equals repository `fw/tsr/tsr_profile_boot.sh` (`63b7179bfd3983219f51f91159ce9c730dd84f6ec8c810d1ba31a96c2b91a37d`). Runtime status is `APPLIED_WAIT_STOCK_REDECODE`. The hook adds/restores five TSR keys and invokes stock base64 encoding, explaining the new source representation without attributing it to Wi-Fi research.

## Actual laptop GET regression

Established read-only endpoint: Config.cgi action=get, property ADAS.config, VersionPrototal1.0.1.

- HTTP200, body658 bytes, status0/OK.
- Stored source is681 bytes, nine lines of base64, decodes completely to502 bytes identical to the runtime decoded file.
- The HTTP value, excluding its added final LF, is **exactly the first640 bytes of that681-byte source**.
- Ignoring base64 whitespace, HTTP value decodes to474 bytes, not502; it truncates in the TSR tail. FCW/HMW true3 are still present in that474-byte decoded prefix.
- The first base64 line alone decodes to57 bytes and lacks both FCW/HMW keys. This is a useful discriminator, **not evidence that the APK only reads that first line**.

Thus a boot-associated change in representation/length and an incomplete CGI readback are proven. Subsequent static analysis of the delivered Config.cgi confirmed the fixed-size boundary (see below). Full base64 data/decoded values are private and deliberately omitted.

### Static confirmation of the CGI record boundary

Read-only extraction of delivered Config.cgi matched its manifest:71672 bytes, SHA-256 `b2768de8f22cb5a7b7d5f83810ccee3e7fc77a488b59b223bf2763167ce7abc5`. In ExeCgiCmd, ADAS.config GET calls fread(buf,0x280,1,fp), with the640-byte length loaded at0x146de before the call at0x146e2. The setter similarly writes a640-byte record (length load0x1465e, fwrite0x14662), after dollar-to-equals substitution, and notifies cardv. This confirms both directions' fixed record convention; a getter-only or serialization-only fix must not be assumed to solve the entire round trip.

**Removing base64 wrapping alone is insufficient.** The first502-byte postboot decoded config requires672 base64 characters; the later498-byte all-High config requires664 characters. Both exceed640 even without whitespace. A candidate must preserve license/calibration and non-TSR settings, preserve owner TSR intent, accommodate the actual app parser and setter, and test boot/save/reboot round trips without silent truncation. No candidate is deployed.

## Owner-authorized LDW save during repeat observation

The owner authorized another bounded observation and chose to enable a different warning: LDW at Very High. A subsequent read-only snapshot confirms LDW=true/level4, while FCW/HMW are now false/level0. The source returned to640 bytes and the decoded file is373 bytes. Both calibration file hashes remain unchanged. The earlier post-boot/no-save snapshot had FCW/HMW true3, so these are **two different states separated by an owner app save**; do not describe the newer OFF values as proof boot had disabled them.

The repeat120-second capture completed:88 packets/14,588 bytes, no capture-tail truncation or reported reassembly gaps/conflicts. Its actual phone ADAS.config setter decodes to373 bytes, SHA-256 matching the live decoded file, with LDW=true4 and FCW/HMW=false0. Thus the **whole-blob save of those OFF values is now observed**, not merely inferred. The preceding phone ADAS.config GET returned HTTP200/body658, with the same body hash as the earlier laptop snapshot. Full multiline decoding yields474 bytes retaining FCW/HMW=true3 and a truncated TSR tail; the first-line-only analysis output must not be mistaken for actual APK parsing. A later phone GET returned HTTP200/body518 with the complete373-byte config, LDW=true4/FCW-HMW=false0.

The owner then confirmed LDW still displays Very High on re-entry and the other warnings display Off. This confirms this post-save LDW UI readback, not a post-power-cycle acceptance. The owner subsequently reported all warnings set to High. A read-only pre-drive snapshot confirmed all six warning flags UFCW/SAG/HMW/FCW/LDW/PCW=true with level3 and enable_vehicle=true. Source640 bytes, decoded368 bytes; both calibration hashes unchanged. Logger sample260 was running, card_result0/truncated0; ADAS/lane family present. This verifies saved configuration, not actual warning emission or post-reboot persistence. No further power cycle was requested. Logger was checked running with card_result0/truncated0. No agent setter or repair was performed. Normal-driving observation is not permission to provoke warnings or rely on unverified ADAS.

## Second owner reboot after all-six-High save

The owner then explicitly rebooted and requested another read-only check. At uptime58 seconds, all six runtime flags remained true/level3. Decoding the stored source matched the runtime file exactly. Removing exactly the five TSR lines restored the verified368-byte preboot config SHA-256 `f806d51e9a833d189467461992592e415659edeeda39de1fe5265db68c34c89c`. Thus persistence of those saved warning settings across this reboot is verified, not merely assumed.

The representation/readback defect repeated: source673 bytes, decoded498 bytes, while HTTP200/body658 returned exactly the source's first640 bytes plus final LF. Full multiline decoding of the HTTP value produced474 bytes including all six true3 warning pairs, but an incomplete last line without an equals sign. This new laptop GET is not an observed phone GET or proof of current UI state. If the UI again shows Off, saving it could overwrite the still-correct settings, as captured in the earlier LDW test.

Logger naturally relaunched as PID1117, sample10/card_result0/truncated0. Across boot, its source observation changed at monotonic8.721s and decoded observation converged by18.722s. Both calibration hashes stayed unchanged and ADAS/lane processes were present; no driving-health verdict follows from process presence. No camera mutation was performed in this check.

## Owner normal-driving report: no collision warning heard

The owner later reported having driven during the observation period without hearing a collision warning. This is an owner symptom, not proof a safe, naturally occurring scene crossed the vendor trigger thresholds. No provocative driving test was requested.

Read-only check at uptime1536s found all six flags still true3, current ADAS/lane PIDs2069/2070/2071 (same as the early postboot check), logger running sample306/card_result0/truncated0. The available log tail covers roughly25 minutes of the current boot. After early decoded-file convergence, no further config change appeared in this tail; sampled kernel substring counters were all zero. Vendor-log incremental substring counters for FCW/HMW/etc were zero, but those counters are not guaranteed warning-event telemetry and cannot prove no events occurred. Recorder PID remained640; no driving acceptance is claimed from process presence.

D4 advisory freshness remained0 and its allowlisted current status was waiting_gps. /tmp/car_info exists. This is evidence about the separate C2M advisory consumer, **not proof that vendor ADAS lacked GPS/speed** or that GPS explains the collision-warning symptom. No coordinates, speed history, UART stream, license payload or raw media was displayed. Further context should be requested only when the owner is safely stopped.

## Follow-up GPS hypothesis check

After the owner reported no other warnings and suspected GPS, five bounded read-only samples of the existing regular /tmp/car_info GPS region (offset0x330, length0x1c0) were **entirely zero and unchanged**. No coordinate/speed/UTC values were output or saved. The VI writer layout is independently documented in CANDIDATE_D5_VI_20261016.md:51-55, so this is stronger than the D4 freshness flag alone: that documented UI snapshot currently contains no usable GPS record. It does not establish the state of every vendor internal GPS/ADAS channel or isolate antenna/fix/parser/publication failure.

Two passive /proc/tty/driver/ms_uart counter reads separated by at least3 seconds showed RX advancing on serial1/2 with no observed overrun increase. No UART was opened, configured or attached, and no payload read. These ports have existing cardv users; byte arrival does not identify the data as GPS, prove a satellite fix or prove ADAS speed delivery. GPS/speed gating remains a leading investigation direction, not a confirmed cause or permission to bypass thresholds.

## Causality limits and next check

**Do not call the OFF UI explained yet.** Muse v2 documents Android Base64.DEFAULT accepting whitespace; multiline encoding by itself is not a sufficient explanation. Its reported catch fallback is Medium, not Off. Truncated-tail parsing, transport preprocessing, actual phone response and final UI path must be checked against this new fixture. Previous good372-byte/single-line fixture did not exercise this condition.

The existing owner TSR boot hook is now a relevant compatibility suspect: it restores keys omitted by an app save and expands the source past the observed CGI read boundary. Do not hide that by attributing the problem to generic app behavior. Do not remove TSR intent, change calibration, repair configs or deploy CGI/boot-hook changes without a reviewed, scoped plan.

A subsequent120-second observation using the previously reviewed RAM-only helper completed normally:17 packets,2659 bytes, no capture-tail truncation or reassembly gaps/conflicts. It observed a Setting setter (not an ADAS.config save), plus unrelated302/404 replies, but **no ADAS.config GET**. Thus this attempt did not capture the discriminating phone response; do not substitute the laptop response as proof of what the phone consumed. The helper was removed after completion. User timing versus capture window still needs clarification; caching is not established.

The next discriminating evidence is the exact phone request/response and parser behavior using this post-boot fixture, preserving the no-save state. Any packet observation must remain bounded, AP-only, private, and avoid M4's single-client streams.
