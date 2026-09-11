#pragma once
#include <string>
#include <vector>
#include "c2m/display/i_display_adapter.hpp"
namespace c2m {
namespace display {
// Records plans for host tests / Web overlay demo. Loopback only, never stock.
class MockDisplayAdapter : public IDisplayPlanner {
 public:
  std::string Name() const override { return "MockDisplayAdapter"; }
  std::vector<PlannedMessage> Plan(const DisplayState& s) const override {
    last_ = s;
    count_++;
    return {};
  }
  mutable DisplayState last_;
  mutable int count_ = 0;
};
}  // namespace display
}  // namespace c2m
