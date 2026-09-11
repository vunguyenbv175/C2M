# Candidate-B runbook — how the real Linux chain is executed

## Supported path (F1): GitHub-hosted runner + private firmware vault

One-time setup (already done 2026-09-11, recorded here so it is reproducible):

1. `ssh-keygen -t ed25519 -C c2m-firmware-vault-deploy` (local, key kept out
   of every repo; public half below).
2. Private repo `vunguyenbv175/c2m-firmware-vault` holding exactly one file:
   `V2023.08.03.1_C2M_U_FR_WIFI_EN.tar` (original vendor bytes, unmodified).
3. Read-only deploy key on the vault (`c2m-candidateB-readonly`,
   `read_only: true`).
4. Vault private key stored as this repo's Actions secret `FIRMWARE_VAULT_KEY`.

Each dispatch of `firmware-candidateB.yml` then: clones the vault over SSH
with that key, copies the TAR to `firmware/original/`, and MANDATORILY
verifies SHA-256
`3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c`
(`sha256sum -c`, fail-closed) before any use. Key material is deleted from
the runner immediately after cloning.

Dispatch: Actions tab → `firmware-candidateB` → Run workflow → watch gates.
Evidence downloads from the `candidateB-evidence` artifact (JSON/MD/TXT
only — never firmware bytes).

## Alternative: canonical local Linux execution (no GitHub needed)

On any Ubuntu 24.04 box with the original EN TAR:

```bash
sudo apt-get install -y mtd-utils gcc-arm-linux-gnueabihf ninja-build liblzo2-dev
EN=firmware/original/V2023.08.03.1_C2M_U_FR_WIFI_EN.tar
echo "3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c  $EN" | sha256sum -c -
python3 tools/fw/carve_upgrade.py "$EN" -o work/carve
CUST=$(ls work/carve/customer.es.load0.*.bin)
python3 tools/fw/ubifs_geometry.py "$CUST" -o work/customer_geometry.json
python3 tools/fw/ubifs_manifest.py "$CUST" -o work/customer_manifest.json
python3 tools/fw/ubifs_extract_tree.py "$CUST" work/tree \
  --manifest work/customer_manifest.json --report work/tree_report.json
sudo bash tools/fw/rebuild_customer.sh --mode noop \
  --tree work/tree --tree-report work/tree_report.json \
  --geometry work/customer_geometry.json \
  --stock-manifest work/customer_manifest.json \
  --out work/customer_noop.es --report work/rebuild_noop.json
cmake -S fw/device_minimal -B build/arm-dyn-b -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=fw/device_minimal/toolchain-armhf-dyn.cmake \
  -DCMAKE_BUILD_TYPE=MinSizeRel && cmake --build build/arm-dyn-b
python3 fw/device_minimal/check_elf.py build/arm-dyn-b/c2m-idle --allow-dynamic
python3 tools/fw/mutate_customer.py --tree work/tree \
  --manifest work/customer_manifest.json \
  --idle-bin build/arm-dyn-b/c2m-idle --out-manifest work/mutation.json
sudo bash tools/fw/rebuild_customer.sh --mode mutated \
  --tree work/tree --tree-report work/tree_report.json \
  --geometry work/customer_geometry.json \
  --stock-manifest work/customer_manifest.json \
  --mut-manifest work/mutation.json \
  --out work/customer_B.es --report work/rebuild_B.json
python3 tools/fw/build_candidates.py --en-tar "$EN" \
  --workdir work/candidates --customer-b work/customer_B.es
```

## Alternative: self-hosted Linux runner

Not currently provisioned. If added later: pre-place the SHA-verified TAR at
`firmware/original/` on the runner (or grant it vault access the same way),
then dispatch the same workflow with `runs-on: [self-hosted, linux]`.
No workflow logic change needed beyond the runner label.

## Hard rules (all paths)

- Never commit vendor firmware to the public repo; never upload `*.tar` /
  `*.bin` as Actions artifacts (the upload step lists evidence files only).
- Every gate is fail-closed; a RED job means the chain stopped, not that a
  partial Candidate B exists.
