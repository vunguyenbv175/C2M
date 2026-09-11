#pragma once
// c2m-enhance core — EF-A04, R5/R9 hardened.
// The core depends ONLY on IDisplayPlanner (pure). It never sees a sender,
// a transmitter, or a capability token: read-only by type construction.
// TickResult.planned_messages is populated from the planner (R9).
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
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
  std::uint64_t loop_period_ms = 200;
};

struct TickResult {
  display::DisplayState display;
  std::size_t planned_messages = 0;
};

class EnhanceCore {
 public:
  EnhanceCore(EnhanceConfig cfg, std::shared_ptr<adas::IAdasProvider> adas,
              std::shared_ptr<display::IDisplayPlanner> disp, EventBus* bus = nullptr)
      : cfg_(cfg), adas_(adas), disp_(disp), owned_bus_(bus ? nullptr : new EventBus()),
        bus_(bus ? bus : owned_bus_.get()) {}

  // Read-only tick: poll ADAS at caller time -> DisplayState -> pure Plan.
  TickResult Tick(std::uint64_t now_ms, int ego_speed_raw = -1) {
    adas::AdasState a = adas_->PollAt(now_ms);
    display::DisplayState d = display::BuildFromAdas(a, ego_speed_raw);
    std::vector<display::PlannedMessage> planned = disp_->Plan(d);
    ServiceHealth h{adas_->Name(), adas_->HealthyAt(now_ms), now_ms,
                    "planned=" + std::to_string(planned.size())};
    registry_.SetHealth(h);
    registry_.SetHealth(ServiceHealth{disp_->Name(), true, now_ms, "planner-only"});
    if (a.fcw.active || a.pcw.active || a.ldw.active)
      bus_->Publish(Event{"adas", "warning", now_ms, "stock warning active"});
    last_ = d;
    return TickResult{d, planned.size()};
  }

  ProviderRegistry& Registry() { return registry_; }
  EventBus& Bus() { return *bus_; }
  display::DisplayState Last() const { return last_; }

 private:
  EnhanceConfig cfg_;
  std::shared_ptr<adas::IAdasProvider> adas_;
  std::shared_ptr<display::IDisplayPlanner> disp_;
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
