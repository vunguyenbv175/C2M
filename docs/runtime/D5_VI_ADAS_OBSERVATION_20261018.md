# D5-VI ADAS observation — 2026-10-18

## Current conclusion

**No functional repair has been applied and the reported OFF-on-reopen failure was not reproduced in the final phone capture.** The owner confirmed the two selected warnings still displayed **High (Cao)** after both captured reopens. The available UI choices are Off/Low/Medium/High/Very High, not simple Boolean toggles.

The original report of warnings returning to Off remains an unresolved historical symptom. Driving-load stability and actual emitted collision warnings have not been accepted. Same-APK EN-good/VI-bad behavior is owner-provided comparative evidence, not dismissed by the successful stationary readback.

## Evidence obtained

- Installed C2M files and WAVs:27/27 hash matches; wider ADAS package and CGI:114/114 matches, including the WAV subset. Installed cardv matches original VI.
- Owner-selected save produced source-config change, followed by deliberate ADAS/lane process teardown/relaunch and decoded-config convergence. Calibration hashes unchanged.
- Static original-VI trace proves Config.v2 notification latches config_changed, working loops finish, main returns0, mutualism tears down its group, guard relaunches. Thus the observed save-associated PID replacement is expected configuration application, not by itself a crash.
- Source, decoded file and actual phone HTTP ADAS.config response agree: FCW/HMW true, level3. Other warnings were false0, consistent with owner selecting only two for the test.
- Captured phone GET ADAS.config HTTP200: clean0/OK and496-byte base64 value,372 decoded bytes/19 `--`-prefixed flag lines. No TCP reassembly gaps/conflicting overlaps in the parsed flows. This is the actual phone exchange, not only a laptop-generated GET.
- The bounded phone capture also observed app-generated Setting enter/exit requests. Those were not agent setters. No ADAS.config save was observed during the readback-only capture.
- Passive capture helper was root-reviewed, fixed wlan0/AP/client IPv4/TCP80, non-promiscuous, duration/payload/packet capped. It streamed private packets to laptop only and was stopped/removed from RAM afterward. Raw captures are not in the repository.
- Ten-minute laptop stability monitor:120 successful samples; main ADAS/lane PIDs and four config hashes unchanged. A transient extra same-name cardv process appeared once while the main recorder PID remained. Do not label that a restart. GPS advisory freshness remained0; driving status was not inferred.

## Static comparisons and rejected explanations

- Muse v1 bare-key parser root cause was retracted in [v2 APK report](../reverse/MUSE_UTOUR_GO_ADAS_TOGGLE_ANALYSIS.md). Prefixes are present; its reported offline fixture parses correctly. Owner confirms the same analyzed APK is installed, UTOUR GO6.1.20; USB debugging is prohibited on that phone due banking-app constraints.
- EN/VI modern CGI ADAS.config GET/SET semantics, formats, query parsing and protocol handling compare equivalent. CGI deltas found concern GSensor; returned ADAS version identities differ, protocol remains1.4.0. No proven causal warning-readback difference.
- Checked cardv ADAS presence/calibration/WebSocket paths compare equivalent EN/VI. Process-presence debounce and change-only status emission are shared caveats, not a demonstrated VI-only cause.
- ADAS.enable GET omits a value in firmware, but the analyzed APK does not use it. Generic CGI success0 must not be interpreted as enable=false.
- Numeric install_calib_state1 is accepted by the traced startup logic; no traced FCW/HMW gate requires state2. Do not force calibration success or reset calibration.
- Actual phone ADAS.Adjust response has extra generic nvconf output plus native response, using uppercase Adjust and lowercase adjust. Static origin: nvconf_get prints its value; first-pass suppression excludes ADAS.config but not ADAS.Adjust. This is shared EN/VI behavior, not a proven UI failure cause. GSensor output matches the same side effect. No memory-leak or malformed-calibration claim is warranted.

## Persistence note

App save replaces the full flag blob, omitting the five custom TSR keys. That is a separate persistence issue. The boot-only TSR status ALREADY_APPLIED does not verify the later app-rewritten configuration, and the logger must not silently reapply settings.

## Next diagnostic step

The owner has approved a continuous bounded diagnostic logger on the SD card, independent of the laptop, including future boots. See [continuous diagnostics add-on](CONTINUOUS_DIAGNOSTICS_20261018.md) for implementation status and safety boundaries. No collision-provoking test, fake speed, warning injection, license modification, forced calibration, app reinstall or firmware rollback is authorized by this observation.
