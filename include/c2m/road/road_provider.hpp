#pragma once
// RoadIntelligence interfaces — EF-A06. Offline-first, host-preprocessed OSM.
#include <cstdint>
#include <optional>
#include <string>
#include <vector>
namespace c2m {
namespace road {
struct RoadSegment {
  std::int64_t id = -1;
  int maxspeed_kmh = -1;
  std::string road_class;
  bool oneway = false;
  double lat = 0, lon = 0;
};
struct RoadState {
  std::uint64_t timestamp_ms = 0;
  bool matched = false;
  RoadSegment segment;
  std::optional<int> osm_limit_kmh;
  double match_confidence = 0.0;
  std::string db_version = "none";
};
struct SpeedLimitState {
  std::optional<int> limit_kmh;
  float confidence = 0.0f;
  std::string source = "none";  // none|camera|osm|vietmap|fusion
  std::uint64_t age_ms = 0;
};
class IRoadProvider {
 public:
  virtual ~IRoadProvider() = default;
  virtual std::string Name() const = 0;
  virtual RoadState Query(double lat, double lon, double heading_deg) = 0;
};
class MockRoadProvider : public IRoadProvider {
 public:
  std::string Name() const override { return "MockRoadProvider"; }
  RoadState Query(double, double, double) override {
    RoadState s;
    s.matched = true;
    s.segment.maxspeed_kmh = 60;
    s.osm_limit_kmh = 60;
    s.match_confidence = 0.8;
    s.db_version = "mock-v1";
    return s;
  }
};
// Confidence fusion: camera TSR > VietMap (fresh) > OSM > none.
inline SpeedLimitState FuseSpeedLimit(std::optional<int> camera, float cam_conf,
                                      std::optional<int> osm, float osm_conf,
                                      std::optional<int> vietmap, float vm_conf,
                                      std::uint64_t age_ms = 0) {
  SpeedLimitState out;
  out.age_ms = age_ms;
  if (camera.has_value() && cam_conf >= 0.6f) {
    out.limit_kmh = camera;
    out.confidence = cam_conf;
    out.source = "camera";
  } else if (vietmap.has_value() && vm_conf >= 0.6f) {
    out.limit_kmh = vietmap;
    out.confidence = vm_conf;
    out.source = "vietmap";
  } else if (osm.has_value() && osm_conf >= 0.4f) {
    out.limit_kmh = osm;
    out.confidence = osm_conf;
    out.source = "osm";
  }
  return out;
}
}  // namespace road
}  // namespace c2m
