#pragma once
// StockADASProvider — EF-A01, Gate B hardened (review F4/F5/F11).
// Sole warning drivers per STOCK_ADAS_SCHEMA_V2: fcw field, is_danger,
// deviate_state, is_crucial. Transport observations never imply process state.
#include <cstdint>
#include <map>
#include <string>
#include <vector>
#include "c2m/adas/adas_state.hpp"
#include "c2m/adas/i_adas_provider.hpp"

namespace c2m {
namespace adas {

struct StockSnapshot {
  std::uint64_t now_ms = 0;
  std::map<std::string, std::vector<NumMap>> nums;
  std::map<std::string, std::string> cardv;
  bool libflow_reachable = false;
  bool subscription_active = false;
  bool cardv_reachable = false;
  bool frame_seen = false;
  std::uint64_t last_frame_ms = 0;
  std::uint64_t frame_id = 0;
  // Set ONLY from device-collector process evidence. Absent by default.
  std::optional<ProcessPresence> process;
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
  out.health.frame_seen = s.frame_seen;
  out.health.libflow_reachable = s.libflow_reachable;
  out.health.subscription_active = s.subscription_active;
  out.health.cardv_reachable = s.cardv_reachable;
  out.health.process = s.process.value_or(ProcessPresence::Unknown);
  out.health.age_ms = (s.frame_seen && s.now_ms >= s.last_frame_ms) ? (s.now_ms - s.last_frame_ms) : 0;
  out.stale = !s.frame_seen || (out.health.age_ms > stale_after_ms);

  // --- vehicleWarning (7 keys, RAW-ONLY except fcw) ---
  auto vw = s.nums.find("vehicleWarning");
  NumMap warn = (vw != s.nums.end() && !vw->second.empty()) ? vw->second[0] : NumMap{};
  out.raw.vehicle_warning = warn;
  int warn_vehicle_id = static_cast<int>(GetNum(warn, "vehicle_id", -1));
  double headway = GetNum(warn, "headway", 0.0);
  out.raw.warning_level = static_cast<int>(GetNum(warn, "warning_level", 0));
  int fcw_raw = static_cast<int>(GetNum(warn, "fcw", 0));
  out.raw.headway_warning = static_cast<int>(GetNum(warn, "headway_warning", 0));
  out.raw.vb_warning = static_cast<int>(GetNum(warn, "vb_warning", 0));
  out.raw.sag_warning = static_cast<int>(GetNum(warn, "sag_warning", 0));

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
  // Lead ONLY on stock markers. No min-distance fallback (F11).
  for (const auto& v : out.vehicles) {
    if (v.is_crucial) {
      out.lead = LeadInfo{true, "crucial", v.long_dist, v.ttc};
      break;
    }
  }
  if (!out.lead.present) {
    for (const auto& v : out.vehicles) {
      if (v.is_second_crucial) {
        out.lead = LeadInfo{true, "second_crucial", v.long_dist, v.ttc};
        break;
      }
    }
  }
  // SOLE driver: explicit fcw field. warning_level NEVER drives FCW (F4).
  out.fcw.active = (fcw_raw != 0);
  out.fcw.level = fcw_raw;
  out.fcw.source = out.fcw.active ? WarningSource::Stock : WarningSource::Unknown;
  out.fcw.evidence = out.fcw.active ? Evidence::HighConfidence : Evidence::Unknown;

  // --- pedestrians: SOLE driver is_danger; is_key preserved only ---
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
      if (p.is_key) out.raw.key_pedestrian_count++;
      if (p.is_danger) pcw = true;
      out.pedestrians.push_back(p);
    }
  }
  out.pcw.active = pcw;
  out.pcw.source = pcw ? WarningSource::Stock : WarningSource::Unknown;
  out.pcw.evidence = pcw ? Evidence::HighConfidence : Evidence::Unknown;

  // --- laneWarningRes: SOLE driver deviate_state ---
  auto lw = s.nums.find("laneWarningRes");
  if (lw != s.nums.end() && !lw->second.empty()) {
    const NumMap& r = lw->second[0];
    out.lane.deviate_state = static_cast<int>(GetNum(r, "deviate_state", 0));
    out.raw.deviate_state = out.lane.deviate_state;
    out.lane.turn_radius = static_cast<float>(GetNum(r, "turn_radius", 0.0));
    out.lane.turn_frequently = GetNum(r, "turn_frequently", 0.0) != 0.0;
    out.ldw.active = (out.lane.deviate_state != 0);
    out.ldw.level = out.lane.deviate_state;
    out.ldw.source = out.ldw.active ? WarningSource::Stock : WarningSource::Unknown;
    out.ldw.evidence = out.ldw.active ? Evidence::HighConfidence : Evidence::Unknown;
  }

  auto it = s.cardv.find("AdasStatus");
  if (it != s.cardv.end()) {
    out.cardv_status.adas_status = it->second;
    out.cardv_status.stale = false;
  }
  it = s.cardv.find("HeavyCalibStatus");
  if (it != s.cardv.end()) out.cardv_status.calib_status = it->second;

  // Runtime class: transport NEVER implies process (F5).
  if (out.health.process == ProcessPresence::Absent) {
    out.health.runtime_class = AdasRuntimeClass::A_ProcessAbsent;
  } else if (!s.frame_seen) {
    out.health.runtime_class = AdasRuntimeClass::Unknown;
  } else if (out.stale) {
    out.health.runtime_class = AdasRuntimeClass::C_InputPathSuspect;
  } else {
    out.health.runtime_class = AdasRuntimeClass::Ok;
  }
  return out;
}

struct StockProviderConfig {
  std::uint64_t stale_after_ms = 500;
};

class StockADASProvider : public IAdasProvider {
 public:
  explicit StockADASProvider(StockProviderConfig cfg = {}) : cfg_(cfg) {}
  void Ingest(const StockSnapshot& s) { last_ = s; has_ = true; }
  std::string Name() const override { return "StockADASProvider"; }
  AdasState Poll() const override {
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
