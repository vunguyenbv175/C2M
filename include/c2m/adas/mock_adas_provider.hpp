#pragma once
// MockADASProvider — host-sim + Web V0 scenarios. No hardware needed.
#include <cstdint>
#include <string>
#include <vector>
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
  AdasState Poll() override {
    AdasState s;
    s.timestamp_ms = ++tick_ * 100;
    s.frame_id = tick_;
    s.stale = false;
    s.health.runtime_class = AdasRuntimeClass::Ok;
    s.health.libflow_connected = true;
    if (sc_.name == "lead" || sc_.name == "fcw") {
      VehicleObject v;
      v.id = 1;
      v.vehicle_class = 1;
      v.long_dist = (sc_.name == "fcw") ? 6.5f : 22.0f;
      v.ttc = (sc_.name == "fcw") ? 1.1f : 3.4f;
      v.is_crucial = true;
      s.vehicles.push_back(v);
      s.lead_distance_m = v.long_dist;
      s.ttc_s = v.ttc;
      if (sc_.name == "fcw") {
        s.fcw.active = true;
        s.fcw.level = 2;
        s.fcw.source = WarningSource::Stock;
      }
    }
    if (sc_.name == "ldw") {
      s.lane.deviate_state = 1;
      s.ldw.active = true;
      s.ldw.level = 1;
      s.ldw.source = WarningSource::Stock;
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
    }
    return s;
  }
  bool Healthy() const override { return true; }

 private:
  MockScenario sc_;
  std::uint64_t tick_;
};

}  // namespace adas
}  // namespace c2m
