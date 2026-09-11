#pragma once
// M4Adapter — EF-A02, Gate B hardened + Gate F (L3 BLOCKED).
// ONLY place allowed to know stock M4 wire details.
// Implements IDisplayPlanner (pure) + IStockTransmitter (capability-gated).
// Policy: M4Policy (single source, F2). Dry-run is explicit (F12).
#include <cstdint>
#include <functional>
#include <string>
#include <vector>
#include "c2m/display/display_state.hpp"
#include "c2m/display/i_display_adapter.hpp"
#include "c2m/display/m4_policy.hpp"

namespace c2m {
namespace display {

// Stock JSON templates from cardv .rodata (CONFIRMED, STOCK_ADAS_SCHEMA_V2 §2).
// L2-allowed only; semantic ones exist for future L3 and are DENY-gated.
inline std::string StockJson_GPSSpeed(int speed) {
  return "{\"type\":1601,\"uuid\":\"GPSSpeed\",\"speed\":" + std::to_string(speed) + "}";
}
inline std::string StockJson_DispBright(int b) {
  return "{\"type\":1100,\"uuid\":\"DispBrightSet\",\"brightness\":" + std::to_string(b) + "}";
}
inline std::string StockJson_Storage(const std::string& status) {
  return "{\"type\":1200,\"uuid\":\"StorageStatus\",\"status\":\"" + status + "\"}";
}

struct M4Config {
  int brightness_min = 1;
  int brightness_max = 10;
};

class M4Adapter : public IDisplayPlanner, public IStockTransmitter {
 public:
  using Sender = std::function<bool(const std::string& channel, const std::string& payload)>;
  explicit M4Adapter(M4Config cfg = {}, Sender sender = nullptr)
      : cfg_(cfg), sender_(sender) {}
  std::string Name() const override { return "M4Adapter"; }

  // Pure planning. L2 info-class only, each message policy-checked.
  // NOTE: ego_speed/GPSSpeed is NOT emitted at L2 (F2: semantic-DENY).
  std::vector<PlannedMessage> Plan(const DisplayState& s) const override {
    std::vector<PlannedMessage> out;
    if (s.system.brightness >= cfg_.brightness_min && s.system.brightness <= cfg_.brightness_max &&
        M4Policy::ClassifyJsonUuid("DispBrightSet") == M4Verdict::AllowL2)
      out.push_back(PlannedMessage{"cardv:8080", StockJson_DispBright(s.system.brightness)});
    return out;
  }

  TransmitStatus Transmit(const std::vector<PlannedMessage>& msgs, AllowTransmit) override {
    if (!sender_) return TransmitStatus::DryRun;
    TransmitStatus st = TransmitStatus::SendOk;
    for (auto& m : msgs)
      if (!sender_(m.channel, m.payload)) st = TransmitStatus::SendFailed;
    return st;
  }

 private:
  M4Config cfg_;
  Sender sender_;
};

}  // namespace display
}  // namespace c2m
