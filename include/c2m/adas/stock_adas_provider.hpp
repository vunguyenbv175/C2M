#pragma once
// StockADASProvider — EF-A01.
// Converts stock libflow inner payloads + cardv JSON status into AdasState.
// Transport-agnostic: caller feeds already-decoded maps (from libflow_protocol.py
// logic or C++ msgpack layer). No sockets here -> testable on host, safe on device.
#include <algorithm>
#include <cstdint>
#include <map>
#include <string>
#include <vector>
#include "c2m/adas/adas_state.hpp"
#include "c2m/adas/i_adas_provider.hpp"

namespace c2m {
namespace adas {

// Minimal decoded value that mirrors Python dicts from libflow decode.
// Keeps this header free of msgpack dependency; transport layer converts first.
using NumMap = std::map<std::string, double>;
using StrMap = std::map<std::string, std::string>;

struct StockSnapshot {
  std::uint64_t now_ms = 0;
  // Inner key -> rows. vehicleWarning/laneWarningRes use rows[0].
  std::map<std::string, std::vector<NumMap>> nums;
  // cardv :8080 status strings.
  StrMap cardv;
  bool libflow_connected = false;
  bool cardv_connected = false;
  std::uint64_t last_frame_ms = 0;
  std::uint64_t frame_id = 0;
};

inline double GetNum(const NumMap& m, const std::string& k, double dflt = 0.0) {
  auto it = m.find(k);
  return it == m.end() ? dflt : it->second;
}

// Pure function: snapshot -> normalized state. Mirrors tools/m4/normalize_adas.py.
inline AdasState NormalizeStock(const StockSnapshot& s, std::uint64_t stale_after_ms = 500) {
  AdasState out;
  out.timestamp_ms = s.now_ms;
  out.frame_id = s.frame_id;
  out.health.libflow_connected = s.libflow_connected;
  out.health.cardv_connected = s.cardv_connected;
  out.health.age_ms = (s.now_ms >= s.last_frame_ms) ? (s.now_ms - s.last_frame_ms) : 0;
  out.stale = !s.libflow_connected || (out.health.age_ms > stale_after_ms);

  // --- vehicleWarning (map 7 keys) ---
  auto vw = s.nums.find("vehicleWarning");
  NumMap warn = (vw != s.nums.end() && !vw->second.empty()) ? vw->second[0] : NumMap{};
  int warn_vehicle_id = static_cast<int>(GetNum(warn, "vehicle_id", -1));
  double headway = GetNum(warn, "headway", 0.0);
  int warning_level = static_cast<int>(GetNum(warn, "warning_level", 0));
  int fcw_raw = static_cast<int>(GetNum(warn, "fcw", 0));

  // --- vehicleMeasure (array of 8-key maps) ---
  auto vm = s.nums.find("vehicleMeasure");
  if (vm != s.nums.end()) {
    for (const auto& r : vm->second) {
      VehicleObject v;
      v.id = static_cast<int>(GetNum(r, "vehicle_id", -1));
      v.vehicle_class = static_cast<int>(GetNum(r, "vehicle_class", -1));
      v.width = static_cast<float>(GetNum(r, "vehicle_width", 0.0));
      v.long_dist = static_cast<float>(GetNum(r, "longitude_dist", 0.0));
      v.lat_dist = static_cast<float>(GetNum(r, "lateral_dist", 0.0));
      v.ttc = static_cast<float>(GetNum(r, "ttc", 0.0));
      v.is_crucial = GetNum(r, "is_crucial", 0.0) != 0.0;
      v.is_second_crucial = GetNum(r, "is_second_crucial", 0.0) != 0.0;
      if (v.id == warn_vehicle_id) v.headway = static_cast<float>(headway);
      out.vehicles.push_back(v);
    }
  }
  // Lead pick: crucial > second_crucial > nearest long_dist.
  const VehicleObject* lead = nullptr;
  for (const auto& v : out.vehicles)
    if (v.is_crucial) {
      lead = &v;
      break;
    }
  if (!lead)
    for (const auto& v : out.vehicles)
      if (v.is_second_crucial) {
        lead = &v;
        break;
      }
  if (!lead && !out.vehicles.empty()) {
    lead = &*std::min_element(out.vehicles.begin(), out.vehicles.end(),
                              [](const VehicleObject& a, const VehicleObject& b) {
                                return a.long_dist < b.long_dist;
                              });
  }
  if (lead) {
    out.lead_distance_m = lead->long_dist;
    out.ttc_s = lead->ttc;
  }
  out.fcw.active = (fcw_raw != 0 || warning_level != 0);
  out.fcw.level = warning_level;
  out.fcw.source = out.fcw.active ? WarningSource::Stock : WarningSource::Unknown;

  // --- pedestrians ---
  auto pd = s.nums.find("pedestrians");
  bool pcw = false;
  if (pd != s.nums.end()) {
    for (const auto& r : pd->second) {
      PedestrianObject p;
      p.id = static_cast<int>(GetNum(r, "id", -1));
      p.world_x = static_cast<float>(GetNum(r, "world_x", 0.0));
      p.world_y = static_cast<float>(GetNum(r, "world_y", 0.0));
      p.is_key = GetNum(r, "is_key", 0.0) != 0.0;
      p.is_danger = GetNum(r, "is_danger", 0.0) != 0.0;
      p.ttc_m = static_cast<float>(GetNum(r, "ttc_m", 0.0));
      p.ttc = static_cast<float>(GetNum(r, "ttc", 0.0));
      p.have_bike = GetNum(r, "have_bike", 0.0) != 0.0;
      if (p.is_danger || p.is_key) pcw = true;
      out.pedestrians.push_back(p);
    }
  }
  out.pcw.active = pcw;
  out.pcw.source = pcw ? WarningSource::Stock : WarningSource::Unknown;

  // --- laneWarningRes ---
  auto lw = s.nums.find("laneWarningRes");
  if (lw != s.nums.end() && !lw->second.empty()) {
    const NumMap& r = lw->second[0];
    out.lane.deviate_state = static_cast<int>(GetNum(r, "deviate_state", 0));
    out.lane.turn_radius = static_cast<float>(GetNum(r, "turn_radius", 0.0));
    out.lane.turn_frequently = GetNum(r, "turn_frequently", 0.0) != 0.0;
    out.ldw.active = (out.lane.deviate_state != 0);
    out.ldw.level = out.lane.deviate_state;
    out.ldw.source = out.ldw.active ? WarningSource::Stock : WarningSource::Unknown;
  }

  // --- cardv status (never makes whole state stale) ---
  auto it = s.cardv.find("AdasStatus");
  if (it != s.cardv.end()) {
    out.cardv_status.adas_status = it->second;
    out.cardv_status.stale = false;
  }
  it = s.cardv.find("HeavyCalibStatus");
  if (it != s.cardv.end()) out.cardv_status.calib_status = it->second;

  if (!s.libflow_connected)
    out.health.runtime_class = AdasRuntimeClass::A_ProcessAbsent;
  else if (out.stale)
    out.health.runtime_class = AdasRuntimeClass::C_InputPathSuspect;
  else
    out.health.runtime_class = AdasRuntimeClass::Ok;
  return out;
}

struct StockProviderConfig {
  std::uint64_t stale_after_ms = 500;
};

// Thin stateful wrapper around the pure NormalizeStock().
class StockADASProvider : public IAdasProvider {
 public:
  explicit StockADASProvider(StockProviderConfig cfg = {}) : cfg_(cfg) {}
  void Ingest(const StockSnapshot& s) { last_ = s; has_ = true; }
  std::string Name() const override { return "StockADASProvider"; }
  AdasState Poll() override {
    if (!has_) {
      AdasState s;
      s.stale = true;
      return s;
    }
    return NormalizeStock(last_, cfg_.stale_after_ms);
  }
  bool Healthy() const override { return has_ && !Poll().stale; }

 private:
  StockProviderConfig cfg_;
  StockSnapshot last_;
  bool has_ = false;
};

}  // namespace adas
}  // namespace c2m
