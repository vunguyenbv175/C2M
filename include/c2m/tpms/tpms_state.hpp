#pragma once
// TPMS normalized state — EF scope P10, interface-first so Display/Voice/Web
// can render even before RF/BLE gateway exists.
#include <cstdint>
#include <optional>
#include <string>
namespace c2m {
namespace tpms {
struct TireState {
  float pressure_bar = 0.0f;
  float temperature_c = 0.0f;
  std::optional<int> battery_percent;
  bool low_pressure = false;
  bool high_pressure = false;
  bool high_temperature = false;
  bool rapid_loss = false;
};
struct TpmsState {
  bool available = false;
  std::string provider = "none";  // none|rf433|ble|obd|mock
  TireState wheels[4];             // FL FR RL RR
  std::uint64_t timestamp_ms = 0;
};
class ITpmsProvider {
 public:
  virtual ~ITpmsProvider() = default;
  virtual std::string Name() const = 0;
  virtual TpmsState Poll() = 0;
};
}  // namespace tpms
}  // namespace c2m
