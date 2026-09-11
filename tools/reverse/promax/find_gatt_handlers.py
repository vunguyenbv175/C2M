#!/usr/bin/env python3
"""Find GATT handler evidence without a disassembler (string-structure fallback).

Usage: python find_gatt_handlers.py <firmware.bin> [--json]
Reports: 8a7e UUID block, FFF block, advert/scan role strings, service-creation
API remnants, attr-db candidates, and -- what is MISSING for LEVEL 1.
Pure python, deterministic. A Ghidra/IDA Xtensa run is still required for TRUE handlers.
"""
import re, sys, json
PATS = {
 "uuid_8a7e": rb"8a7e000[123]-4d6e-4c48-9a9d-484c504c0001",
 "fff": rb"FFF[0123]",
 "adv": rb"VIETMAP_HUD|Promax XL|startAdvert",
 "scan": rb"Dump scan|getServices|registerForNotify|writeValue|readValue",
 "svc_api": rb"createService|registerApp|RegEvt|CreateEvt|ConfEvt|SetValue|indicate|notify",
 "ble_lib": rb"BLEUUID|esp_ble|esp_gatt|esp_gap|NimBLE|nimble|Bluedroid|btc_gap_ble",
 "cccd": rb"CCCD|2902|registerForNotify|characteristicvaluechanged",
}
def main():
    p = sys.argv[1]; d = open(p, "rb").read()
    out = {"image": p, "size": len(d), "hits": [], "level1_gaps": []}
    for name, pat in PATS.items():
        for m in re.finditer(pat, d):
            s = m.start()
            ctx = d[max(0, s-80):s+120]
            txt = "".join(chr(c) if 32 <= c < 127 else "." for c in ctx)
            out["hits"].append({"group": name, "offset": f"0x{s:X}", "match": m.group(0)[:80].decode(errors="replace"), "context": txt[:200]})
            print(f"[{name}] 0x{s:X} {m.group(0)[:60]!r}")
    gaps = []
    if d.count(b"createCharacteristic") == 0: gaps.append("no createCharacteristic string: characteristic creation callsite unproven")
    if d.count(b"setCallbacks") == 0: gaps.append("no setCallbacks/onWrite/onRead strings: callback registration unproven")
    if d.count(b"esp_gatts_attr_db") == 0: gaps.append("no esp_gatts_attr_db_t symbol: static attr-db unproven")
    if d.count(b"8a7e") and d.count(b"createService") == 0 and "XL" in p: gaps.append("XL has 8a7e but no createService string (NimBLE path differs): role mapping needs disassembly")
    out["level1_gaps"] = gaps
    for g in gaps: print("GAP:", g)
    if "--json" in sys.argv: print(json.dumps(out, indent=2))
if __name__ == "__main__": main()
