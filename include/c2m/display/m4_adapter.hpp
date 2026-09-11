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
    // Final stock-facing boundary (R2): EVERY message is re-validated here, so
    // a caller that bypasses Plan() with a hand-built payload still cannot
    // reach the sender with semantic/unknown content while L3 is BLOCKED.
    for (auto& m : msgs)
      if (!AllowedForTransmit(m)) return TransmitStatus::BlockedPolicy;
    TransmitStatus st = TransmitStatus::SendOk;
    for (auto& m : msgs)
      if (!sender_(m.channel, m.payload)) st = TransmitStatus::SendFailed;
    return st;
  }

  // Boundary validator (also unit-tested directly). Channel allowlist +
  // uuid policy + strict key-shape allowlist + denied-substring sweep.
  // Shape validation is the strong layer: a payload may only contain the keys
  // of its claimed harmless template. Anything else fails CLOSED (safe).
  static bool AllowedForTransmit(const PlannedMessage& m) {
    if (m.channel != "cardv:8080") return false;
    std::string uuid = ExtractUuid(m.payload);
    if (uuid.empty() || M4Policy::ClassifyJsonUuid(uuid) != M4Verdict::AllowL2) return false;
    if (!ShapeOk(uuid, m.payload)) return false;
    static const char* kDenied[] = {"vehicleWarning",  "vehicleMeasure", "pedestrians",
                                    "laneWarningRes",  "AdasStatus",     "HeavyCalibStatus",
                                    "GPSSpeed",        "GPSLevel",       "RecordVoice",
                                    "warning_level",   "warn",           "crucial",
                                    "danger",          "deviat",         "fcw",
                                    "ttc",             "dist",           "headway",
                                    "lane",            "ped",            "bike",
                                    "frame_id",        "is_key",         "speed"};
    for (const char* d : kDenied)
      if (m.payload.find(d) != std::string::npos) return false;
    return true;
  }

  // Payload keys must be exactly the harmless template's key set.
  static bool ShapeOk(const std::string& uuid, const std::string& payload) {
    std::string want;
    if (uuid == "DispBrightSet")
      want = "|brightness|";
    else if (uuid == "StorageStatus")
      want = "|status|";
    else if (uuid == "ScreenModeSet")
      want = "|theme|";
    else if (uuid == "ClientConn")
      want = "|connected|";
    else
      return false;
    std::string::size_type pos = 0;
    while ((pos = payload.find('"', pos)) != std::string::npos) {
      std::string::size_type end = payload.find('"', pos + 1);
      if (end == std::string::npos) return false;
      std::string::size_type colon = payload.find_first_not_of(" \t", end + 1);
      if (colon != std::string::npos && payload[colon] == ':') {
        std::string key = payload.substr(pos + 1, end - pos - 1);
        if (key != "type" && key != "uuid" && want.find("|" + key + "|") == std::string::npos)
          return false;
        pos = colon + 1;
      } else {
        pos = end + 1;
      }
    }
    return true;
  }

 private:
  static std::string ExtractUuid(const std::string& payload) {
    const std::string key = "\"uuid\":\"";
    std::string::size_type i = payload.find(key);
    if (i == std::string::npos) return "";
    i += key.size();
    std::string::size_type j = payload.find('"', i);
    if (j == std::string::npos || j - i > 64) return "";
    return payload.substr(i, j - i);
  }

  M4Config cfg_;
  Sender sender_;
};

}  // namespace display
}  // namespace c2m
