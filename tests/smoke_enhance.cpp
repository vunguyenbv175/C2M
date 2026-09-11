// Host smoke for EF-A01..A04+A06 + Gate B (F1/F2/F4/F5/F11/F12).
// Build: cmake -S . -B build && cmake --build build && ctest --test-dir build
#include <cassert>
#include <iostream>
#include <string>
#include <vector>
#include "c2m/adas/mock_adas_provider.hpp"
#include "c2m/adas/stock_adas_provider.hpp"
#include "c2m/core/c2m_enhance.hpp"
#include "c2m/display/m4_adapter.hpp"
#include "c2m/display/m4_policy.hpp"
#include "c2m/road/road_provider.hpp"

int main() {
  using namespace c2m;

  // 1. Sole-driver normalization (F4): warning_level alone must NOT raise FCW.
  adas::StockSnapshot snap;
  snap.now_ms = 1000;
  snap.last_frame_ms = 900;
  snap.frame_id = 42;
  snap.frame_seen = true;
  snap.libflow_reachable = true;
  snap.subscription_active = true;
  snap.nums["vehicleWarning"] = {{{"vehicle_id", 3},
                                  {"headway", 0.9},
                                  {"warning_level", 5},
                                  {"fcw", 0},
                                  {"headway_warning", 1}}};
  snap.nums["vehicleMeasure"] = {{{"vehicle_class", 1},
                                  {"vehicle_id", 3},
                                  {"longitude_dist", 6.5},
                                  {"lateral_dist", 0.4},
                                  {"ttc", 1.1},
                                  {"is_crucial", 1}}};
  adas::AdasState s = adas::NormalizeStock(snap);
  assert(!s.stale);
  assert(!s.fcw.active);  // F4 negative
  assert(s.raw.warning_level == 5 && s.raw.headway_warning == 1);
  assert(s.lead.present && s.lead.reason == "crucial");
  assert(s.health.runtime_class == adas::AdasRuntimeClass::Ok);

  // 2. No invented lead fallback (F11).
  adas::StockSnapshot snap2 = snap;
  snap2.nums["vehicleMeasure"] = {{{"vehicle_id", 4}, {"longitude_dist", 25.0}}};
  adas::AdasState s2 = adas::NormalizeStock(snap2);
  assert(!s2.lead.present);

  // 3. Honest health (F5): no frames -> Unknown, never A_ProcessAbsent.
  adas::StockSnapshot snap3;
  snap3.now_ms = 2000;
  adas::AdasState s3 = adas::NormalizeStock(snap3);
  assert(s3.stale && s3.health.runtime_class == adas::AdasRuntimeClass::Unknown);

  // 4. F1 read-only gate: sender must see ZERO calls through EnhanceCore.
  int sender_calls = 0;
  display::M4Adapter m4(display::M4Config{},
                        [&](const std::string&, const std::string&) {
                          ++sender_calls;
                          return true;
                        });
  auto adas = std::make_shared<adas::StockADASProvider>();
  adas->Ingest(snap);
  auto disp = std::make_shared<display::M4Adapter>(m4);
  core::EnhanceCore core(core::EnhanceConfig{}, adas, disp);
  core.Tick(3000, 52);
  assert(sender_calls == 0);  // F1 acceptance
  assert(disp->LastStatus() == display::TransmitStatus::BlockedReadOnly);

  // 5. F2: GPSSpeed/GPSLevel denied at L2 on both sides of the policy.
  assert(display::M4Policy::ClassifyJsonUuid("GPSSpeed") == display::M4Verdict::Deny);
  assert(display::M4Policy::ClassifyJsonUuid("DispBrightSet") == display::M4Verdict::AllowL2);
  display::DisplayState d = display::DisplayState::Now(4000);
  d.ego_speed_kmh = 52;  // must NOT produce any planned message at L2
  d.system.brightness = 7;
  auto msgs = m4.PlanMessages(d);
  assert(msgs.size() == 1);  // brightness only
  assert(msgs[0].second.find("DispBrightSet") != std::string::npos);

  // 6. Mock core tick still works end to end.
  auto mock = core::MakeMockCore("fcw");
  display::DisplayState md = mock->Tick(5000, 52).display;
  assert(md.warning.fcw && md.ego_speed_kmh == 52);

  // 7. Road fusion sanity.
  road::SpeedLimitState lim = road::FuseSpeedLimit(60, 0.9f, 50, 0.8f, 50, 0.9f);
  assert(lim.limit_kmh.has_value() && lim.limit_kmh.value() == 60 && lim.source == "camera");

  std::cout << "smoke_enhance: OK\n";
  return 0;
}
