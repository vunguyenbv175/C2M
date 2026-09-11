#pragma once
// Display interfaces — Gate B/R5 type-level read-only split.
// IDisplayPlanner is pure: planning a render must never touch stock transport.
// Stock-facing transmission requires IStockTransmitter + an AllowTransmit token
// that EnhanceCore never holds. Future adapters cannot smuggle writes through
// the core's read-only path.
#include <cstdint>
#include <string>
#include <utility>
#include <vector>
#include "c2m/display/display_state.hpp"

namespace c2m {
namespace display {

struct PlannedMessage {
  std::string channel;
  std::string payload;
};

// Capability token for stock-facing transmission. Only daemon commissioning
// code (with explicit owner-approved mode) may construct and pass one.
struct AllowTransmit {
  explicit AllowTransmit() = default;
};

enum class TransmitStatus : std::uint8_t {
  DryRun = 0,         // planned only; no sender configured
  BlockedReadOnly = 1,  // no capability presented
  BlockedL3 = 2,         // semantic content while L3 is BLOCKED (Gate F)
  SendOk = 3,
  SendFailed = 4
};

class IDisplayPlanner {
 public:
  virtual ~IDisplayPlanner() = default;
  virtual std::string Name() const = 0;
  virtual std::vector<PlannedMessage> Plan(const DisplayState& s) const = 0;
};

class IStockTransmitter {
 public:
  virtual ~IStockTransmitter() = default;
  virtual TransmitStatus Transmit(const std::vector<PlannedMessage>& msgs,
                                  AllowTransmit) = 0;
};

}  // namespace display
}  // namespace c2m
