// main.cpp — c2m-ipu-smoke skeleton (probe-only default; BENCH_ONLY inference on request).
// Builds ONLY with vendor headers/libs supplied privately (see build_armv7.sh).
// Without them, this file documents the exact future call order and PASS outputs.
#include <cstdio>
#include <cstring>
#include "mi_ipu_compat.hpp"
static void usage() {
  std::printf("usage: c2m-ipu-smoke [--probe-only] [--model <path>] [--image <path>] [--single-invoke]\n"
              "  [--channel <id>] [--firmware <path>] [--no-stock-stop]\n"
              "default: --probe-only (READ_ONLY discovery, no inference, never stops stock)\n");
}
int main(int argc, char** argv) {
  bool probe_only = true, single_invoke = false;
  const char* model = nullptr, *image = nullptr, *firmware = "/config/dla/ipu_firmware.bin";
  unsigned channel = 0;
  for (int i = 1; i < argc; ++i) {
    if (!std::strcmp(argv[i], "--probe-only")) { probe_only = true; single_invoke = false; }
    else if (!std::strcmp(argv[i], "--single-invoke")) { single_invoke = true; probe_only = false; }
    else if (!std::strcmp(argv[i], "--model") && i + 1 < argc) { model = argv[++i]; }
    else if (!std::strcmp(argv[i], "--image") && i + 1 < argc) { image = argv[++i]; }
    else if (!std::strcmp(argv[i], "--firmware") && i + 1 < argc) { firmware = argv[++i]; }
    else if (!std::strcmp(argv[i], "--channel") && i + 1 < argc) { channel = (unsigned)std::atoi(argv[++i]); }
    else if (!std::strcmp(argv[i], "--no-stock-stop")) { /* default, accepted explicitly */ }
    else { usage(); return 2; }
  }
  std::printf("[probe-only] firmware=%s (READ_ONLY discovery)\n", firmware);
  std::printf("[probe-only] report: /dev/mi_ipu presence, ipu_nodes.tsv state, lib version T_0.0.1_210525 expectation\n");
  if (probe_only) { std::printf("[probe-only] done (no inference; stock untouched)\n"); return 0; }
  // BENCH_ONLY path below requires vendor link; without it, refuse safely.
#ifdef C2M_IPU_HAVE_VENDOR_HEADERS
  std::printf("[bench-only] model=%s image=%s channel=%u (explicit request)\n",
              model ? model : "(none)", image ? image : "(none)", channel);
  std::printf("order: MI_SYS_Init -> CreateDevice(fw,varSize) -> CreateCHN(depths 2,2) -> GetDesc\n"
              "  -> GetOutputTensors -> Invoke once -> XOR/checksum+latency -> Put -> DestroyCHN/Device\n");
  std::printf("PASS needs: CreateDevice==0 CreateCHN==0 Invoke==0 valid-output clean-Destroy no-hang\n");
  return 0;
#else
  std::printf("refusing inference: vendor headers/libs not supplied (see build_armv7.sh). Staying probe-only.\n");
  return 3;
#endif
}
