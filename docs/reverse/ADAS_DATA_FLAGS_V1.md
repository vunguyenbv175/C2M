# ADAS Appended Data / Flag Block V1

## Flag block comparison

`tools/fw/extract_tail_flags.py` extracts the appended default `--key=value` block from both ADAS executables.

Result:

```text
EN flags: 121
VI flags: 121
key sets identical: yes
value differences: 1
```

The **only** changed default flag value is `m0`.

Everything else in the parsed default block is identical, including:

```text
enable_vehicle=true
enable_ped=true
enable_lane=true
enable_fcw=true
enable_hmw=true
enable_ldw=true
enable_tsr=false
enable_screen_service=true
sdk_use_msgpack=true
camera_input=ringbuf_vehicle
ringbuf_name=raw_adas
protocol=1.4.0
```

This significantly reduces the likelihood that a visible default flag change explains the VI regression.

## `m0` structure

`m0` is 384 hex characters = 192 bytes = twelve 16-byte blocks.

Comparing EN and VI block-by-block gives an exact alternating pattern:

```text
block 0  changed
block 1  identical
block 2  changed
block 3  identical
block 4  changed
block 5  identical
block 6  changed
block 7  identical
block 8  changed
block 9  identical
block 10 changed
block 11 identical
```

Thus `m0` can also be viewed as six 32-byte records in which the first 16 bytes change and the second 16 bytes remain stable.

The 16-byte blocks do **not** match MD5 hashes of files in the extracted EN/VI customer or rootfs trees.

Do not label `m0` a checksum manifest yet. Plausible classes include integrity/cryptographic metadata, model-package metadata or license/build metadata.

## Appended payload structure clue

The appended high-entropy region begins with a repeated 16-byte pattern. EN repeats the initial pattern for 1312 bytes; VI repeats it for 176 bytes before diverging. Later large regions can align with a systematic offset, indicating internal structure rather than an undifferentiated random blob.

This is compatible with padding/encrypted/protected package data, but the exact format is **UNKNOWN**.

## Next reverse tasks

1. Find all code references to `FLAGS_m0` (`_ZN3fLS8FLAGS_m0B5cxx11E`).
2. Determine whether the executable reads its own appended region.
3. Identify any crypto/protection routines that consume `m0`.
4. Compare overlay boundaries/records using block alignment and longest-common-region analysis.
5. Do not patch `m0` until its validation role is understood.
