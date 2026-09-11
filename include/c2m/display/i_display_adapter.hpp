#pragma once
#include <string>
#include "c2m/display/display_state.hpp"
namespace c2m {
namespace display {
class IDisplayAdapter {
 public:
  virtual ~IDisplayAdapter() = default;
  virtual std::string Name() const = 0;
  // Returns false on transport error; must never throw into stock path.
  virtual bool Render(const DisplayState& s) = 0;
};
}  // namespace display
}  // namespace c2m
