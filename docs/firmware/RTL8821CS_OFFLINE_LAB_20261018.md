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

Preparation in progress. Build results and run URL will be recorded after the first workflow execution; no module compilation success is claimed at this stage.
