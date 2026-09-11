#!/usr/bin/env python3
"""Gate E test (SYNTHETIC — R7): fixture integration, NOT captured-wire proof.

Uses build/fixtures/*.bin (stand-ins for hardware pcap frames until a real
capture exists). Proves the decoder→normalizer consumer pipeline handles the
project's stock-compatible fixture contract. Real EN frame compatibility stays
UNKNOWN until L1 passive capture.
"""
from pathlib import Path
from normalize_adas import normalize_stock
from libflow_protocol import decode_ws_binary

FIX = Path("build/fixtures")


def inner_to_snapshot(decoded_inners: list[dict]) -> dict:
    nums: dict[str, list] = {}
    for inner in decoded_inners:
        key = inner["key"]
        body = inner["data"]
        # Mechanical lift (no semantics): stock laneWarningRes nests the flag as
        # data.ldw_info.deviate_state (M4_STATIC_PROTOCOL_V1 §6). The transport
        # decoder lifts it so snapshot rows stay flat measurement rows.
        if key == "laneWarningRes" and isinstance(body, dict):
            body = dict(body)
            ldw = body.get("ldw_info", {})
            if isinstance(ldw, dict) and "deviate_state" in ldw:
                body["deviate_state"] = ldw["deviate_state"]
        nums.setdefault(key, []).append(body) if isinstance(body, dict) else nums.setdefault(key, []).extend(body)
    return {"now_ms": 1100, "last_frame_ms": 1000, "frame_id": 42,
            "libflow_reachable": True, "subscription_active": True,
            "cardv_reachable": False, "frame_seen": True,
            "nums": nums, "cardv": {}}


def main():
    inners = []
    for f in sorted(FIX.glob("*.bin")):
        r = decode_ws_binary(f.read_bytes())
        assert not r.warnings, (f.name, r.warnings)
        assert r.outer["source"] == "AdasScreenService", r.outer
        inners.append(r.inner)
        print(f"decoded {f.name}: topic={r.outer['topic']} key={r.inner['key']}")
    s = normalize_stock(inner_to_snapshot(inners))
    assert not s["stale"] and s["runtime_class"] == "Ok", s
    assert s["fcw"]["active"] is True, s["fcw"]          # fcw=2 explicit field
    assert s["pcw"]["active"] is True, s["pcw"]          # is_danger
    assert s["ldw"]["active"] is True, s["ldw"]          # deviate_state=1
    assert s["lead"]["reason"] == "crucial", s["lead"]   # is_crucial marker
    # DisplayState-level view (minimal projection, mirrors BuildFromAdas)
    disp = {"objects": len(s["vehicles"]) + len(s["pedestrians"]),
            "warnings": {"fcw": s["fcw"]["active"], "pcw": s["pcw"]["active"], "ldw": s["ldw"]["active"]}}
    assert disp == {"objects": 2, "warnings": {"fcw": True, "pcw": True, "ldw": True}}, disp
    print("SYNTHETIC fixture-path smoke: OK (captured-wire proof still UNKNOWN)")


if __name__ == "__main__":
    main()
