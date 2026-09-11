# c2m-ipu-smoke — future standalone IPU probe (bench only, NOT firmware)

**Status:** PREPARATION ONLY skeleton. Does NOT modify firmware/Candidates. Compiles only when vendor `mi_ipu.h`/`mi_sys.h` + libs are supplied (never vendored here).
**Default:** `--probe-only` (READ_ONLY discovery). `--single-invoke` is BLOCKED_TOOLCHAIN: refused with exit 4 in ALL builds until a vendor-backed Invoke implementation exists (never 0 for a non-executed Invoke). Default never stops stock (`--no-stock-stop` implied; no autostart edits).

See `RUNBOOK.md` for SAFE (bench, stock untouched) vs COEXIST (stock alive, single-shot) phases and PASS gates.
Layout reconstructed in `mi_ipu_compat.hpp` is UNVERIFIED — validate `sizeof`/ioctl against shipped `libmi_ipu.so` + on-device `GetInOutTensorDesc` before trusting.
