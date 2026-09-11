#pragma once
// C2M Enhanced — normalized stock ADAS state (EF-A01, Gate B hardened).
// Schema verdicts: docs/reverse/STOCK_ADAS_SCHEMA_V2.md.
// Rule: only HIGH-CONFIDENCE *driver* fields feed normalized warnings.
// Everything else is preserved in AdasRaw and never promoted.
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace c2m {
namespace adas {

using NumMap = std::map<std::string, double>;

enum class WarningSource : std::uint8_t { Unknown = 0, Stock = 1, Fused = 2, Custom = 3 };

// Evidence tier of the semantic mapping (not of the raw bytes).
enum class Evidence : std::uint8_t { Unknown = 0, RawOnly = 1, HighConfidence = 2, Confirmed = 3 };

// Process presence comes ONLY from the device runtime collector
// (tools/device/collect_baseline.sh + classify_adas_state.py).
// A socket state must NEVER imply it (review F5).
enum class ProcessPresence : std::uint8_t { Unknown = 0, Present = 1, Absent = 2 };

enum class AdasRuntimeClass : std::uint8_t {
  Unknown = 0,
  A_ProcessAbsent = 1,  // allowed ONLY when process == Absent (collector proof)
  B_CrashLoop = 2,      // reserved: needs restart-loop evidence (not inferred here)
  C_InputPathSuspect = 3,
  D_InferenceSuspect = 4,  // reserved: needs model/IPU evidence
  E_WarningSuppressed = 5,  // reserved: needs inference-alive proof + no warning
  F_DisplayAudioSuspect = 6,  // reserved: needs display-path evidence
  Ok = 7
};

struct WarningState {
  bool active = false;
  int level = 0;  // raw stock int; enum meaning UNKNOWN per schema V2
  WarningSource source = WarningSource::Unknown;
  Evidence evidence = Evidence::Unknown;
};

struct VehicleObject {
  int id = -1;
  int vehicle_class = -1;  // RAW-ONLY
  float width = 0.0f;      // RAW-ONLY (unit unverified)
  float long_dist = 0.0f;  // RAW-ONLY (unit/sign unverified)
  float lat_dist = 0.0f;   // RAW-ONLY
  float ttc = 0.0f;        // RAW-ONLY
  bool is_crucial = false;
  bool is_second_crucial = false;
  float headway = 0.0f;  // RAW-ONLY, joined when ids match
};

struct PedestrianObject {
  int id = -1;
  float world_x = 0.0f;  // RAW-ONLY
  float world_y = 0.0f;  // RAW-ONLY
  bool is_key = false;   // RAW-ONLY: NEVER drives pcw
  bool is_danger = false;
  float ttc_m = 0.0f;  // RAW-ONLY
  float ttc = 0.0f;    // RAW-ONLY
  bool have_bike = false;
};

struct LaneLine {
  std::string poly_coeff_repr = "UNKNOWN";  // RAW-ONLY
  int label = -1;                           // RAW-ONLY
  int type = -1;                            // RAW-ONLY
};

struct LaneState {
  std::vector<LaneLine> lines;
  int deviate_state = 0;  // RAW value; enum UNKNOWN, sole LDW driver (HIGH-CONFIDENCE)
  float turn_radius = 0.0f;
  bool turn_frequently = false;
};

struct CardvAdasStatus {
  bool stale = true;
  std::string adas_status = "UNKNOWN";
  std::string calib_status = "UNKNOWN";
  int gps_level = -1;
  int gps_speed = -1;  // VI GPSSpeed; EN leaves -1
};

// Untouched stock numbers for debug/logging. Never drives warnings.
struct AdasRaw {
  NumMap vehicle_warning;
  int warning_level = 0;
  int headway_warning = 0;
  int vb_warning = 0;
  int sag_warning = 0;
  int key_pedestrian_count = 0;
  int second_crucial_count = 0;  // metadata only; never creates lead (R2)
  int deviate_state = 0;
};

struct AdasHealth {
  bool frame_seen = false;
  bool libflow_reachable = false;
  bool subscription_active = false;
  bool cardv_reachable = false;
  ProcessPresence process = ProcessPresence::Unknown;
  std::uint64_t age_ms = 0;
  AdasRuntimeClass runtime_class = AdasRuntimeClass::Unknown;
};

struct LeadInfo {
  bool present = false;
  std::string reason = "none";  // crucial | none (R2: no second_crucial fallback)
  float long_dist = 0.0f;       // RAW-ONLY unit
  float ttc = 0.0f;             // RAW-ONLY unit
};

struct AdasState {
  std::uint64_t timestamp_ms = 0;
  std::uint64_t frame_id = 0;
  bool stale = true;

  AdasHealth health;
  LaneState lane;
  std::vector<VehicleObject> vehicles;
  std::vector<PedestrianObject> pedestrians;

  LeadInfo lead;  // present ONLY on stock crucial markers (no invented fallback)
  std::optional<int> detected_speed_limit;  // reserved; stays empty until TSR proven

  WarningState fcw;
  WarningState ldw;
  WarningState pcw;
  CardvAdasStatus cardv_status;
  AdasRaw raw;
};

}  // namespace adas
}  // namespace c2m
