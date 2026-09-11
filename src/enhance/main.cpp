// c2m-enhance daemon — Gate D host skeleton (read-only, mock providers).
// Usage:
//   c2m-enhance --scenario lead --ticks 10 --period-ms 200
// Prints one JSON status line per tick to stdout. No stock control, no
// transmission: M4Adapter runs planning-only (BlockedReadOnly by construction).
// Lifecycle: SIGINT/SIGTERM stop the loop; exit code 0 on clean stop.
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <string>
#include <thread>

#include "c2m/core/c2m_enhance.hpp"

namespace {
std::atomic<bool> g_stop{false};
void OnSignal(int) { g_stop.store(true); }

struct Args {
  std::string scenario = "lead";
  int ticks = 10;
  int period_ms = 200;
};

Args Parse(int argc, char** argv) {
  Args a;
  for (int i = 1; i < argc; ++i) {
    std::string k = argv[i];
    auto val = [&](int& i) -> std::string { return (i + 1 < argc) ? argv[++i] : ""; };
    if (k == "--scenario")
      a.scenario = val(i);
    else if (k == "--ticks")
      a.ticks = std::stoi(val(i));
    else if (k == "--period-ms")
      a.period_ms = std::stoi(val(i));
    else {
      std::fprintf(stderr, "unknown arg: %s\n", k.c_str());
      std::fprintf(stderr, "usage: c2m-enhance [--scenario idle|lead|fcw|ldw|ped] "
                           "[--ticks N] [--period-ms MS]\n");
      std::exit(2);
    }
  }
  return a;
}
}  // namespace

int main(int argc, char** argv) {
  Args args = Parse(argc, argv);
  std::signal(SIGINT, OnSignal);
  std::signal(SIGTERM, OnSignal);

  auto core = c2m::core::MakeMockCore(args.scenario);
  std::uint64_t now_ms = 1000;
  for (int t = 0; t < args.ticks && !g_stop.load(); ++t, now_ms += (std::uint64_t)args.period_ms) {
    c2m::core::TickResult r = core->Tick(now_ms, /*ego_speed_kmh=*/-1);
    std::printf("{\"tick\":%d,\"ts\":%llu,\"objects\":%zu,\"fcw\":%d,\"ldw\":%d,\"pcw\":%d,"
                "\"lead\":%d,\"transport\":%d}\n",
                t, (unsigned long long)r.display.timestamp_ms, r.display.objects.size(),
                (int)r.display.warning.fcw, (int)r.display.warning.ldw, (int)r.display.warning.pcw,
                (int)r.display.lead.present, (int)r.transmit);
    std::fflush(stdout);
    if (t + 1 < args.ticks) std::this_thread::sleep_for(std::chrono::milliseconds(args.period_ms));
  }
  return 0;
}
