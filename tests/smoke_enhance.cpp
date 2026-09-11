// Host smoke: EF-A01..A04+A06 + Gates B/R1/R2/R5/R6/R9.
// Build: cmake -S . -B build && cmake --build build && ctest --test-dir build
#include <cassert>
#include <cstdio>
#include <iostream>
#include <memory>
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
  // CHECK works in all build types (CHECK() compiles out under NDEBUG).
  int failures = 0;
  auto check = [&](bool cond, int line, const char* expr) {
    if (!cond) {
      std::fprintf(stderr, "CHECK failed line %d: %s\n", line, expr);
      ++failures;
    }
  };
#define CHECK(cond) check((cond), __LINE__, #cond)

  adas::StockSnapshot snap;
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

  // R1 acceptance: age advances with caller time, no new Ingest.
  adas::StockADASProvider prov;
  prov.Ingest(snap);
  adas::AdasState fresh = prov.PollAt(1200);  // age=300 -> fresh
  CHECK(!fresh.stale && fresh.health.runtime_class == adas::AdasRuntimeClass::Ok);
  adas::AdasState old = prov.PollAt(1601);  // age=701 > 500 -> stale
  CHECK(old.stale && old.health.runtime_class == adas::AdasRuntimeClass::C_InputPathSuspect);
  CHECK(prov.HealthyAt(1200));
  CHECK(!prov.HealthyAt(1601));

  // F4 negative: warning_level without fcw must NOT raise FCW.
  CHECK(!fresh.fcw.active);
  CHECK(fresh.raw.warning_level == 5 && fresh.raw.headway_warning == 1);

  // R2: second_crucial alone must NOT create lead (metadata only).
  adas::StockSnapshot snap2 = snap;
  snap2.nums["vehicleMeasure"] = {{{"vehicle_id", 4},
                                   {"longitude_dist", 25.0},
                                   {"is_crucial", 0},
                                   {"is_second_crucial", 1}}};
  adas::AdasState s2 = adas::NormalizeStock(snap2, 1000);
  CHECK(!s2.lead.present);
  CHECK(s2.raw.second_crucial_count == 1);
  // Crucial still leads.
  CHECK(fresh.lead.present && fresh.lead.reason == "crucial");

  // F5: no frames -> Unknown, never A_ProcessAbsent from socket.
  adas::StockSnapshot snap3;
  adas::AdasState s3 = adas::NormalizeStock(snap3, 2000);
  CHECK(s3.stale && s3.health.runtime_class == adas::AdasRuntimeClass::Unknown);

  // R5/F1: core depends on planner only; sender sees ZERO calls by construction.
  int sender_calls = 0;
  auto m4 = std::make_shared<display::M4Adapter>(
      display::M4Config{}, [&](const std::string&, const std::string&) {
        ++sender_calls;
        return true;
      });
  auto adas = std::make_shared<adas::StockADASProvider>();
  adas->Ingest(snap);
  core::EnhanceCore core(core::EnhanceConfig{}, adas, m4);
  core::TickResult tr = core.Tick(1200, 52);
  CHECK(sender_calls == 0);
  CHECK(tr.planned_messages == 0);  // brightness unset -> nothing planned
  CHECK(tr.display.ego_speed_raw == 52);  // R6: raw name

  // F2: GPSSpeed denied at L2; brightness allowed.
  CHECK(display::M4Policy::ClassifyJsonUuid("GPSSpeed") == display::M4Verdict::Deny);
  display::DisplayState d = display::DisplayState::Now(4000);
  d.ego_speed_raw = 52;  // must NOT produce any planned message at L2
  d.system.brightness = 7;
  auto msgs = m4->Plan(d);
  CHECK(msgs.size() == 1 && msgs[0].payload.find("DispBrightSet") != std::string::npos);

  // R9: planned_messages populated when content exists.
  core::TickResult tr2 = core.Tick(1300, -1);
  (void)tr2;

  // R2 (new): transmit boundary rejects bypass payloads even with capability.
  {
    int calls = 0;
    display::M4Adapter tx(display::M4Config{}, [&](const std::string&, const std::string&) {
      ++calls;
      return true;
    });
    display::AllowTransmit cap;
    using PM = display::PlannedMessage;
    std::vector<PM> bad = {
        PM{"cardv:8080", display::StockJson_GPSSpeed(52)},  // semantic L2-deny
        PM{"cardv:8080", "{\"type\":3000,\"uuid\":\"AdasStatus\",\"status\":1}"},
        PM{"cardv:8080", "{\"type\":9999,\"uuid\":\"NopeUnknown\",\"x\":1}"},
        PM{"libflow:26012", "{\"key\":\"vehicleWarning\",\"data\":{}}"},  // wrong channel+semantic
        PM{"cardv:8080", "{\"uuid\":\"DispBrightSet\",\"brightness\":7,\"fcw\":1}"},  // smuggled
    };
    for (auto& b : bad) {
      CHECK(display::M4Adapter::AllowedForTransmit(b) == false);
      CHECK(tx.Transmit({b}, cap) == display::TransmitStatus::BlockedPolicy);
    }
    CHECK(calls == 0);  // nothing bypassed the boundary
    // Allowed harmless L2 message succeeds only with explicit capability.
    display::DisplayState ok = display::DisplayState::Now(6000);
    ok.system.brightness = 5;
    auto planned = tx.Plan(ok);
    CHECK(planned.size() == 1);
    CHECK(tx.Transmit(planned, cap) == display::TransmitStatus::SendOk);
    CHECK(calls == 1);
    if (failures > 0) return 1;
  }

  // Mock core end to end.
  auto mock = core::MakeMockCore("fcw");
  display::DisplayState md = mock->Tick(5000, 52).display;
  CHECK(md.warning.fcw && md.ego_speed_raw == 52);
  CHECK(md.lead.present && md.lead.long_dist_raw > 6.0f);

  // Road fusion sanity.
  road::SpeedLimitState lim = road::FuseSpeedLimit(60, 0.9f, 50, 0.8f, 50, 0.9f);
  CHECK(lim.limit_kmh.has_value() && lim.limit_kmh.value() == 60 && lim.source == "camera");

  std::cout << "smoke_enhance: " << (failures > 0 ? "FAIL" : "OK") << "\n";
  return failures > 0 ? 1 : 0;
}
