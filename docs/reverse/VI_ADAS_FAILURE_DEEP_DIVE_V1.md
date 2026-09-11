# VI ADAS Failure Deep Dive V1

## EXECUTIVE VERDICT

Static, read-only evidence does **not** prove one definitive root cause for the EN-working versus VI-non-working ADAS activation regression. The highest-value remaining failure surface is the VI runtime integration boundary: kernel/media/memory behavior, live `raw_adas` frame availability, IPU initialization, and persistent calibration/config state.

Several intuitive explanations are now strongly downgraded or excluded as primary causes. The six embedded model blobs are byte-identical, the visible `cardv` producer contract is unchanged, compared BitAnswer/license implementation paths are byte-identical, and the main ADAS executable retains an almost identical symbol and call surface. The exact VI failure class therefore remains **UNKNOWN** until read-only runtime evidence distinguishes process startup, frame starvation, IPU failure, calibration suppression, and display-only failure.

EN 2023-08-03 remains the golden runtime baseline. VI 2023-09-20 should remain a donor/reference build only. No firmware, Candidate A, Candidate B, binaries, or Candidate C were modified or built during this investigation.

## 1. Scope and evidence policy

Ground truth supplied for the same physical C2M unit:

- EN 2023-08-03: ADAS operated.
- VI 2023-09-20: ADAS did not operate.

Analysis rules:

- Static and read-only only.
- Every unproven causal statement is marked **UNKNOWN**.
- Existing extracted payloads were used where their hashes were reproducible.
- No firmware or extracted proprietary payload is added to source control.
- No binary patching, Candidate C work, Candidate A/B alteration, commit, or push.

Canonical machine-readable evidence is in `docs/reverse/EVIDENCE_VI_ADAS_FAILURE.json`.

## 2. Verified input identity

| Input | Size | SHA-256 |
|---|---:|---|
| EN original TAR | verified by generator | `3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c` |
| VI original TAR | verified by generator | `f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa` |
| EN kernel uImage | 2,255,135 | `c1fa8f7363615f1dc7d91f3308608d336fee6d89f5dcfe48e826bf4a399f5030` |
| VI kernel uImage | 2,255,137 | `8261589e10474885277d59fea0a2ad02e079a5b94661a2f4f8f869be29364314` |
| EN `cardv` | 1,225,780 | `344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c` |
| VI `cardv` | 1,225,780 | `56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23` |
| EN `adas` | 11,636,008 | `0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043` |
| VI `adas` | 11,653,870 | `997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1` |
| EN `sc7a20.ko` | 24,196 | `2d8121dd245d88684a5ece8e5647dfd04571a3184beca2a01fcac7743bbc797a` |
| VI `sc7a20.ko` | 24,204 | `5d020616c2b67909a6bc5db19245bfedaf1301d875ae7c117c4d1888de566d64` |

The deterministic verifier is `tools/fw/vi_adas_failure_evidence.py`. It fails if any expected hash differs.

## 3. Ranked root-cause assessment (required columns)

| RANK | CANDIDATE CAUSE | PROVEN DIFFERENCE | MECHANISM | SUPPORTING EVIDENCE | CONTRADICTING EVIDENCE | CONFIDENCE | NEXT DISCRIMINATING TEST |
|---:|---|---|---|---|---|---|---|
| 1 | VI kernel/media/contiguous-memory or IPU-init behaviour blocks usable frames | Distinct uImage payloads (EN `c1fa8f73…`, VI `8261589e…`, +2 B); VI-only `mmap_reserved=fb,miu=0,sz=0x800000,max_start_off=0x3F000000,max_end_off=0x3F800000`; load/entry both `0x20008000`, CRCs valid | Changed reservation/allocator ordering or VIF/ISP/SCL/IPU driver behaviour starves `raw_adas` or fails `MI_SYS_Init` / `MI_SCL_CreateDevice` / `IPUCreateDevice` at runtime | Kernel is the largest opaque VI delta; userspace media stack is otherwise identical (526/528 rootfs files same) | No config/DTB/allocator/IPU log proves starvation; camera+recording work so sensor path is not grossly broken | UNKNOWN | Read-only EN/VI capture: `cat /proc/cmdline`, `cat /proc/meminfo`, `cat /proc/iomem`, `dmesg`, `lsmod`, `ps` + `MI_*` return codes + `raw_adas` frame counters |
| 2 | Persistent calibration/config accepted differently by VI executable | No script delta (`run.sh` + `adas_checkcalib.sh` byte-identical); updater preserves `/customer/minieye/config` (proven) | Same flag bytes fail VI parser/range/validation branches, or VI requires a new key absent from EN-era files | Startup depends on device-specific `adas.flag`/`calib.flag` decoded to `adas_de`/`calib_de.flag` + `--enable_vehicle` gate | No parser diff proven in compared code; generic image holds placeholder only | UNKNOWN | Private read-only copy+decode of device flags; EN-vs-VI parser matrix on copies; record validation logs, redact secrets |
| 3 | Upstream frame starvation despite unchanged writer helpers | `cardv` builds differ (equal size 1225780, distinct hashes) but `send()` + `adas_minieye_send_frame_task()` normalized code identical; single `raw_adas` token both sides (EN `0xFF340`, VI `0xF5794`) | Sensor/VIF/ISP/SCL setup, CMA allocation, thread-start timing, or startup-order race yields no/tardy/malformed frames to an unchanged writer | Static writer equality does not prove live geometry/stride/timestamps/cadence/mapping/startup order | Call-sequence equality lowers deliberate-rewrite probability; recording works so some camera path flows | UNKNOWN | Capture `cardv`/`adas` threads, `raw_adas` existence, frame metadata (w/h/stride/fmt/seq/ts/fps), allocation errors on EN vs VI |
| 4 | ADAS interstitial package metadata interpretation | 7 non-model gaps sum exactly to `+17862` B (`EN 10117644` → `VI 10135506`); 6 model blobs identical; `m0` self-consistent | Opaque protection/package records gate model loading, feature enable, or calibration via an unidentified reader | Placement around protected blobs is consistent with package/protection metadata | No xref/reader/parser/log ties gaps to activation; BitAnswer compared paths byte-identical | UNKNOWN | Xref search for gap/overlay offsets; `mmap`/`/proc/self/exe` range trace; reversible EN-base + VI-`adas` launch log |
| 5 | Runtime license/custom-info/feature state | None in compared implementation (`Bit_Login`/`Bit_ReadFeature`/`Bit_CheckOutSn`/`Bit_CheckOutFeatures`/`Bit_SetRootPath`/dispatcher byte-identical) | Identical code returns different feature set when fed different UUID/license/feature blobs | License root lives under preserved config dir; device-specific state untested | Implementation delta downgraded by byte-identity of compared paths | LOW | Sanitized login/feature-query return-code capture on EN vs VI; never publish secrets |
| 6 | Display/M4-only failure masking live inference | VI adds `SendGPSSpeedToScreen(int)` + GPS/display/G-sensor/power changes + 8 MiB `fb` reservation; display reportedly normal | Inference runs but warnings/pixels/audio never reach screen/M4, appearing as never-active lane/AI | `cardv` owns many `Send*ToScreen` paths; `MessagePack`/`AdasStatus` layers separate inference from rendering | No evidence inference reaches display boundary in VI | LOW | Classify A–F first; if inference alive, capture `ScreenService`/`MessagePack` traffic + M4 pcap on verified interface |

Excluded causes (do-not-claim list) are in `EVIDENCE_VI_ADAS_FAILURE.json:excluded_causes`: model weights (`CONFIRMED` excluded — 6/6 identical), stale `m0` (`CONFIRMED`), `adas_checkcalib.sh` delta (`CONFIRMED` identical), missing `UpdateInstallCalibState(2)` path (`MEDIUM`), broad lane-algorithm rewrite (`MEDIUM`), `raw_adas` API rewrite/rename (`HIGH-CONFIDENCE` same), M4/display collapse as sole proof (`MEDIUM`).

## 4. Complete payload-diff implications (section A)

Machine-readable table: `EVIDENCE_VI_ADAS_FAILURE.json:payload_diff` (from
`tools/fw/carve_upgrade.py` manifests; outer TAR members hashed directly).
Reproduce with `python tools/fw/vi_adas_failure_evidence.py`.

| payload | EN size | VI size | EN SHA256 | VI SHA256 | same/different |
|---|---:|---:|---|---|---|
| cis.es#0 | 23552 | 23552 | `70a587437182018af328c50fdb7d94663311857bbc14e849cb21c08913584e70` | `70a587437182018af328c50fdb7d94663311857bbc14e849cb21c08913584e70` | same |
| cis.es#1 | 512 | 512 | `5fedff9f36704ec2f51771adc4d5b6ff5d244a24afcfd34548d658579f129be4` | `5fedff9f36704ec2f51771adc4d5b6ff5d244a24afcfd34548d658579f129be4` | same |
| ipl.es#0 | 24960 | 24960 | `78d4ba339b4ba5f892e9a3d5ade44a9125932188acd5e73d093fadba365a2e2e` | `78d4ba339b4ba5f892e9a3d5ade44a9125932188acd5e73d093fadba365a2e2e` | same |
| ipl_cust.es#0 | 24240 | 24240 | `6f892733ff63d4493b8465bfe6a044043ebde25d8f79ba2af1d4aceb5ffb8a6e` | `6f892733ff63d4493b8465bfe6a044043ebde25d8f79ba2af1d4aceb5ffb8a6e` | same |
| uboot.es#0 | 297540 | 297540 | `7c64be8cb848af856a9f107139ee90765be4c3c3bdcd4eb49563839b57304490` | `0e1e13409beaf77e680f5c9c5221ab21d796164dc926715e649ac52457102fd9` | different |
| kernel.es#0 | 2255135 | 2255137 | `c1fa8f7363615f1dc7d91f3308608d336fee6d89f5dcfe48e826bf4a399f5030` | `8261589e10474885277d59fea0a2ad02e079a5b94661a2f4f8f869be29364314` | different |
| rootfs.es#0 | 8658283 | 8655223 | `1dcc3e954910661af2bb36ae6bc53433e378e9b496eaa20717bb7479b4bd3f2b` | `f90f109a29711ad926e8d302df083ef4eb24876bd2c4183c2b5a6f0c16ab6edc` | different |
| miservice.es#0 | 1650688 | 1650688 | `358c01a9e9455a8d0b43587eff8eea754b4df3a538d2974cf8ff714191a16db7` | `db3327bdc33b5b6ac49cf02ad179bc784cec811f6449112117eb9f8d176e84d9` | different |
| customer.es#0 | 39743488 | 39743488 | `b4dabc4d789c758d94313208d57dbec279d394c4d91b6935542242a8b515dd8f` | `7325f9fffa461596273ae30995b4e69d80d380da5aa1cbea0f874e904b599c93` | different |
| misc.es#0 | 2097152 | 2097152 | `c9bbb3850500aae6312bd9bb79bed093d2ded7b9019c76ef2910434e2d6914f8` | `b1aafe49adce7d531b14e90b5ff79053d7d4dc36519660b803c5a2c1537d3be8` | different |
| oneed_cust.es#0 | 3555328 | 3301376 | `f982f15e2d18dc2549ee53617a45c44ea1764c5b84debee634bb75b8edd92a87` | `69bebcf4301bc778e3088dd639dc5b84766436900859c48f0ea2b80af6782915` | different |

Outer TAR: `adas_upgrade.sh` is byte-identical both releases
(`0e18c91fd95f2a2cdf64637448d8540e946ae5bb2e37627d8bbd6bef7f7da05b`, 2972 B);
`sysVer.txt` differs (`sysVer 20230803193750` vs `sysVer 20230920185743`);
`minieye_firmware.md5` differs only because it tracks the inner image hash.
Inner images: EN `58359832` B `e3f2443294f71588…`, VI `58105880` B `9ec1c85ec0d8b69e…`.
Partition layout / `fatload` offsets are unchanged except kernel/rootfs/oneed sizes;
`mtdparts` line is identical. Bootargs differ only by the VI `mmap_reserved=fb…` addition.

The vendor updater layout is unchanged in structure. CIS, IPL, and IPL_CUST payloads are identical, which strongly reduces the probability of an early board-initialization cause. Kernel, rootfs, customer content, U-Boot, and `oneed_cust` contain meaningful deltas.

The rootfs comparison is unusually narrow: 528 files in each image, 526 identical, with content differences limited to `bootconfig/bin/cardv` and `bootconfig/modules/4.9.227/sc7a20.ko`. This concentrates rootfs-side ADAS investigation on `cardv`, IMU behavior, and runtime interaction with the changed kernel rather than a broad userspace replacement.

The customer UBIFS manifests each contain 227 entries with no added or removed path. A content-only comparison identified 34 changed paths. ADAS-relevant changes include the `adas` executable, version/checksum metadata, seven localized audio assets, and version markers. Other changes include rebuilt storage/USB/network modules and web/config resources. Metadata-only owner/mode/mtime drift must not be mistaken for executable semantic change.

## 5. Kernel, media, and memory boundary

The two kernel artifacts are valid legacy uImages with matching load and entry addresses `0x20008000`. Their data CRCs validate. The compressed payloads differ by two bytes:

- EN payload: 2,255,071 bytes, SHA-256 `4c9b8b1ad13cbe8520c7cb18819c1249d22e7733e967f2427e7a7ea87041b665`.
- VI payload: 2,255,073 bytes, SHA-256 `cf9f928dc53bd43dc9253634f86c0a159988907cdb7b537b4cfe16e12810b983`.

VI bootargs add:

```text
mmap_reserved=fb,miu=0,sz=0x800000,max_start_off=0x3F000000,max_end_off=0x3F800000
```

This proves an additional 8 MiB region labeled `fb` is reserved. It does **not** prove memory starvation, overlap, or ADAS impact. Exact kernel configuration and DTB semantic differences remain **UNKNOWN** because no reliable decompressed kernel config/DTB comparison was recovered in this pass.

The front-camera path is documented as IMX415 MIPI and ADAS consumes `ringbuf_vehicle` / `raw_adas` at 1920x1440 and 10 Hz. User-space IPU firmware, model image, and SigmaStar libraries are unchanged, but that does not establish equality of the active kernel-side IPU, SCL, VIF, ISP, sensor, or memory allocation behavior.

See `VI_KERNEL_MEDIA_DIFF_V1.md` for the focused analysis.

## 6. Producer-to-consumer contract

Both `cardv` builds import and use:

```text
CRingBuf::CRingBuf(char const*, char const*, int, int, bool, bool)
CRingBuf::RequestWriteFrame(unsigned int, __FRAME_E, __CRB_WRITE_MODE_E)
CRingBuf::CommitWrite(unsigned int, int*, int*)
```

Within `adas_minieye_send_frame_task(void*)`, both builds retain the `raw_adas` endpoint and the same visible constructor semantics. Normalized code for the high-value producer helpers is identical. A deliberate source-level rewrite of the writer is therefore low probability.

Still **UNKNOWN**:

- Whether VI starts this task.
- Whether upstream frames arrive.
- Actual width, height, stride, pixel format, plane layout, timestamps, and cadence.
- Shared-memory allocation success.
- Producer/consumer startup ordering.
- Whether ADAS opens the same endpoint before timeout.

See `VI_CARDV_RAW_ADAS_DEEP_DIFF_V1.md`.

## 7. Calibration, config, persistent state, and feature gates

`run.sh` is byte-identical in EN and VI:

```text
size: 1584
SHA-256: 796e555a276d849737b8034021e1464a8241ed291a332ef5a61b767d9ab860e4
```

It exits if either `/customer/minieye/config/adas.flag` or `/customer/minieye/config/calib.flag` is absent. It base64-decodes these into `adas_de.flag` and `calib_de.flag`, refreshes decoded files when MD5 values differ, and exits when `--enable_vehicle=false` is present.

`adas_checkcalib.sh` is also byte-identical:

```text
size: 1145
SHA-256: 518f22e98842eb8a6c315d0a29098c885f0d2c942c4690154ddc730034b3d8c4
```

The updater deliberately preserves the configuration directory. Therefore missing generic image defaults do not explain why EN later worked on the same device. However, compatibility of persisted calibration values with VI executable behavior remains **UNKNOWN** because the device files were not available.

See `VI_CALIBRATION_PATH_V1.md`.

## 8. ADAS executable and interstitial metadata

EN and VI expose the same 3,875 named symbols. The only symbol-size change is `_Z10SystemInitj`, from 124 bytes to 100 bytes. Both versions retain `MI_SYS_Init`, `MI_SCL_CreateDevice`, and `IPUCreateDevice`; the observed difference is primarily failure logging.

Call-sequence comparison covered 2,734 functions: 2,731 had the same sequence and three differed. The two same-sized algorithmic differences are consistent with register-allocation noise until proved otherwise. This lowers the likelihood of a broad algorithm rewrite.

The file-backed ELF boundary is `0x172b1c`. The overlays are:

- EN: 10,117,644 bytes, SHA-256 `c395db153a76cd15f6e50ef003ccfa4295ec87dc01e409b0721ae8d4d24c6084`.
- VI: 10,135,506 bytes, SHA-256 `6becae4d9eb413f36d0b8418a747de5fed24d8eec7d7f5f265a54b84201e04f7`.

All six model blobs (`d0`, `v_a`, `v_t`, `p_r`, `road`, `tl`) are byte-identical. Seven interstitial gaps account exactly for the full 17,862-byte size increase. Their exact proprietary meaning and causal role remain **UNKNOWN**.

See `VI_ADAS_PACKAGE_METADATA_V2.md`.

## 9. License and feature gates

The BitAnswer subsystem is real, but static comparison strongly downgrades a changed implementation as the primary explanation. The executable-directory helper, root-path behavior, `Bit_SetRootPath`, `Bit_Login`, `Bit_ReadFeature`, checkout functions, and a tested internal dispatcher are byte-identical.

Open questions are runtime-only:

- Device UUID/custom-info input.
- License material under the persistent config root.
- Feature values selected through indirect dispatch.
- Login and feature-query result codes on EN versus VI.

Without this runtime state, license causality remains **UNKNOWN**.

## 10. Display-path separation

VI adds `SendGPSSpeedToScreen(int)` and contains GPS/display-related refactoring alongside the 8 MiB framebuffer reservation. These are credible VI changes worth understanding and potentially salvaging later.

However, display failure is not equivalent to ADAS activation failure. A correct investigation must separately observe:

1. Process alive.
2. Frames consumed.
3. IPU/model initialized.
4. Inference outputs produced.
5. Warning gates passed.
6. Screen/audio messages emitted and rendered.

Until those layers are observed, “ADAS does not work” cannot distinguish internal failure from invisible output.

## 11. VI changes worth salvaging (section K — classify only, do not implement)

| VI change (source evidence) | Classification | Rationale |
|---|---|---|
| Vietnamese ADAS audio/localization assets (customer UBIFS: 7 localized audio assets; `docs/firmware_en_vi/08_AUDIO_VIETNAM_LOCALIZATION.md`) | SAFE TO PORT (after isolated hash + playback test) | Data-only assets; no code/ABI dependency proven |
| Region-specific web/config labels (customer + `oneed_cust` web/config resources) | SAFE TO PORT (after isolated hash + UI test) | Label/config data; keep EN code paths |
| GPS speed-to-screen support (`SendGPSSpeedToScreen(int)` VI-only symbol; NMEA `BDGSV` parsing changes) | PORT WITH DEPENDENCIES | Needs cardv GPS parser + screen-protocol + display-path validation together |
| Display/HUD refinements (`SendGPSInfoToScreen` resize, display-mode paths) | PORT WITH DEPENDENCIES | Coupled to M4/screen protocol and `fb` reservation behaviour |
| G-sensor sensitivity / power-on-by-interrupt changes (`GsensorSetSensitivitya`, `GsensorSetPowerOnByInt`) | PORT WITH DEPENDENCIES | Coupled to IMU driver (`sc7a20.ko` also changed) and motion-gated ADAS logic |
| Power/restart control strings (`poweroff_ctrl`, `poweroff_mode`, restart handler resize) | DO NOT PORT YET | Safety-relevant; needs hardware power-state testing |
| VI kernel / bootargs `mmap_reserved=fb` / full `cardv` / full ADAS executable / config DB / protection metadata | DO NOT PORT YET | Carries the unresolved regression surface; transplanting defeats EN-golden policy |

Do not transplant VI kernel, bootargs, `cardv`, full ADAS executable, config database, or protection metadata merely to obtain localization. Each donor item must be isolated, hashed, and tested against the EN golden architecture.

## 12. Decisive next evidence

The next device session should classify the failure as exactly one of:

```text
A. ADAS process absent
B. ADAS process starts then crashes/restarts
C. ADAS process alive but raw_adas/frame input absent
D. frames arrive but IPU/model initialization fails
E. inference runs but calibration/feature/warning gates suppress output
F. ADAS runs internally but display/audio output fails
```

Minimum read-only capture:

```sh
cat /proc/cmdline
cat /proc/meminfo
cat /proc/iomem
dmesg
lsmod
ps
ls -l /dev
cat /proc/modules
```

Also capture media/IPU/SCL/VIF/ISP logs, shared-memory objects, process restart history, `raw_adas` frame metadata, and sanitized hashes of persistent config/license files. Do not publish serial numbers or license secrets.

## 13. Exact reproducibility commands

From repository root:

```powershell
python tools\fw\vi_adas_failure_evidence.py
python -m json.tool docs\reverse\EVIDENCE_VI_ADAS_FAILURE.json > $null
```

Rebuild UBIFS manifests without modifying firmware:

```powershell
python tools\fw\ubifs_manifest.py build\carve_en\customer.es.load0.off_00c5d000.size_25e7000.bin -o build\vi_adas_en_customer_manifest.json
python tools\fw\ubifs_manifest.py build\vi_carve\customer.es.load0.off_00c5d000.size_25e7000.bin -o build\vi_adas_vi_customer_manifest.json
```

Extract and verify startup scripts:

```powershell
python tools\fw\ubifs_extract_file.py build\carve_en\customer.es.load0.off_00c5d000.size_25e7000.bin /minieye/adas/run.sh -o build\run_en.sh --report build\run_en.extract.json
python tools\fw\ubifs_extract_file.py build\vi_carve\customer.es.load0.off_00c5d000.size_25e7000.bin /minieye/adas/run.sh -o build\run_vi.sh --report build\run_vi.extract.json
Get-FileHash -Algorithm SHA256 build\run_en.sh,build\run_vi.sh
```

Existing specialized analyses:

```powershell
python tools\fw\cardv_ringbuf_contract.py build\fw_bin_en\cardv build\fw_bin_vi\cardv -o build\cardv_ringbuf_contract.json
python tools\fw\thumb_callgraph_diff.py build\fw_bin_en\adas build\fw_bin_vi\adas
```

The latter commands require their documented ELF/disassembly tool dependencies.

## 14. Cross-references

- `docs/reverse/VI_KERNEL_MEDIA_DIFF_V1.md`
- `docs/reverse/VI_CALIBRATION_PATH_V1.md`
- `docs/reverse/VI_CARDV_RAW_ADAS_DEEP_DIFF_V1.md`
- `docs/reverse/VI_ADAS_PACKAGE_METADATA_V2.md`
- `docs/reverse/EVIDENCE_VI_ADAS_FAILURE.json`
- `docs/reverse/CARDV_RAW_ADAS_CONTRACT_V1.md`
- `docs/reverse/BITANSWER_LICENSE_PATH_V1.md`
- `docs/reverse/ADAS_INTERSTITIAL_GAPS_V1.md`

## 15. Final conclusion

The evidence supports a disciplined negative conclusion: the VI regression is not explained by changed CNN weights, a deliberate visible `raw_adas` writer-contract rewrite, or a broadly rewritten license implementation. The precise positive cause remains **UNKNOWN**.

Kernel/media/memory behavior, live frame production, persistent calibration/config compatibility, and runtime feature/license state are the leading unresolved boundaries. The investigation should remain on the EN golden base and obtain read-only runtime evidence before any firmware engineering decision.