#pragma once
// IAdasProvider — EF-A01. Every ADAS source implements this.
#include <string>
#include "c2m/adas/adas_state.hpp"

namespace c2m {
namespace adas {

class IAdasProvider {
 public:
  virtual ~IAdasProvider() = default;
  virtual std::string Name() const = 0;
  // Non-blocking. Returns stale state on timeout; never throws to caller.
  virtual AdasState Poll() const = 0;
  virtual bool Healthy() const = 0;
};

}  // namespace adas
}  // namespace c2m
