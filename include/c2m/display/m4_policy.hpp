#pragma once
// Canonical M4 safety policy (review F2). Single source of truth in C++;
// projection in tools/m4/m4_policy.json, parity-tested by test_m4_policy.py.
//
// L2 (harmless info-class, replayable only stationary + owner-approved):
//   DispBrightSet, StorageStatus, ScreenModeSet, ClientConn
// Everything else (all ADAS/libflow keys, AdasStatus/Calib, GPSSpeed/GPSLevel,
// RecordVoice, unknown) is DENY until runtime proof exists. Default-deny.
// L3 semantic injection: BLOCKED (Gate F) — no encoder exists yet.
#include <cstdint>
#include <string>

namespace c2m {
namespace display {

enum class M4Verdict : std::uint8_t { AllowL2 = 0, Deny = 1 };

struct M4Policy {
  static M4Verdict ClassifyJsonUuid(const std::string& uuid) {
    return (uuid == "DispBrightSet" || uuid == "StorageStatus" || uuid == "ScreenModeSet" ||
            uuid == "ClientConn")
               ? M4Verdict::AllowL2
               : M4Verdict::Deny;
  }
  // Inner libflow keys + cardv semantic uuids: always DENY at L2/L3-blocked.
  static M4Verdict ClassifyInnerKey(const std::string& key) {
    (void)key;
    return M4Verdict::Deny;
  }
};

}  // namespace display
}  // namespace c2m
