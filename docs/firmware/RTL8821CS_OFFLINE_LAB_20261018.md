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

The original report warned that `CONFIG_WIRELESS_EXT` remained n despite `CONFIG_CFG80211_WEXT=y`. Follow-up source review corrected this expectation: in upstream4.9 the latter selects WEXT_CORE, not the separate promptless legacy WIRELESS_EXT symbol. This warning was a reporting mistake, not a build failure or proof WEXT compatibility was absent. Future reports check WEXT_CORE/WEXT_PROC/PROC_FS instead; the vendor value of the layout-affecting legacy symbol remains unverified. Compiler warnings include address comparisons and enum/integer mismatch in vendor code; they were logged, not silently removed. Section sizes differ from stock, including baseline .text69,148 bytes smaller and .bss14,568 bytes smaller. These differences need investigation before any further candidate claim.

The independent general CI run39099821238 failed because the newly added metadata test imported pyelftools before that CI job installed it; the module-lab job installed its dependency and passed. The general CI dependency list was corrected in `b8e72ac`; subsequent [general CI39100229565](https://github.com/vunguyenbv175/C2M/actions/runs/39100229565) passed. Do not conflate the earlier test-environment failure with a failed driver compile.

Next work is to identify which config/compiler choices explain the baseline symbol/layout deltas, then run a separately recorded offline iteration. The produced modules remain **NO_LOAD_EVER_FROM_THIS_LAB**.

## Iteration2 hypothesis (recorded before execution)

Proposed offline-only config changes: DEBUG_SPINLOCK/DEBUG_MUTEXES enabled, regular stack protector enabled, IPv6 disabled and lockdep allocation disabled. These are hypotheses inferred from stock symbol references, **not recovered vendor config**. The expected outcome is closure of the two IPv6-notifier additions and four stock-only lock/canary references, potentially leaving `__memzero` as the remaining extra symbol. A compiler-emitted layout probe will record actual lock/mutex sizes and constant-zero/variable memset references without executing target code.

Independent static stock-object anchors were checked by the parent directly against the pinned original module: `GLBtcBtMpOperLock`36 bytes (source typedef struct mutex), `GLBtcBtMpRptSema`28 bytes (struct semaphore), `GLBtcBtMpOperTimer`32 bytes (driver timer wrapper). The extra code trace observes spinlock-debug magic in semaphore initialization. These are strong layout clues, not recovery of the entire vendor config or proof every kernel structure matches. In particular, no standalone global spinlock object was available for a direct sizeof measurement; field-attribution models remain hypotheses until compared with emitted layout probes.

Iteration2 was pushed as `424ba90`; [run39101623926](https://github.com/vunguyenbv175/C2M/actions/runs/39101623926) **passed** in3m58s. The parent downloaded and inspected the metadata, not merely workflow status.27 local lab tests passed before the run.

| Variant | Bytes | SHA-256 |
|---|---:|---|
| baseline iteration2 | 2,859,464 | `c39f9ce75961283192c542a4b2c8f9f4be73da28ec3f6ab05c791015a555bbce` |
| concurrent iteration2 | 2,883,032 | `7cf41dd8bfdd04ac24b77388b4b717ee1040367b86f04743d57ca35d07fc0902` |

Both have220 undefined symbols: **all219 stock undefined symbols plus exactly `__memzero`, none removed**. The six config-associated differences from iteration1 closed. All proposed iteration2 config choices survived olddefconfig. This supports the stated hypothesis for these references, not a recovered vendor config.

The compile-only probe measured spinlock/raw_spinlock16 bytes and mutex36 bytes, mutex owner offset28/magic offset32. Mutex size matches the independently measured stock lock global, while spinlock16 agrees with the stock semaphore-initialization trace. Probe emitted both `__memzero` and `memset`; the source scan confirmed upstream `EXPORT_SYMBOL(__memzero)` in armksyms.c.

Remaining limitations are material: no vendor ABI acceptance or live export check, dependency metadata remains empty, the legacy WIRELESS_EXT vendor setting remains unknown (the earlier lab expectation was corrected as described above), and baseline section differences remain (.text58,224 bytes smaller, .bss14,216 bytes smaller, .data328 bytes smaller than stock). Matching selected lock sizes does not validate every embedded kernel structure, compiler option, downstream patch or race behavior. No produced module was retained as a deployable artifact or sent to the camera.

One research claim was independently rejected before implementation: upstream `arch/arm/kernel/armksyms.c` **does export `__memzero`**. Absence of an export declaration in `memzero.S` alone was not sufficient. Do not label the lab module unloadable merely because it references that symbol; target exports and vendor layout still require validation. No header patch will be used to hide it.

## Next evidence iteration: zero-initialized storage accounting

Stock .bss is28,190 bytes versus iteration2 baseline13,974, a14,216-byte difference. Stock named objects include the4096-byte PHY path, BT-coexist state and efuse arrays. However, the lab's `-fcommon` can keep tentative definitions in SHN_COMMON instead of .bss; comparing .bss section size alone cannot prove those features are absent or that allocated memory shrank by that amount. Proposed iteration3 retains the inferred iteration2 config and adds per-module object/COMMON tables, with interval-union accounting to avoid alias double counting. No compile-option change is justified solely to make a section size match.

Iteration3 [run39106160974](https://github.com/vunguyenbv175/C2M/actions/runs/39106160974), source `3454cb6`, **passed** in2m43s. Artifact inspection found no config mismatches or failed steps. Baseline SHA-256 `9a05824d39ce49ff540074a98e4f10c26f0407714b69b3a4f86da23bf6945f17`; concurrent `f219be49d3da18cfa954c17f61b71bf54f3fcb0c06c10b729f80786731e5ff88`.

Both modules have38 COMMON objects totaling14,117 bytes, while .bss remains13,974. The large PHY path, efuse and BT-coexist objects are present with stock-matching sizes; absence of those features is therefore disproven as an explanation of the section-size difference. Common total plus named NOBITS union is28,019 bytes, not a finalized memory layout. Every shared named writable object had matching size in the name-based comparison; the sole stock name absent from the lab table is `rtw_handlers_def` (24 bytes). This is evidence to investigate legacy WEXT configuration, not proof of a complete vendor net_device layout.

A further source check found that upstream4.9.227 kernel/module.c simplify_symbols rejects non-LTO SHN_COMMON with `please compile with -fno-common` and -ENOEXEC. Thus the previous target `-fcommon` workaround produced another known load blocker. This does not undo compilation success but prevents treating those modules as deployable. The host-tool workaround must not leak into target modules.

## Iteration4: separate target code generation from host compatibility

Keep inferred Kconfig unchanged; use target KCFLAGS `-fno-common -fno-pie`, retaining `-fcommon` only in HOSTCFLAGS for old host tools. Predict zero COMMON symbols. Add a failing offline gate if any remain while retaining metadata evidence. Link/build failures are reported, never suppressed; no header patch, force-vermagic or live load is involved. WEXT/vendor layout, live-missing `__memzero`, target export checks and independent recovery remain unresolved.

Iteration4 [run39106622652](https://github.com/vunguyenbv175/C2M/actions/runs/39106622652), source `657b054`, **passed** in3m50s. Downloaded reports show no failed steps/config mismatches, zero COMMON symbols in both profiles, .bss28,106 bytes (84 bytes below stock). Baseline2,859,384 bytes/SHA-256 `5b5c0c76151cee158643268ba8dd863a1ad88ff990a4321fad179fd26a216f48`; concurrent2,882,968 bytes/`470987063507196e880bf797995bc21bd8b59a7b1e03dd4649957803f4eba196`. Both still have the stock219 undefined references plus `__memzero`; dependencies remain unpopulated and WEXT/vendor-layout/recovery checks remain open. Baseline .text remains58,388 bytes smaller than stock. The COMMON codegen issue is closed for these outputs, not the ABI/load-safety gate.

The same metadata-only artifact boundary and no-load policy apply. No module was loaded or transferred to the camera.

## Iteration5: `__memzero` attribution and codegen variant measurement (recorded before execution)

Iteration5 is a metadata-only iteration: the reconstructed Kconfig and target
flags are unchanged from iteration4. It adds two evidence passes:

1. **Object-level attribution** — every regular `*.o` under each per-profile
   driver build tree is parsed and the objects whose undefined set contains
   `__memzero` (and/or `memset`) are listed, so the extra dependency can be
   traced to exact translation units instead of only the final `.ko`.
2. **Compile-only codegen variant table** — a tiny standalone snippet
   (constant-zero sized fill, constant-size fill, variable fill) is compiled
   with the pinned host cross compiler under five flag sets (lab target
   flags, `-fno-builtin`, `-fno-builtin-memset`, `-Os`, `-marm`) and each
   object's undefined set is recorded. Variant flags are a reduced subset of
   the kbuild command line; the table isolates flag effects and is not a
   byte-exact kbuild reproduction.

Neither pass changes the built modules and both keep the NO_LOAD policy: the
attribution/table JSON files are metadata and the objects stay in the
ephemeral runner scratch directory. Resolution of the stock `memset`-only
difference, the legacy WEXT/layout question, vendor ABI, recovery and any
live test remain open gates. Iteration5 source: commit `4d74218`; workflow
run [39137457671](https://github.com/vunguyenbv175/C2M/actions/runs/39137457671).
