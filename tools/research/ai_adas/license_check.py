"""License gate: flag non-commercial / copyleft entries from models.json.

Usage: python3 license_check.py <models.json>
Heuristic only — NOT legal advice. Always get counsel review before product.
Flags: NON-COMMERCIAL datasets (CC-BY-NC*, research-only, gated), copyleft weights
(AGPL-3.0, GPL-*) that trigger source/weight duties in closed dashcam unless licensed.
"""
import json, sys

NC_HINTS = ("NON-COMMERCIAL", "RESEARCH-ONLY", "RESEARCH ONLY", "CC-BY-NC", "CC BY-NC",
            "ACADEMIC", "GATED", "NONCOMMERCIAL")
COPYLEFT = ("AGPL", "GPL-2", "GPL-3", "GPL2", "GPL3")

def main():
    rows = json.loads(open(sys.argv[1], encoding="utf-8").read())
    for r in rows:
        lic = str(r.get("license", "UNKNOWN"))
        flags = []
        if any(h in lic.upper() for h in NC_HINTS):
            flags.append("NON-COMMERCIAL-DATA/WEIGHTS: need own collection or commercial agreement")
        if any(h in lic.upper() for h in COPYLEFT):
            flags.append("COPYLEFT: closed-product trigger — prefer Apache-2.0/MIT or buy Enterprise/commercial")
        if lic.strip().upper() == "UNKNOWN":
            flags.append("UNKNOWN license: do not ship before confirming")
        if flags:
            print(f"- {r.get('model')}: {lic} :: {' | '.join(flags)}")
    print("done (heuristic, not legal advice)")

if __name__ == "__main__":
    main()
