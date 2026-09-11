#pragma once
// M4Adapter — EF-A02, Gate B hardened + Gate F (L3 BLOCKED).
// ONLY place allowed to know stock M4 wire details.
// Planning (pure) is separated from transmission (capability-gated, F1).
// Policy: M4Policy (single source, F2). Dry-run is explicit (F12).
#include <cstdint>
#include <functional>
#include <string>
#include <utility>
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

enum class TransmitStatus : std::uint8_t {
  DryRun = 0,        // no sender configured: planned only, nothing transmitted
  BlockedReadOnly = 1,  // capability gate refused transmission (F1)
  BlockedL3 = 2,         // semantic content requested while L3 is blocked (Gate F)
  SendOk = 3,
  SendFailed = 4
};

struct M4Config {
  int brightness_min = 1;
  int brightness_max = 10;
};

class M4Adapter : public IDisplayAdapter {
 public:
  using Sender = std::function<bool(const std::string& channel, const std::string& payload)>;
  explicit M4Adapter(M4Config cfg = {}, Sender sender = nullptr)
      : cfg_(cfg), sender_(sender) {}
  std::string Name() const override { return "M4Adapter"; }

  // Pure planning. L2 info-class only, each message policy-checked.
  // NOTE: ego_speed/GPSSpeed is NOT emitted at L2 (F2: semantic-DENY).
  std::vector<std::pair<std::string, std::string>> PlanMessages(const DisplayState& s) const {
    std::vector<std::pair<std::string, std::string>> out;
    if (s.system.brightness >= cfg_.brightness_min && s.system.brightness <= cfg_.brightness_max &&
        M4Policy::ClassifyJsonUuid("DispBrightSet") == M4Verdict::AllowL2)
      out.emplace_back("cardv:8080", StockJson_DispBright(s.system.brightness));
    return out;
  }

  struct RenderResult {
    TransmitStatus status = TransmitStatus::DryRun;
    std::size_t planned = 0;
    std::size_t sent = 0;
  };

  // Capability-gated transmit. allow_transmit=false (read-only) NEVER calls sender.
  RenderResult RenderEx(const DisplayState& s, bool allow_transmit) {
    RenderResult r;
    auto msgs = PlanMessages(s);
    r.planned = msgs.size();
    if (!allow_transmit) {
      r.status = TransmitStatus::BlockedReadOnly;
      return r;
    }
    if (!sender_) {
      r.status = TransmitStatus::DryRun;
      return r;
    }
    r.status = TransmitStatus::SendOk;
    for (auto& kv : msgs) {
      if (!sender_(kv.first, kv.second)) r.status = TransmitStatus::SendFailed;
      ++r.sent;
    }
    return r;
  }

  // IDisplayAdapter: dry-run planning only. Real transmission requires RenderEx
  // with an explicit capability. Returns false when nothing was transmitted so a
  // missing transport can never look healthy (F12).
  bool Render(const DisplayState& s) override {
    RenderResult r = RenderEx(s, /*allow_transmit=*/false);
    last_ = r.status;
    return r.status == TransmitStatus::SendOk;
  }
  TransmitStatus LastStatus() const { return last_; }

 private:
  M4Config cfg_;
  Sender sender_;
  TransmitStatus last_ = TransmitStatus::DryRun;
};

}  // namespace display
}  // namespace c2m
