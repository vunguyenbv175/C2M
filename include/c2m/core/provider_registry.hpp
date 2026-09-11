#pragma once
// ProviderRegistry + Health — EF-A04.
#include <cstdint>
#include <map>
#include <string>
namespace c2m {
namespace core {
struct ServiceHealth {
  std::string name;
  bool healthy = false;
  std::uint64_t last_ok_ms = 0;
  std::string detail;
};
class ProviderRegistry {
 public:
  void SetHealth(const ServiceHealth& h) { health_[h.name] = h; }
  std::map<std::string, ServiceHealth> Snapshot() const { return health_; }
  bool AllHealthy() const {
    for (auto& kv : health_)
      if (!kv.second.healthy) return false;
    return true;
  }

 private:
  std::map<std::string, ServiceHealth> health_;
};
}  // namespace core
}  // namespace c2m
