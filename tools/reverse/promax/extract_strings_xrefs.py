#!/usr/bin/env python3
"""Extract ASCII strings with file offsets + cross-reference neighbouring context.

Usage: python extract_strings_xrefs.py <firmware.bin> [--json] [--min 4]
Also supports --scan : run protocol-relevant regex set (UUIDs, URLs, DTBK, JSON keys,
AT commands, IMG markers, VietMap tokens) and print offset+match.

Pure python; complements `strings` with offsets and context windows.
"""
import re,sys,json
MINL=4
PATTERNS={
 "ble_uuid_short":rb"(?:FFF0|FFF1|FFF2|FFF3|180A|2A26|18F0|2AF0|2AF1)",
 "uuid_8a7e":rb"8a7e000[123]-4d6e-4c48-9a9d-484c504c0001",
 "ble_name":rb"VIETMAP_HUD|Promax XL|Promax",
 "json_msg":rb"\{\"v\":1,\"t\":\"(?:pong|ping|dev)\"[^}]*\}",
 "json_keys":rb"\"(?:nav|spd|lim|trn|dst|exit|st|eta|rmin|rkm|avg|avgL|alrs|lan|proto|want|can|transport|rate|fields)\"",
 "dtbk":rb"DTBK;[ -~]{0,400}",
 "img":rb"IMG_(?:START|END)(?:;\d+)?",
 "at":rb"AT [A-Z0-9 ]{1,12}",
 "url":rb"https?://[A-Za-z0-9._/\-]{3,80}",
 "ip":rb"192\.168\.\d+\.\d+",
 "cert":rb"BEGIN CERTIFICATE",
 "idf":rb"esp-idf v[0-9.]+[^ \x00]{0,40}",
 "chip":rb"esp32(?:s3|c3|s2|c2|c6|h2)?",
 "nimb":rb"NimBLE|nimble|Bluedroid|btc_gap_ble|esp_ble|esp_gatt|esp_gap",
 "uart":rb"UART_NUM|uart_driver|baud|USB serial|tinyusb|cdc_acm",
 "wifi":rb"SSID|SoftAP|WiFiManager|captive|StartAP|ota_check|ota_update",
 "nav_en":rb"(?i)(?:turn|roundabout|lane|speed_limit|camera|hazard|heading|compass|reroute|destination)",
}
def strings_with_offsets(d,minl=MINL):
    out=[]; cur=b""; start=0
    for i,b in enumerate(d):
        if 32<=b<127:
            if not cur: start=i
            cur+=bytes((b,))
        else:
            if len(cur)>=minl: out.append((start,cur))
            cur=b""
    if len(cur)>=minl: out.append((start,cur))
    return out
def main():
    path=sys.argv[1]
    d=open(path,"rb").read()
    if "--scan" in sys.argv:
        hits=[]
        for name,pat in PATTERNS.items():
            for m in re.finditer(pat,d):
                s=m.start(); ctx=d[max(0,s-64):s+160]
                # trim to printable
                txt="".join(chr(c) if 32<=c<127 else "." for c in ctx[:160])
                hits.append({"pattern":name,"offset":f"0x{s:X}","off_dec":s,"match":m.group(0)[:200].decode(errors="replace"),"context":txt[:160]})
                print(f"[{name}] 0x{s:X} {m.group(0)[:120]!r}")
        if "--json" in sys.argv:
            print(json.dumps(hits,indent=2))
        return
    strs=strings_with_offsets(d,int(sys.argv[2]) if len(sys.argv)>2 and sys.argv[2].isdigit() else MINL)
    for off,s in strs:
        try: print(f"0x{off:X}: {s.decode()}")
        except: pass
if __name__=="__main__": main()
