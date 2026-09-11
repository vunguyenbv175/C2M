#pragma once
// EventBus — EF-A04. Tiny sync bus; enhancement-only, never in stock path.
#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <vector>
namespace c2m {
namespace core {
struct Event {
  std::string topic;  // adas|display|road|tpms|system
  std::string key;
  std::uint64_t timestamp_ms = 0;
  std::string summary;
};
class EventBus {
 public:
  using Handler = std::function<void(const Event&)>;
  void Publish(const Event& e) {
    log_.push_back(e);
    if (log_.size() > 512) log_.erase(log_.begin());
    auto it = subs_.find(e.topic);
    if (it != subs_.end())
      for (auto& h : it->second) h(e);
  }
  void Subscribe(const std::string& topic, Handler h) { subs_[topic].push_back(h); }
  const std::vector<Event>& Log() const { return log_; }

 private:
  std::map<std::string, std::vector<Handler>> subs_;
  std::vector<Event> log_;
};
}  // namespace core
}  // namespace c2m
