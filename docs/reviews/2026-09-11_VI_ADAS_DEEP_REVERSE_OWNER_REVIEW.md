# Owner Review — VI ADAS Deep Reverse Evidence

Reviewed commit: `f91afdb090df60bcc571970b0faf7cff3d5b28ad`

## Verdict

**PASS — evidence/reverse-analysis quality.**

**PARTIAL — root cause remains unproven.**

The commit contains exactly the seven intended files and no unrelated changes. The analysis correctly avoids promoting hypotheses to causes. Candidate A/B remain untouched.

## Accepted findings

1. EN/VI inputs and key extracted binaries are hash-gated by a fail-closed deterministic generator.
2. Model-weight change is excluded as a primary cause: all six embedded model blobs are identical.
3. `m0` stale-offset failure is excluded: VI offsets are self-consistent.
4. `run.sh` and `adas_checkcalib.sh` are byte-identical; script-gate regression is excluded.
5. Compared calibration success/state paths, including `UpdateInstallCalibState(2)`, show no proven semantic EN/VI regression.
6. The visible `raw_adas` producer contract is stable enough to downgrade a deliberate API/endpoint rewrite.
7. Rootfs delta is narrow: `cardv` and `sc7a20.ko` are the meaningful changed rootfs files while the named SigmaStar media user-space stack remains stable.
8. EN and VI kernels are distinct valid uImages; VI adds the 8 MiB `fb` reservation, but no causal overlap/starvation has been proven.
9. Positive root cause remains UNKNOWN.

## Owner classification

- Static analysis: **PASS**
- Evidence integrity: **PASS**
- Scope discipline: **PASS**
- Root-cause confirmation: **NOT YET ACHIEVED**
- Hardware/runtime proof: **NOT PERFORMED**

## Important correction / next static opportunity

The uImage compression byte is `9`. Standard upstream legacy U-Boot compression enums normally cover values such as NONE/GZIP/BZIP2/LZMA/LZO/LZ4; therefore treating `9` as ordinary zlib is incorrect. The current report appropriately calls the payload opaque, but the next highest-value static task is not generic decompressor guessing.

Because the vendor U-Boot must understand the kernel image it boots, reverse the **EN and VI U-Boot decompression path** to identify what compression/packing algorithm vendor value `9` means, recover or reproduce the decoder, and then decompress both kernels for semantic diff.

Target chain:

`uImage ih_comp=9 -> vendor U-Boot bootm/decompress dispatch -> decoder -> decompressed ARM Linux image -> config/DTB/media-driver comparison`

This has higher information gain than another broad userspace pass.

## Next-task gate

Do not patch VI or build Candidate C. First attempt one bounded static task:

1. Locate U-Boot handling of legacy image compression value `9` in EN and VI `uboot.es`.
2. Identify decoder signature/algorithm and any helper table/function.
3. Reproduce decoder on host if feasible.
4. Decompress both kernels.
5. Compare embedded config, DTB, reserved-memory, CMA/MMA, VIF/ISP/SCL/IPU/media-driver evidence.
6. If decoder cannot be recovered after this bounded pass, stop static work and keep runtime capture as the next discriminator.

## Final status

`VI ADAS REGRESSION: STATIC ROOT CAUSE NARROWED / POSITIVE CAUSE UNKNOWN`
