// Host smoke for EF-A01..A04+A06. Compiles with: g++ -std=c++17 -I include tests/smoke_enhance.cpp
#include <cassert>
#include <iostream>
#include "c2m/adas/mock_adas_provider.hpp"
#include "c2m/adas/stock_adas_provider.hpp"
#include "c2m/core/c2m_enhance.hpp"
#include "c2m/display/m4_adapter.hpp"
#include "c2m/road/road_provider.hpp"

int main() {
  using namespace c2m;
  // 1. NormalizeStock pure function
  adas::StockSnapshot snap;
  snap.now_ms = 1000;
  snap.last_frame_ms = 900;
  snap.frame_id = 42;
  snap.libflow_connected = true;
  snap.cardv_connected = true;
  snap.nums["vehicleWarning"] = {{{"vehicle_id", 3}, {"headway", 1.2}, {"warning_level", 2}, {"fcw", 1}}};
  snap.nums["vehicleMeasure"] = {{{"vehicle_class", 1},
                                  {"vehicle_id", 3},
                                  {"vehicle_width", 1.8},
                                  {"longitude_dist", 6.5},
                                  {"lateral_dist", 0.4},
                                  {"ttc", 1.1},
                                  {"is_crucial", 1},
                                  {"is_second_crucial", 0}}};
  adas::AdasState s = adas::NormalizeStock(snap);
  assert(!s.stale);
  assert(s.lead_distance_m.has_value() && s.lead_distance_m.value() > 6.0f);
  assert(s.fcw.active);

  // 2. EnhanceCore tick with mock
  auto core = core::MakeMockCore("fcw");
  display::DisplayState d = core->Tick(2000, 52);
  assert(d.warning.fcw);
  assert(d.ego_speed_kmh == 52);

  // 3. M4Adapter L2 vs L3 gating
  display::M4Adapter l2(display::M4Config{false}, nullptr);
  display::M4Adapter l3(display::M4Config{true}, nullptr);
  d.system.brightness = 7;
  assert(!l2.PlanMessages(d).empty());  // harmless brightness allowed
  assert(l3.PlanMessages(d).size() >= l2.PlanMessages(d).size());

  // 4. Road fusion
  road::SpeedLimitState lim =
      road::FuseSpeedLimit(60, 0.9f, 50, 0.8f, 50, 0.9f);
  assert(lim.limit_kmh.has_value() && lim.limit_kmh.value() == 60 && lim.source == "camera");

  std::cout << "smoke_enhance: OK\n";
  return 0;
}
