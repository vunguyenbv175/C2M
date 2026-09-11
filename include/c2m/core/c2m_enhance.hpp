#pragma once
// c2m-enhance core — EF-A04, Gate B hardened + Gate D skeleton support.
// Capability model (F1): the core NEVER transmits to stock-facing transport.
// It only produces DisplayState + planned messages. Transmission requires an
// explicit capability object owned by the daemon main, never by the core.
// Read-only is therefore structural, not a string label.
#include <cstdint>
#include <memory>
#include <string>
#include "c2m/adas/i_adas_provider.hpp"
#include "c2m/adas/mock_adas_provider.hpp"
#include "c2m/core/event_bus.hpp"
#include "c2m/core/provider_registry.hpp"
#include "c2m/display/display_state.hpp"
#include "c2m/display/i_display_adapter.hpp"
#include "c2m/display/m4_adapter.hpp"
#include "c2m/display/mock_display_adapter.hpp"

namespace c2m {
namespace core {

// Capability token: only code holding an AllowTransmit instance may invoke a
// stock-facing sender. EnhanceCore never holds one.
struct AllowTransmit {
  explicit AllowTransmit() = default;
};

struct EnhanceConfig {
  std::uint64_t loop_period_ms = 200;
};

struct TickResult {
  display::DisplayState display;
  display::TransmitStatus transmit = display::TransmitStatus::DryRun;
  std::size_t planned_messages = 0;
};

class EnhanceCore {
 public:
  EnhanceCore(EnhanceConfig cfg, std::shared_ptr<adas::IAdasProvider> adas,
              std::shared_ptr<display::IDisplayAdapter> disp, EventBus* bus = nullptr)
      : cfg_(cfg), adas_(adas), disp_(disp), owned_bus_(bus ? nullptr : new EventBus()),
        bus_(bus ? bus : owned_bus_.get()) {}

  // Read-only tick: poll ADAS -> DisplayState -> adapter planning/render.
  // IDisplayAdapter::Render is defined as non-transmitting; adapters that CAN
  // transmit (M4Adapter with sender) only do so via RenderEx(+AllowTransmit),
  // which the core never calls. Zero sender invocations by construction (F1).
  TickResult Tick(std::uint64_t now_ms, int ego_speed_kmh = -1) {
    adas::AdasState a = adas_->Poll();
    display::DisplayState d = display::BuildFromAdas(a, ego_speed_kmh);
    bool transmitted = disp_->Render(d);  // must be false for read-only adapters
    (void)transmitted;
    display::TransmitStatus st = display::TransmitStatus::DryRun;
    if (auto* m4 = dynamic_cast<display::M4Adapter*>(disp_.get())) st = m4->LastStatus();
    ServiceHealth h{adas_->Name(), adas_->Healthy(), now_ms,
                    std::string("transport=") + std::to_string(static_cast<int>(st))};
    registry_.SetHealth(h);
    registry_.SetHealth(ServiceHealth{disp_->Name(), true, now_ms, "planned-only"});
    if (a.fcw.active || a.pcw.active || a.ldw.active)
      bus_->Publish(Event{"adas", "warning", now_ms, "stock warning active"});
    last_ = d;
    return TickResult{d, st, 0};
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
