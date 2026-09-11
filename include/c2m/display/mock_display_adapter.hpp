#pragma once
#include <string>
#include <vector>
#include "c2m/display/i_display_adapter.hpp"
namespace c2m {
namespace display {
// Records renders for host tests / Web overlay demo.
class MockDisplayAdapter : public IDisplayAdapter {
 public:
  std::string Name() const override { return "MockDisplayAdapter"; }
  bool Render(const DisplayState& s) override {
    last_ = s;
    count_++;
    return true;
  }
  DisplayState last_;
  int count_ = 0;
};
}  // namespace display
}  // namespace c2m
