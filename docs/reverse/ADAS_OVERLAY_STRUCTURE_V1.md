# ADAS Appended Payload Structure V1

## Confirmed boundary

The file-backed ELF ends at:

```text
0x1755e4
```

Payload sizes:

```text
EN 10,106,692 bytes
VI 10,124,554 bytes
VI - EN = +17,862 bytes = 0x45c6
```

Both payloads have entropy ~7.9767 bits/byte.

## Exact-anchor mapping

`tools/fw/overlay_anchor_map.py` samples exact 64-byte anchors from EN and searches for the same bytes in VI.

With a 32 KiB sampling stride:

```text
total EN anchors:   309
exactly matched:    306
```

This is important: the payloads are **not completely unrelated encrypted blobs**. Large regions are byte-for-byte identical, separated by changed/inserted/deleted regions.

Dominant EN->VI offset plateaus:

```text
+0x0520   1,312 bytes
+0x16c2   5,826 bytes
+0x3b48  15,176 bytes
+0x3392  13,202 bytes
+0x37ce  14,286 bytes
+0x3c92  15,506 bytes
```

At the plaintext flag tail, VI is shifted by the full file-size delta:

```text
+0x45c6 = +17,862 bytes
```

## Delta transitions

The observed plateau transitions imply multiple independent size changes rather than one single inserted block.

Representative cumulative-delta increments:

```text
0x0000 -> 0x0520 : +1,312
0x0520 -> 0x16c2 : +4,514
0x16c2 -> 0x3b48 : +9,350
0x3b48 -> 0x3392 : -1,974
0x3392 -> 0x37ce : +1,084
0x37ce -> 0x3c92 : +1,220
0x3c92 -> 0x45c6 : +2,356
```

This pattern is consistent with a concatenated resource/package layout where several component payloads changed size.

Do **not** yet label the components as AI models, licenses, or encrypted resources without a parser/header proof.

## Plaintext tail

Both builds expose exactly 121 default `--key=value` flags with identical key sets.

Only one default value differs:

```text
m0
```

All operational defaults relevant to the known ADAS pipeline remain identical, including:

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

## `m0`

`m0` is 192 bytes represented as 384 hex characters. EN/VI comparison shows an alternating 16-byte pattern:

```text
changed 16 bytes
same    16 bytes
changed 16 bytes
same    16 bytes
... repeated six times
```

Its role remains UNKNOWN.

## Next tasks

1. Detect exact common-region boundaries rather than sampled plateaus.
2. Search executable code for readers/validators of the appended payload.
3. Trace `FLAGS_m0` data references through GOT/literal pools.
4. Identify chunk headers or length tables near each plateau transition.
5. Correlate each changed chunk with runtime subsystems using controlled EN-base/VI-adas testing.

## Regression implication

Given the near-identical ADAS call graph and multiple changed payload chunks, the appended data package is now the highest-value static reverse target.
