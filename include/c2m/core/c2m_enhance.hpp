#pragma once
// c2m-enhance core — EF-A04. Read-only V0: health/status + registry + event bus.
// No control of safety-critical stock services yet.
#include <cstdint>
#include <memory>
#include <string>
#include "c2m/adas/i_adas_provider.hpp"
#include "c2m/adas/mock_adas_provider.hpp"
#include "c2m/core/event_bus.hpp"
#include "c2m/core/provider_registry.hpp"
#include "c2m/display/display_state.hpp"
#include "c2m/display/i_display_adapter.hpp"
#include "c2m/display/mock_display_adapter.hpp"

namespace c2m {
namespace core {

struct EnhanceConfig {
  std::string mode = "read-only";  // hard gate V0
  std::uint64_t loop_period_ms = 200;
};

class EnhanceCore {
 public:
  EnhanceCore(EnhanceConfig cfg, std::shared_ptr<adas::IAdasProvider> adas,
              std::shared_ptr<display::IDisplayAdapter> disp, EventBus* bus = nullptr)
      : cfg_(cfg), adas_(adas), disp_(disp), owned_bus_(bus ? nullptr : new EventBus()),
        bus_(bus ? bus : owned_bus_.get()) {}

  // One tick: poll ADAS -> build DisplayState -> render -> health/events.
  // Read-only: never touches stock recorder/config.
  display::DisplayState Tick(std::uint64_t now_ms, int ego_speed_kmh = -1) {
    adas::AdasState a = adas_->Poll();
    display::DisplayState d = display::BuildFromAdas(a, ego_speed_kmh);
    bool ok = disp_->Render(d);
    ServiceHealth h{adas_->Name(), adas_->Healthy(), now_ms, ok ? "render-ok" : "render-fail"};
    registry_.SetHealth(h);
    registry_.SetHealth(ServiceHealth{disp_->Name(), ok, now_ms, "display"});
    if (a.fcw.active || a.pcw.active || a.ldw.active)
      bus_->Publish(Event{"adas", "warning", now_ms, "stock warning active"});
    last_ = d;
    return d;
  }

  ProviderRegistry& Registry() { return registry_; }
  EventBus& Bus() { return *bus_; }
  display::DisplayState Last() const { return last_; }

 private:
  EnhanceConfig cfg_;
  std::shared_ptr<adas::IAdasProvider> adas_;
  std::shared_ptr<display::IDisplayAdapter> disp_;
  std::unique_ptr<EventBus> owned_bus_;
  EventBus* bus_;
  ProviderRegistry registry_;
  display::DisplayState last_;
};

inline std::shared_ptr<EnhanceCore> MakeMockCore(const std::string& scenario = "lead") {
  adas::MockScenario sc;
  sc.name = scenario;
  return std::make_shared<EnhanceCore>(
      EnhanceConfig{}, std::make_shared<adas::MockADASProvider>(sc),
      std::make_shared<display::MockDisplayAdapter>());
}

}  // namespace core
}  // namespace c2m
