# RTL8821CS offline compilation lab — 2026-10-18

## Purpose

Perform an actual Linux out-of-tree module compilation, not just preprocessing, using public source. The local Windows host has no WSL/Linux container build environment; the owner-requested experiment uses a GitHub Actions Ubuntu runner, initially triggered by an explicit research-branch push. Manual dispatch is available only subject to GitHub's default-branch workflow registration; the job itself is restricted to the research branch.

**Every resulting module is research-only and must NOT be loaded onto the camera.** Upstream Linux4.9.227 with reconstructed configuration is not the vendor Mercury6 kernel ABI. Equal release/vermagic/symbol names do not prove vendor struct layout compatibility.

## Inputs and output boundary

- Public driver pin and hashes: [source provenance](RTL8821CS_SOURCE_PROVENANCE_20261018.md).
- Public upstream Linux4.9.227 release: archive SHA-256 `38c485b411a14e825f8a66a5c2e64f1480397325a5f692b4929f68d228070c5f`, cross-checked against kernel.org's HTTPS-published `sha256sums.asc`. PGP signature verification was not performed; do not describe this as an authenticated signing-key verification.
- Ubuntu ARM cross-compiler; report actual version, never claim the vendor GCC9.1.0 toolchain was reproduced.
- Separate one-interface baseline and same-channel concurrent profiles; remove unrelated Rockchip/Android default platform block.
- No camera access, firmware/private SDK/config/audio/database/key inputs, module loading, AP changes or flash package creation.
- Only metadata, hashes and public-source build logs may be uploaded as artifacts. `.ko`, kernel trees, source archives and flash images are not artifact outputs.

## Interpretation

A successful compile proves only that the selected public sources can produce a module against the selected upstream header/config set. A failure is useful evidence of toolchain/header/source mismatches and must be reported honestly rather than bypassed by forcing module metadata.

Before a camera candidate: obtain/validate the vendor ABI, assess a baseline build against the stock module, establish AP-independent recovery, then separately review a narrowly controlled driver test. This lab authorizes none of those live actions.

## Execution status

First actual build **passed**: [GitHub Actions39099821245](https://github.com/vunguyenbv175/C2M/actions/runs/39099821245), branch `lab/rtl8821cs-offline-20261018`, source commit `9de8d9c`, job duration3m58s. Both baseline and concurrent modules compiled. Report/downloaded metadata verified locally; no module binary was uploaded or transferred to the camera.

| Variant | Bytes | SHA-256 |
|---|---:|---|
| baseline | 2,837,060 | `04508f36c9b4d9f481f9a921ada5223d491802e5ef5dc4ce3fdb2c00e507a119` |
| concurrent | 2,860,660 | `5a97ff8e51145e038dfd33b40b579dc4f4584c512013c4204a59a361ed6a07b3` |

Both report the same release/vermagic string as stock and218 undefined symbols versus stock219. **This is a compilation success, not an ABI acceptance.**

Compared with stock, both add undefined symbols `__memzero`, `register_inet6addr_notifier`, `unregister_inet6addr_notifier`; both omit `__raw_spin_lock_init`, `__stack_chk_fail`, `__stack_chk_guard`, `mutex_destroy`. Dependency text is empty instead of cfg80211/mmc_core because this header-preparation-only lab has not built a kernel export database; no symbol-version CRCs exist in either case, so that axis supplies no safety proof.

The reconstructed config retained `CONFIG_CFG80211_WEXT=y` but did not retain expected `CONFIG_WIRELESS_EXT=y`; the report explicitly lists this mismatch. Compiler warnings include address comparisons and enum/integer mismatch in vendor code; they were logged, not silently removed. Section sizes differ from stock, including baseline .text69,148 bytes smaller and .bss14,568 bytes smaller. These differences need investigation before any further candidate claim.

The independent general CI run39099821238 failed because the newly added metadata test imported pyelftools before that CI job installed it; the module-lab job installed its dependency and passed. The general CI dependency list is corrected separately; do not conflate that test-environment failure with a failed driver compile.

Next work is to identify which config/compiler choices explain the baseline symbol/layout deltas, then run a separately recorded offline iteration. The produced modules remain **NO_LOAD_EVER_FROM_THIS_LAB**.
