#pragma once
// M4Adapter — EF-A02/A03. ONLY place allowed to know stock M4 wire details.
// V1: encode DisplayState -> stock-compatible JSON (cardv :8080 style) + libflow
// topic/key routing hints. No sockets here; transport injects via ISender so
// host tests run without hardware. Real socket sender added at integration.
#include <functional>
#include <string>
#include <vector>
#include "c2m/display/display_state.hpp"
#include "c2m/display/i_display_adapter.hpp"

namespace c2m {
namespace display {

struct M4Config {
  bool allow_semantic_injection = false;  // L3 gate: false => L2 harmless-only
  int brightness_min = 1;
  int brightness_max = 10;
};

// Stock JSON templates from M4_STATIC_PROTOCOL_V1 §7 (CONFIRMED strings).
// Kept as helpers here so no other module rebuilds them.
inline std::string StockJson_GPSSpeed(int speed) {
  return "{\"type\":1601,\"uuid\":\"GPSSpeed\",\"speed\":" + std::to_string(speed) + "}";
}
inline std::string StockJson_GPSLevel(int level) {
  return "{\"type\":1600,\"uuid\":\"GPSLevel\",\"level\":" + std::to_string(level) + "}";
}
inline std::string StockJson_DispBright(int b) {
  return "{\"type\":1100,\"uuid\":\"DispBrightSet\",\"brightness\":" + std::to_string(b) + "}";
}

class M4Adapter : public IDisplayAdapter {
 public:
  using Sender = std::function<bool(const std::string& channel, const std::string& payload)>;
  explicit M4Adapter(M4Config cfg = {}, Sender sender = nullptr)
      : cfg_(cfg), sender_(sender) {}
  std::string Name() const override { return "M4Adapter"; }

  // L2 harmless-only vs L3 semantic routing decided here and unit-tested.
  std::vector<std::pair<std::string, std::string>> PlanMessages(const DisplayState& s) const {
    std::vector<std::pair<std::string, std::string>> out;
    // L2: system info passthrough is always allowed (harmless class).
    if (s.system.brightness >= cfg_.brightness_min && s.system.brightness <= cfg_.brightness_max)
      out.emplace_back("cardv:8080", StockJson_DispBright(s.system.brightness));
    if (s.ego_speed_kmh >= 0)
      out.emplace_back("cardv:8080", StockJson_GPSSpeed(s.ego_speed_kmh));
    if (!cfg_.allow_semantic_injection) return out;
    // L3: semantic injection only when explicitly enabled.
    // Warnings themselves stay on stock ADAS path; M4Adapter only adds context
    // (speed-limit confidence, nav, tpms text) via info-class messages.
    // Full libflow warning encode reserved until L1 decode proven on device.
    return out;
  }

  bool Render(const DisplayState& s) override {
    if (!sender_) return true;  // dry-run / planning mode
    bool ok = true;
    for (auto& kv : PlanMessages(s)) ok = sender_(kv.first, kv.second) && ok;
    return ok;
  }

 private:
  M4Config cfg_;
  Sender sender_;
};

}  // namespace display
}  // namespace c2m
