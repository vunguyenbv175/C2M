#!/usr/bin/env python3
"""Parse a ProMax BLE capture into a packet table (READ-ONLY, no BLE I/O).

Inputs (one required):
  btsnoop_hci.log                 Android Bluetooth HCI snoop log (btsnoop v1)
  --tshark-json pkts.json         `tshark -r btsnoop_hci.log -T json` output
  --gatt gatt_map.csv             optional handle->UUID map: handle,uuid,name
                                  (handle as hex, e.g. 0x002a)

Output (--out table.json, plus human summary unless --quiet):
  rows: index, ts_iso, ts_raw_us, direction, hci, att_op, handle, uuid,
        payload_hex, payload_ascii, note
  extras decoded when present: ATT MTU exchange, LE conn interval.

Direction (documented, btsnoop standard):
  phone_to_air  = HCI packet SENT by phone host (btsnoop flags bit0 == 0)
  air_to_phone  = HCI packet RECEIVED by phone host (flags bit0 == 1)
Relative to ProMax: RX(ProMax receives) == phone_to_air ATT writes;
TX(ProMax sends) == air_to_phone ATT notify/indicate. Role labels are NOT
assigned here -- see correlate + analysis plan.

btsnoop timestamp = microseconds since 0000-01-01 + 0x00E03AB44A676000 offset
to Unix epoch (Wireshark convention); raw value always emitted too.

Usage:
  python parse_promax_ble_capture.py btsnoop_hci.log --out 05_packets/table.json
  python parse_promax_ble_capture.py --tshark-json pkts.json --out 05_packets/table.json
  python parse_promax_ble_capture.py btsnoop_hci.log --gatt 03_gatt/handles.csv --out 05_packets/table.json
Deterministic, stdlib only. Never touches BLE hardware.
"""
import sys
import os
import json
import struct
import csv
import datetime

BTSNOOP_EPOCH_OFFSET = 0x00E03AB44A676000

ATT_OPS = {
    0x01: "ErrorRsp", 0x02: "MTU_Req", 0x03: "MTU_Rsp",
    0x04: "FindInfo_Req", 0x05: "FindInfo_Rsp",
    0x06: "FindByType_Req", 0x07: "FindByType_Rsp",
    0x08: "ReadByType_Req", 0x09: "ReadByType_Rsp",
    0x0A: "Read_Req", 0x0B: "Read_Rsp", 0x0C: "ReadBlob_Req", 0x0D: "ReadBlob_Rsp",
    0x10: "ReadByGroup_Req", 0x11: "ReadByGroup_Rsp",
    0x12: "WRITE_REQ", 0x13: "Write_Rsp",
    0x16: "PrepWrite_Req", 0x17: "PrepWrite_Rsp", 0x18: "ExecWrite_Req", 0x19: "ExecWrite_Rsp",
    0x1B: "NOTIFY", 0x1D: "INDICATE", 0x1E: "Indicate_Confirm",
    0x52: "WRITE_CMD", 0xD2: "SignedWrite_CMD",
}
HANDLE_OPS = {0x01, 0x0A, 0x0B, 0x0C, 0x0D, 0x12, 0x13, 0x16, 0x17, 0x1B, 0x1D, 0x52, 0xD2}


def iso(ts_us):
    try:
        return datetime.datetime.fromtimestamp(
            (ts_us - BTSNOOP_EPOCH_OFFSET) / 1e6).isoformat(timespec="milliseconds")
    except Exception:
        return "UNKNOWN"


def ascii_of(b):
    return "".join(chr(x) if 32 <= x < 127 else "." for x in b)


def parse_acl(payload, row):
    if len(payload) < 4:
        row["note"] = "runt-ACL"
        return
    hf, alen = struct.unpack("<HH", payload[:4])
    row["acl_handle"] = hf & 0x0FFF
    l2 = payload[4:4 + alen]
    if len(l2) < 4:
        row["note"] = "runt-L2CAP"
        return
    llen, cid = struct.unpack("<HH", l2[:4])
    row["l2cap_cid"] = cid
    att = l2[4:4 + llen]
    if cid != 0x0004 or not att:
        row["note"] = "non-ATT-CID-0x%04x" % cid
        row["payload_hex"] = att.hex() if att else ""
        return
    op = att[0]
    row["att_op"] = "0x%02X" % op
    row["att_op_name"] = ATT_OPS.get(op, "UNKNOWN-0x%02X" % op)
    rest = att[1:]
    if op in HANDLE_OPS and len(rest) >= 2:
        row["handle"] = "0x%04x" % struct.unpack("<H", rest[:2])[0]
        rest = rest[2:]
    if op == 0x03 and len(rest) >= 2:  # MTU_Rsp: server RX MTU
        row["note"] = "ATT-MTU-server-rx=%d" % struct.unpack("<H", rest[:2])[0]
    elif op == 0x02 and len(rest) >= 2:
        row["note"] = "ATT-MTU-client-rx=%d" % struct.unpack("<H", rest[:2])[0]
    row["payload_hex"] = rest.hex()
    row["payload_ascii"] = ascii_of(rest)


def parse_evt(payload, row):
    if len(payload) < 2:
        row["note"] = "runt-EVT"
        return
    ev, plen = payload[0], payload[1]
    body = payload[2:2 + plen]
    row["att_op"] = "HCI-EVT-0x%02X" % ev
    if ev == 0x3E and body:  # LE Meta
        sub = body[0]
        row["att_op_name"] = "LE-Meta-0x%02X" % sub
        if sub == 0x01 and len(body) >= 13:  # LE Conn Complete: interval @ +11
            interval = struct.unpack("<H", body[11:13])[0]
            row["note"] = "LE-conn-interval=%.2fms" % (interval * 1.25)
        elif sub == 0x03 and len(body) >= 5:  # LE Conn Update Complete: interval @ +3
            interval = struct.unpack("<H", body[3:5])[0]
            row["note"] = "LE-conn-update-interval=%.2fms" % (interval * 1.25)
        else:
            row["note"] = "LE-meta-unparsed"
    else:
        row["att_op_name"] = {0x0E: "Cmd_Complete", 0x0F: "Cmd_Status",
                              0x05: "Disconnect_Complete"}.get(ev, "UNKNOWN")
    row["payload_hex"] = body.hex()


def parse_btsnoop(path):
    d = open(path, "rb").read()
    if d[:8] != b"btsnoop\x00":
        raise SystemExit("not a btsnoop file (bad magic): %s" % path)
    ver, dl = struct.unpack(">II", d[8:16])
    if ver != 1 or dl not in (1001, 1002):
        raise SystemExit("unsupported btsnoop ver=%d datalink=%d" % (ver, dl))
    rows = []
    off = 16
    idx = 0
    while off + 24 <= len(d):
        olen, ilen, flags, drops, ts = struct.unpack(">IIIIQ", d[off:off + 24])
        pkt = d[off + 24:off + 24 + ilen]
        off += 24 + ilen
        if len(pkt) < ilen:
            break
        row = {"index": idx, "ts_raw_us": ts, "ts_iso": iso(ts),
               "direction": "phone_to_air" if not (flags & 1) else "air_to_phone",
               "hci": "?", "att_op": "", "att_op_name": "", "handle": "",
               "uuid": "", "payload_hex": "", "payload_ascii": "", "note": ""}
        if dl == 1002 and pkt:
            ind = pkt[0]
            body = pkt[1:]
            if ind == 0x01:
                row["hci"] = "CMD"
                row["payload_hex"] = body.hex()
            elif ind == 0x02:
                row["hci"] = "ACL"
                parse_acl(body, row)
            elif ind == 0x04:
                row["hci"] = "EVT"
                parse_evt(body, row)
            else:
                row["hci"] = "H4-0x%02X" % ind
                row["payload_hex"] = body.hex()
        else:
            row["hci"] = "H1"
            row["payload_hex"] = pkt.hex()
        rows.append(row)
        idx += 1
    return rows


def walk(o, keys):
    found = {}
    if isinstance(o, dict):
        for k, v in o.items():
            if k in keys and isinstance(v, str):
                found[k] = v
            else:
                found.update(walk(v, keys))
    elif isinstance(o, list):
        for v in o:
            found.update(walk(v, keys))
    return found


def parse_tshark_json(path):
    pkts = json.load(open(path))
    if isinstance(pkts, dict):
        pkts = [pkts]
    rows = []
    for i, p in enumerate(pkts):
        layers = p.get("layers", p)
        g = walk(layers, {"btatt.opcode", "btatt.handle", "btatt.value",
                          "frame.time_epoch", "bthci_acl.dst_bd_addr"})
        op = g.get("btatt.opcode", "")
        try:
            opv = int(op, 16)
            name = ATT_OPS.get(opv, "UNKNOWN-" + op)
        except Exception:
            opv, name = None, ""
        val = g.get("btatt.value", "").replace(":", "")
        rows.append({"index": i, "ts_raw_us": "",
                     "ts_iso": g.get("frame.time_epoch", ""),
                     "direction": "UNKNOWN-from-tshark",
                     "hci": "ACL-via-tshark",
                     "att_op": op, "att_op_name": name,
                     "handle": g.get("btatt.handle", ""),
                     "uuid": "", "payload_hex": val,
                     "payload_ascii": ascii_of(bytes.fromhex(val)) if val else "",
                     "note": "tshark-passthrough"})
    return rows


def load_gatt(path):
    m = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            h = (r.get("handle") or "").strip().lower()
            if h.startswith("0x"):
                try:
                    m["0x%04x" % int(h, 16)] = (r.get("uuid") or "").strip()
                except ValueError:
                    pass
    return m


def main():
    a = sys.argv[1:]
    if not a or "-h" in a or "--help" in a:
        print(__doc__)
        return 0
    src = a[0] if a and not a[0].startswith("--") else None
    tj = out = gatt = None
    i = 0
    while i < len(a):
        if a[i] == "--tshark-json":
            tj = a[i + 1]
            i += 2
        elif a[i] == "--out":
            out = a[i + 1]
            i += 2
        elif a[i] == "--gatt":
            gatt = a[i + 1]
            i += 2
        elif a[i] == "--quiet":
            i += 1
        else:
            i += 1
    rows = parse_tshark_json(tj) if tj else parse_btsnoop(src)
    if gatt:
        m = load_gatt(gatt)
        for r in rows:
            if r.get("handle") in m:
                r["uuid"] = m[r["handle"]]
    doc = {"source": tj or src, "packets": len(rows), "rows": rows}
    if out:
        d = os.path.dirname(out)
        if d:
            os.makedirs(d, exist_ok=True)
        json.dump(doc, open(out, "w"), indent=1)
    if "--quiet" not in a:
        n = {}
        for r in rows:
            k = (r["direction"], r["att_op_name"] or r["hci"])
            n[k] = n.get(k, 0) + 1
        print("packets=%d" % len(rows))
        for k in sorted(n):
            print("  %-14s %-18s x%d" % (k[0], k[1], n[k]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
