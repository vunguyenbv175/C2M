#pragma once
// MockADASProvider — host-sim + Web V0 scenarios. No hardware needed.
// Sole-driver semantics match NormalizeStock (Gate B).
#include <cstdint>
#include <string>
#include "c2m/adas/i_adas_provider.hpp"

namespace c2m {
namespace adas {

struct MockScenario {
  std::string name = "idle";  // idle|lead|fcw|ldw|ped
};

class MockADASProvider : public IAdasProvider {
 public:
  explicit MockADASProvider(MockScenario sc = {}) : sc_(sc), tick_(0) {}
  void SetScenario(MockScenario sc) { sc_ = sc; }
  std::string Name() const override { return "MockADASProvider:" + sc_.name; }
  AdasState PollAt(std::uint64_t now_ms) const override {
    AdasState s;
    s.timestamp_ms = now_ms;
    s.frame_id = tick_;
    s.stale = false;
    s.health.frame_seen = true;
    s.health.libflow_reachable = true;
    s.health.subscription_active = true;
    s.health.runtime_class = AdasRuntimeClass::Ok;
    if (sc_.name == "lead" || sc_.name == "fcw") {
      VehicleObject v;
      v.id = 1;
      v.vehicle_class = 1;
      v.long_dist = (sc_.name == "fcw") ? 6.5f : 22.0f;
      v.ttc = (sc_.name == "fcw") ? 1.1f : 3.4f;
      v.is_crucial = true;
      s.vehicles.push_back(v);
      s.lead = LeadInfo{true, "crucial", v.long_dist, v.ttc};
      if (sc_.name == "fcw") {
        s.fcw.active = true;
        s.fcw.level = 2;
        s.fcw.source = WarningSource::Stock;
        s.fcw.evidence = Evidence::HighConfidence;
      }
    }
    if (sc_.name == "ldw") {
      s.lane.deviate_state = 1;
      s.raw.deviate_state = 1;
      s.ldw.active = true;
      s.ldw.level = 1;
      s.ldw.source = WarningSource::Stock;
      s.ldw.evidence = Evidence::HighConfidence;
    }
    if (sc_.name == "ped") {
      PedestrianObject p;
      p.id = 7;
      p.world_x = 1.2f;
      p.is_danger = true;
      p.ttc = 1.4f;
      s.pedestrians.push_back(p);
      s.pcw.active = true;
      s.pcw.source = WarningSource::Stock;
      s.pcw.evidence = Evidence::HighConfidence;
    }
    return s;
  }
  bool HealthyAt(std::uint64_t now_ms) const override {
    (void)now_ms;
    return true;
  }

 private:
  MockScenario sc_;
  mutable std::uint64_t tick_;
};

}  // namespace adas
}  // namespace c2m
