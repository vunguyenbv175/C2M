#!/usr/bin/env python3
"""Scan firmware for transport + navigation protocol constants with offsets.

Usage: python scan_protocol_constants.py <firmware.bin> [--json]
Covers: BLE/GATT/UUID/notify/MTU/NimBLE/Bluedroid, SPP/RFCOMM/A2DP/HFP,
TCP/UDP/HTTP/WS/MQTT/socket/DNS/URLs/IPs/ports/SSID/AP/STA,
UART/baud/CDC/CH340/CP210x/AA55/CRC, magic/len/seq/cmd/CRC/XOR/COBS/SLIP/protobuf/JSON,
nav vocabulary EN+VI (ASCII + diacritic-less), VietMap/S1/S2/HUD tokens.

Each hit: {category, needle, offset, count}. Deterministic, no deps.
"""
import sys,json
GROUPS={
 "ble":[b"BLE",b"GATT",b"UUID",b"notify",b"indicate",b"advertise",b"bond",b"MTU",b"NimBLE",b"nimble",b"Bluedroid",b"esp_ble",b"esp_gatt",b"esp_gap",b"FFF0",b"FFF1",b"FFF2",b"FFF3",b"8a7e",b"VIETMAP_HUD",b"Promax XL",b"0000fff",b"00805f9b34fb",b"180A",b"2A26"],
 "bt_classic":[b"SPP",b"RFCOMM",b"BT_SPP",b"SerialPort",b"A2DP",b"HFP",b"ESP32SPP"],
 "net":[b"TCP",b"UDP",b"HTTP",b"HTTPS",b"WebSocket",b"MQTT",b"socket",b"connect",b"listen",b"DNS",b"SSID",b"SoftAP",b"WiFiManager",b"captive",b"192.168.",b"kimdung.github.io",b"api.openai.com",b"User-Agent",b"Bearer",b"BEGIN CERTIFICATE",b"ota_check",b"ota_update",b"/update"],
 "uart_usb":[b"UART_NUM",b"uart_driver",b"baud",b"USB serial",b"CDC",b"CH340",b"CP210",b"tinyusb",b"cdc_acm",b"A55A",b"/target_mac.txt",b"/poi.jpg",b"/logo.jpg",b"littlefs",b"spiffs"],
 "framing":[b"CRC",b"checksum",b"XOR",b"COBS",b"SLIP",b"protobuf",b"nanopb",b"cJSON",b"MessagePack",b"TLV",b"IMG_START",b"IMG_END",b"LOAD",b"DTBK"],
 "nav_json":[b'"nav"',b'"spd"',b'"lim"',b'"trn"',b'"dst"',b'"exit"',b'"st"',b'"eta"',b'"rmin"',b'"rkm"',b'"avg"',b'"avgL"',b'"alrs"',b'"lan"',b'"proto"',b'"want"',b'"can"',b'"transport"',b'"rate"',b'"fields"',b'"t":"pong"',b'"t":"ping"',b'"t":"dev"'],
 "nav_en":[b"roundabout",b"uturn",b"lane",b"speed_limit",b"camera",b"radar",b"traffic",b"school",b"hazard",b"heading",b"compass",b"reroute",b"destination",b"overspeed",b"tunnel",b"junction",b"navigation"],
 "vietmap":[b"vietmap",b"VietMap",b"VIETMAP",b"ProMax",b"promax",b"S1",b"S2",b"VML",b"vml"],
 "obd":[b"OBD",b"Vlink",b"Viecar",b"FAKE_OBD",b"AT D",b"AT Z",b"ELM",b"VGATE",b"icar"],
}
def scan(path):
    d=open(path,"rb").read()
    out=[]
    for cat,needles in GROUPS.items():
        for n in needles:
            c=d.count(n)
            if c:
                out.append({"category":cat,"needle":n.decode(errors="replace"),"count":c,"first_offset":f"0x{d.find(n):X}"})
                print(f"{cat:10s} {n.decode(errors='replace'):22s} x{c:<4d} @0x{d.find(n):X}")
    return out
if __name__=="__main__":
    r=scan(sys.argv[1])
    if "--json" in sys.argv: print(json.dumps(r,indent=2))
