# Recording-card format check — D3 static finding — 2026-10-14

## Conclusion

Do **not** add only `Normal/Event/Photo` directories to the updater image or
D3 boot hook. That cannot reliably prevent the camera's format prompt:
`cardv` checks the mounted recording card and uses the hidden root marker
`/mnt/mmc/.MINIEYE` in `StorageCheckFormatFile(unsigned int)` before the
post-start customer hook is a useful repair point. A customer hook that runs
after cardv cannot change an earlier format decision.

The existing 59GB MINIEYE recording-card inventory already contained:

```text
.MINIEYE                 zero-byte root marker
Normal/
Event/.sstar.format      zero-byte DCF marker
Photo/.sstar.format      zero-byte DCF marker
System Volume Information/
Normal/F/REC-*.mp4       recorder output
```

This inventory was read-only and is stored in
`C2M_HW_20261012/03_candidate_B/recording_card_20261013_201634/inventory.json`.
No recording card was modified by this investigation.

## Static evidence

EN `cardv` SHA256:
`344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c`.
The exported function `_Z22StorageCheckFormatFilej` is at Thumb VA
`0x80a81`; its code resolves the literal `/mnt/mmc/.MINIEYE` and has explicit
open/create/error paths for that marker. `StorageMount` at Thumb VA `0x81679`
calls this checker after mount. Therefore late creation from `/customer` is
not a safe prevention mechanism.

`libDCF.so` SHA256:
`e33e3d7f04c6a0fccb6b55958a091a36514dd2c4e541b78e04985e27afcef318`.
Its strings show DCF path templates under `/mnt/mmc` and the markers:

```text
%s/%s/.sstar.formatfree
%s/%s/.sstar.format
Normal / REC / F
Event / SOS
Photo / IMG
```

These are recorder-managed DCF database/free-space markers. Their exact
contents, attributes and lifecycle are not proven safe to synthesize merely by
creating empty files. `Normal/F`, `Event/SOS` and `Photo/IMG` are recorder
subdirectories, not a complete independent format contract.

## D3 decision

D3 remains unchanged. It does not create or modify recording-card folders,
`.MINIEYE`, `.sstar.format`, DCF state, or video files. This avoids a race with
`cardv`, avoids masking a real filesystem/format problem, and preserves the
read-only/no-format safety requirement.

After the owner manually flashes D3, the correct test is:

1. Boot with stable power and wait for live view.
2. Insert/use the 59GB MINIEYE recording card and observe whether the official
   recorder still asks for format.
3. If it asks, **do not accept format**. Power down/preserve the card and read
   only its root markers, filesystem, dirty state and D3 diagnostics.
4. If it does not ask, verify new normal recording, event/photo paths and
   marker creation over several minutes.

A true format-prompt fix would require proving the exact `cardv`/DCF marker
contract or fixing the card/filesystem, not adding guessed folders in the
firmware package. No such write is authorized by this finding.
