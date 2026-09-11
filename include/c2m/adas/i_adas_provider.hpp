#pragma once
// IAdasProvider — EF-A01. Every ADAS source implements this.
// Time is explicit: PollAt(now_ms) so freshness advances with the caller clock
// (review R1). Implementations must not freeze age at ingest time.
#include <cstdint>
#include <string>
#include "c2m/adas/adas_state.hpp"

namespace c2m {
namespace adas {

class IClock {
 public:
  virtual ~IClock() = default;
  virtual std::uint64_t NowMs() const = 0;
};

class ManualClock : public IClock {
 public:
  explicit ManualClock(std::uint64_t t = 0) : t_(t) {}
  void Set(std::uint64_t t) { t_ = t; }
  std::uint64_t NowMs() const override { return t_; }

 private:
  std::uint64_t t_;
};

class IAdasProvider {
 public:
  virtual ~IAdasProvider() = default;
  virtual std::string Name() const = 0;
  // Non-blocking. Returns stale state on timeout; never throws to caller.
  virtual AdasState PollAt(std::uint64_t now_ms) const = 0;
  virtual bool HealthyAt(std::uint64_t now_ms) const = 0;
};

}  // namespace adas
}  // namespace c2m
