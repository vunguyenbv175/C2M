# C2M IPU SDK Receipt Validation V1 — Fail-Fast Workflow

**Date:** 2026-09-11. **Runs only when an SDK archive is received. No board work in this task.**
**Safety:** disposable VM/container, no creds/keys mounted, no network unless understood.
Never run unknown compiler binaries on the production workstation. Never commit SDK contents.

Local baseline: 11 MI_IPU exports (`CreateDevice/DestroyDevice/CreateCHN/DestroyCHN/
GetInOutTensorDesc/GetInputTensors/PutInputTensors/GetOutputTensors/PutOutputTensors/
Invoke/GetOfflineModeStaticInfo`), `sdk_commit b03a7d4`, `T_0.0.1_210525`, SSC8838G/Tiramisu.

## Step 0 — Intake (private records only)

```sh
sha256sum <sdk_archive>               # record: filename / size / date / source / SHA256
mkdir -p external/sgs_ipu_sdk && tar -xf <sdk_archive> -C external/sgs_ipu_sdk
git status --short                    # must show NOTHING (external/ is gitignored); STOP if SDK files appear tracked
```

## Step 1 — Tree inspect (no execution)

Expect and record presence/absence of:

```text
README / release notes / version files
cfg_env.sh / requirements / Dockerfile / run_docker.sh
Scripts/ConvertTool (ConvertTool.py / SGS_converter.py)
Scripts/calibrator (calibrator.py / compiler.py / simulator.py)
Netron viewer / SGS_Models examples (esp. MobileNetV2)
mi_ipu.h / mi_ipu_datatype.h / mi_sys.h / mi_scl.h
chip/target DB (CompilerConfig.txt / show_sdk_info.py / CHIP_LIST configs)
board demos (dla_classify / dla_detect / dla_simulator / show_img_info / ipu_log / utilization / ipu_server)
license files / license-server or dongle notes
```

Emit metadata only:

```sh
python3 tools/research/ipu_sdk/fingerprint_sgs_sdk.py --sdk external/sgs_ipu_sdk --out /tmp/sdk_fingerprint.json
```

## Step 2 — Identifier search (proves/denies branch match)

Search the extracted tree for each string, record file + line:

```text
b03a7d4 | 0940dba | T_0.0.1_210525 | 210525 | 20220606
SSC8838G | 8838 | Mercury6 | Tiramisu | SSC35
```

## Step 3 — Help screens (first execution; container preferred)

```sh
source cfg_env.sh (or per-drop equivalent)
python3 Scripts/ConvertTool/ConvertTool.py -h        # or SGS_converter.py -h
python3 Scripts/calibrator/calibrator.py -h
python3 Scripts/calibrator/compiler.py -h
python3 Scripts/calibrator/simulator.py -h
python3 DumpDebug/show_sdk_info.py                   # chip + version list, if present
```

Record: `ONNX_SUPPORTED = YES / NO` from the ConvertTool help (do NOT infer from modern docs).

## Step 4 — API comparison (static only, never executes the target lib)

```sh
python3 tools/research/ipu_sdk/compare_mi_ipu_api.py \
  --dynsym <local_11_dynsym.txt> --header external/sgs_ipu_sdk/<...>/mi_ipu.h \
  [--lib external/sgs_ipu_sdk/<...>/libmi_ipu.so]
```

Tools status: both exist and pass baseline self-check (`compare` prints the local 11/0/0;
`fingerprint` emits metadata-only JSON). No changes were needed for this task.

## Step 5 — Classify (exactly one)

```text
EXACT ......... branch strings match (b03a7d4/0940dba/T_0.0.1_210525) AND
                SSC8838G/Tiramisu target present AND all 11 local APIs present
NEAR .......... same IPU generation + SSC8838G/Tiramisu target present, branch strings
                differ BUT vendor documents backward compatibility with T_0.0.1_210525
FAMILY_ONLY ... IPU toolchain for another chip (e.g. S21 pcupid-only) — flow reference only
INCOMPATIBLE .. any hard-rejection gate fires (§6)
UNKNOWN ....... evidence insufficient — ask FAE before compiling
```

Only EXACT or vendor-confirmed NEAR may proceed to the MobileNetV2 host proof
(`docs/hardware/C2M_IPU_SMOKE_MODEL_RECIPE.md`). Do NOT "try anyway" with FAMILY_ONLY output.

## Step 6 — Hard rejection gates (STOP before compiling if ANY fires)

```text
[ ] SSC8838G/Tiramisu target absent from chip/target list
[ ] Vendor states runtime/model ABI incompatible with T_0.0.1_210525 or b03a7d4
[ ] Any of the 11 required local MI_IPU APIs missing from candidate headers/libs
[ ] Compiler targets only unrelated chips (e.g. pcupid-only drop)
[ ] License/access invalid (expired NDA, missing license server/dongle, no redistribution clarity for internal use)
```

On STOP: record verdict INCOMPATIBLE + triggering gate, reply to FAE with the fingerprint
(version strings + chip list + missing API), and preserve `NATIVE_IPU_TOOLCHAIN_EXTERNAL_DEPENDENCY`.

## Step 7 — Receipt record (private)

```text
archive filename / size / SHA256 / source / date
fingerprint JSON path | ConvertTool -h text | show_sdk_info output
identifier search hits | API diff output | classification + gate checklist
decision: PROCEED (EXACT/NEAR-confirmed) or STOP (gate + reason)
```
