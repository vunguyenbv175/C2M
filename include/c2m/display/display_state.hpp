#pragma once
// DisplayState — EF-A03. Provider-neutral display model.
// No M4 packet types allowed here (see M4_ADAPTER_DESIGN.md).
#include <algorithm>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>
#include "c2m/adas/adas_state.hpp"

namespace c2m {
namespace display {

struct DisplayObject {
  int id = -1;
  std::string kind = "vehicle";  // vehicle|pedestrian
  // RAW stock numbers (units/sign unverified per schema V2) — R6: no _m suffix.
  float lateral_raw = 0.0f;
  float longitudinal_raw = 0.0f;
  bool crucial = false;
};

struct LaneView {
  bool visible = false;
  int deviate_state = 0;
  bool ldw_active = false;
};

struct LeadView {
  bool present = false;
  std::string reason = "none";
  float long_dist_raw = 0.0f;  // RAW-ONLY unit (vendor longitude_dist)
  float ttc_raw = 0.0f;        // RAW-ONLY unit
};

struct NavState {
  bool active = false;
  std::string arrow = "none";  // none|left|right|straight|uturn
  int distance_raw = -1;  // provider units unverified (R6: no _m suffix)
  std::string road_name;
};

struct TpmsView {
  bool available = false;
  float pressures_bar[4] = {0, 0, 0, 0};  // FL FR RL RR when available
  bool alert = false;
  std::string alert_text;
};

struct CameraView {
  std::string mode = "3D";  // 3D|live (stock ScreenModeSet theme)
};

struct SystemView {
  bool recording = true;
  int storage_percent = -1;
  int wifi_clients = -1;
  int brightness = -1;
  std::string adas_status = "UNKNOWN";
};

struct WarningView {
  bool fcw = false;
  bool ldw = false;
  bool pcw = false;
  int max_level = 0;
};

struct DisplayState {
  std::uint64_t timestamp_ms = 0;
  // RAW GPS-derived speed (cardv GPSSpeed unit unverified — R6: no _kmh suffix).
  int ego_speed_raw = -1;  // -1 = unknown
  std::optional<int> speed_limit_kmh;  // empty until TSR/fusion proven
  float speed_limit_confidence = 0.0f;

  LaneView lane;
  LeadView lead;
  std::vector<DisplayObject> objects;
  WarningView warning;
  NavState navigation;
  TpmsView tpms;
  CameraView camera_view;
  SystemView system;

  static DisplayState Now(std::uint64_t now_ms) {
    DisplayState s;
    s.timestamp_ms = now_ms;
    return s;
  }
};

// Pure build step: AdasState (+ speed/system inputs) -> DisplayState.
// Host-testable without M4 hardware.
inline DisplayState BuildFromAdas(const adas::AdasState& a, int ego_speed_raw = -1,
                                  std::optional<int> fused_limit = std::nullopt,
                                  float fused_conf = 0.0f) {
  DisplayState d = DisplayState::Now(a.timestamp_ms);
  d.ego_speed_raw = ego_speed_raw;
  d.speed_limit_kmh = fused_limit.has_value() ? fused_limit : a.detected_speed_limit;
  d.speed_limit_confidence = fused_conf;
  d.lane.visible = !a.stale;
  d.lane.deviate_state = a.lane.deviate_state;
  d.lane.ldw_active = a.ldw.active;
  d.lead.present = a.lead.present;
  d.lead.reason = a.lead.reason;
  d.lead.long_dist_raw = a.lead.long_dist;
  d.lead.ttc_raw = a.lead.ttc;
  for (const auto& v : a.vehicles) {
    DisplayObject o;
    o.id = v.id;
    o.kind = "vehicle";
    o.lateral_raw = v.lat_dist;
    o.longitudinal_raw = v.long_dist;
    o.crucial = v.is_crucial;
    d.objects.push_back(o);
  }
  for (const auto& p : a.pedestrians) {
    DisplayObject o;
    o.id = p.id;
    o.kind = "pedestrian";
    o.lateral_raw = p.world_x;
    o.longitudinal_raw = p.world_y;
    o.crucial = p.is_danger;
    d.objects.push_back(o);
  }
  d.warning.fcw = a.fcw.active;
  d.warning.ldw = a.ldw.active;
  d.warning.pcw = a.pcw.active;
  d.warning.max_level = std::max({a.fcw.level, a.ldw.level, a.pcw.level});
  d.system.adas_status = a.cardv_status.adas_status;
  return d;
}

}  // namespace display
}  // namespace c2m
