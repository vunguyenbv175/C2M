#!/usr/bin/env python3
"""Parity test: C++ m4_policy.hpp vs canonical tools/m4/m4_policy.json (review F2).

Asserts every known UUID/key gets the same verdict on both sides, and that
GPSSpeed/GPSLevel are DENY at L2 (the Sprint-1 contradiction, now fixed).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
policy = json.loads((ROOT / "m4_policy.json").read_text())
header = (ROOT / "../../include/c2m/display/m4_policy.hpp").read_text()

# every ALLOW uuid must appear in the C++ AllowL2 branch
for uuid in policy["allow_l2_json_uuids"]:
    assert f'"{uuid}"' in header, f"C++ policy missing ALLOW uuid {uuid}"

# every DENY uuid/key must NOT be in an AllowL2 position: check the ClassifyJsonUuid
# function body only lists allow-uuids; deny names must not appear as =="..." there
fn = header.split("ClassifyJsonUuid")[1].split("ClassifyInnerKey")[0]
for uuid in policy["deny_json_uuids"]:
    assert f'"{uuid}"' not in fn, f"C++ policy wrongly allows {uuid}"
# behavioral parity with replay_guard
from replay_guard import classify_json_uuid, classify_inner_key


def classify(key):
    return classify_inner_key(key)


for key in policy["deny_inner_keys"]:
    assert classify(key) == "DENY", key


for uuid in policy["allow_l2_json_uuids"]:
    assert classify_json_uuid(uuid) == "ALLOW-L2", uuid
for uuid in policy["deny_json_uuids"]:
    assert classify_json_uuid(uuid) == "DENY", uuid
assert classify_json_uuid("GPSSpeed") == "DENY", "F2 regression: GPSSpeed must be DENY at L2"
assert classify_json_uuid("GPSLevel") == "DENY", "F2 regression: GPSLevel must be DENY at L2"
assert classify_json_uuid("NopeUnknown") == "DENY", "default-deny broken"
print("m4_policy parity: OK")
