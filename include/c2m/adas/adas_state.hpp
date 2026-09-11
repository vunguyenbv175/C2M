#pragma once
// C2M Enhanced — normalized stock ADAS state (EF-A01).
// Mirrors docs/design/STOCK_ADAS_PROVIDER.md. No raw MessagePack/JSON here beyond
// preserved vendor spelling in comments. Header-only for embedded + host-sim.
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace c2m {
namespace adas {

enum class WarningSource : std::uint8_t { Unknown = 0, Stock = 1, Fused = 2, Custom = 3 };
enum class AdasRuntimeClass : std::uint8_t {
  Unknown = 0,
  A_ProcessAbsent = 1,
  B_CrashLoop = 2,
  C_InputPathSuspect = 3,
  D_InferenceSuspect = 4,
  E_WarningSuppressed = 5,
  F_DisplayAudioSuspect = 6,
  Ok = 7
};

struct WarningState {
  bool active = false;
  int level = 0;  // raw stock int preserved; enum meaning runtime-unverified
  WarningSource source = WarningSource::Unknown;
};

struct VehicleObject {
  int id = -1;
  int vehicle_class = -1;  // stock enum unverified
  float width = 0.0f;      // unit unverified, vendor key vehicle_width
  float long_dist = 0.0f;  // vendor key longitude_dist (spelling kept in decoder)
  float lat_dist = 0.0f;   // vendor key lateral_dist
  float ttc = 0.0f;
  bool is_crucial = false;
  bool is_second_crucial = false;
  float headway = 0.0f;  // joined from vehicleWarning when ids match
};

struct PedestrianObject {
  int id = -1;
  float world_x = 0.0f;
  float world_y = 0.0f;
  bool is_key = false;
  bool is_danger = false;
  float ttc_m = 0.0f;
  float ttc = 0.0f;
  bool have_bike = false;
};

struct LaneLine {
  std::string poly_coeff_repr = "UNKNOWN";  // bird_view_poly_coeff format unverified
  int label = -1;
  int type = -1;
};

struct LaneState {
  std::vector<LaneLine> lines;
  int deviate_state = 0;  // raw; 0 assumed no-deviation, must confirm runtime
  float turn_radius = 0.0f;
  bool turn_frequently = false;
};

struct CardvAdasStatus {
  bool stale = true;
  std::string adas_status = "UNKNOWN";
  std::string calib_status = "UNKNOWN";
  int gps_level = -1;
  int gps_speed = -1;  // VI-only GPSSpeed; EN may leave -1
};

struct AdasHealth {
  AdasRuntimeClass runtime_class = AdasRuntimeClass::Unknown;
  bool libflow_connected = false;
  bool cardv_connected = false;
  std::uint64_t age_ms = 0;
};

struct AdasState {
  std::uint64_t timestamp_ms = 0;
  std::uint64_t frame_id = 0;
  bool stale = true;

  AdasHealth health;
  LaneState lane;
  std::vector<VehicleObject> vehicles;
  std::vector<PedestrianObject> pedestrians;

  std::optional<float> lead_distance_m;
  std::optional<float> ttc_s;
  std::optional<int> detected_speed_limit;  // reserved for TSR fusion later

  WarningState fcw;
  WarningState ldw;
  WarningState pcw;
  CardvAdasStatus cardv_status;
};

}  // namespace adas
}  // namespace c2m
