#pragma once
// Diagnostics snapshot — EF-A04/EF-A05 read-only surface for /diagnostics.
#include <cstdint>
#include <map>
#include <string>
namespace c2m {
namespace diag {
struct DiagSnapshot {
  std::uint64_t timestamp_ms = 0;
  double soc_temp_c = 0.0;
  double mem_used_percent = 0.0;
  double storage_used_percent = 0.0;
  std::string sd_health = "UNKNOWN";
  std::string camera_state = "UNKNOWN";
  std::string adas_state = "UNKNOWN";
  std::string m4_state = "UNKNOWN";
  std::string gps_state = "UNKNOWN";
  std::string road_db_version = "none";
  std::map<std::string, bool> services;
};
}  // namespace diag
}  // namespace c2m
