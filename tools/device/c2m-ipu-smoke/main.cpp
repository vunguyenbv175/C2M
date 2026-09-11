// main.cpp — c2m-ipu-smoke skeleton (probe-only default; BENCH_ONLY inference NOT IMPLEMENTED).
// Pre-hardware status: BLOCKED_TOOLCHAIN. --single-invoke hard-refuses with exit 4
// (SDK_BLOCKED/NOT_IMPLEMENTED) in ALL builds until a vendor-backed implementation
// (real MI_SYS_Init / MI_IPU_CreateDevice / CreateCHN / Invoke / cleanup against the
// matching private SDK) lands. This binary NEVER returns 0 for a non-executed Invoke.
// Builds: default documents the probe order; the vendor-header build (build_armv7.sh,
// private SDK dir, never committed) additionally proves header/API compatibility at
// compile time via the real mi_ipu.h/mi_sys.h includes in mi_ipu_compat.hpp.
// Exit codes: 0 = probe-only discovery ok (no inference) · 2 = usage error ·
//             4 = SDK_BLOCKED/NOT_IMPLEMENTED (--single-invoke refused, nothing executed).
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "mi_ipu_compat.hpp"
static void usage() {
  std::printf("usage: c2m-ipu-smoke [--probe-only] [--model <path>] [--image <path>] [--single-invoke]\n"
               "  [--channel <id>] [--firmware <path>] [--no-stock-stop]\n"
               "default: --probe-only (READ_ONLY discovery, no inference, never stops stock)\n"
               "--single-invoke: BLOCKED_TOOLCHAIN (refused, exit 4) until vendor-backed build exists\n");
}
// Intended future BENCH_ONLY call order (documentation only — NOT executed by this skeleton):
//   MI_SYS_Init -> CreateDevice(fw,varSize) -> CreateCHN(depths 2,2) -> GetDesc
//   -> GetOutputTensors -> Invoke once -> XOR/checksum+latency -> Put -> DestroyCHN/Device.
// PASS needs: CreateDevice==0 CreateCHN==0 Invoke==0 valid-output clean-Destroy no-hang.
int main(int argc, char** argv) {
  bool probe_only = true;
  const char* model = nullptr, *image = nullptr, *firmware = "/config/dla/ipu_firmware.bin";
  unsigned channel = 0;
  for (int i = 1; i < argc; ++i) {
    if (!std::strcmp(argv[i], "--probe-only")) { probe_only = true; }
    else if (!std::strcmp(argv[i], "--single-invoke")) { probe_only = false; }
    else if (!std::strcmp(argv[i], "--model") && i + 1 < argc) { model = argv[++i]; }
    else if (!std::strcmp(argv[i], "--image") && i + 1 < argc) { image = argv[++i]; }
    else if (!std::strcmp(argv[i], "--firmware") && i + 1 < argc) { firmware = argv[++i]; }
    else if (!std::strcmp(argv[i], "--channel") && i + 1 < argc) { channel = (unsigned)std::atoi(argv[++i]); }
    else if (!std::strcmp(argv[i], "--no-stock-stop")) { /* default, accepted explicitly */ }
    else { usage(); return 2; }
  }
  if (probe_only) {
    std::printf("[probe-only] firmware=%s (READ_ONLY discovery)\n", firmware);
    std::printf("[probe-only] report: /dev/mi_ipu presence, ipu_nodes.tsv state, lib version T_0.0.1_210525 expectation\n");
    std::printf("[probe-only] done (no inference; stock untouched)\n");
    return 0;
  }
  // --single-invoke requested: refuse in EVERY build. No MI_IPU_Invoke is linked or
  // executed here, so returning 0 would be a false success. A vendor-backed build
  // (real headers + libs + implemented Invoke path) must replace this refuse branch.
  (void)model; (void)image; (void)channel;
  std::printf("SDK_BLOCKED: --single-invoke not implemented in this skeleton (no MI_IPU_Invoke executed).\n"
              "  Supply the matching private SDK plus a vendor-backed implementation, then re-run.\n"
              "  SAFE/COEXIST gates stay BLOCKED_TOOLCHAIN until then.\n");
  return 4;
}
