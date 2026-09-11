#!/usr/bin/env python3
"""Helpers for the C2M stock ADAS libflow / MessagePack screen protocol.

Static reverse evidence:
- libflow outer WebSocket binary frame: {time, source, topic, data}
- subscription frame: {source, topic:'subscribe', data:<topic>}
- ScreenService inner payload: {frame_id, time, key, data}

This module deliberately does not assume units/enums that have not been captured.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import msgpack

KNOWN_TOPICS={"vehicle","ped","lane"}
KNOWN_KEYS={"vehicleWarning","vehicleMeasure","pedestrians","laneWarningRes"}

SCHEMAS={
 "vehicleWarning":{"vehicle_id","headway","warning_level","fcw","headway_warning","vb_warning","sag_warning"},
 "vehicleMeasure":{"vehicle_class","vehicle_id","vehicle_width","longitude_dist","lateral_dist","ttc","is_crucial","is_second_crucial"},
 "pedestrians":{"id","world_x","world_y","is_key","is_danger","ttc_m","ttc","have_bike"},
 "laneWarningRes":{"lanelines","ldw_info","turn_radius","turn_frequently"},
}

@dataclass
class DecodeResult:
    outer: dict[str,Any]
    inner: Any
    warnings: list[str]


def pack_subscription(source:str, topic:str, action:str="subscribe") -> bytes:
    if action not in {"subscribe","unsubscribe"}:
        raise ValueError("action must be subscribe or unsubscribe")
    return msgpack.packb({"source":source,"topic":action,"data":topic},use_bin_type=True)


def _unpack_one(data:bytes) -> Any:
    return msgpack.unpackb(data,raw=False,strict_map_key=False)


def decode_ws_binary(payload:bytes) -> DecodeResult:
    outer=_unpack_one(payload)
    warnings=[]
    if not isinstance(outer,dict):
        return DecodeResult({},outer,["outer frame is not a map"])
    for k in ("time","source","topic","data"):
        if k not in outer:warnings.append(f"outer missing key: {k}")
    inner=None
    raw=outer.get("data")
    if isinstance(raw,(bytes,bytearray,memoryview)):
        try:inner=_unpack_one(bytes(raw))
        except Exception as e:warnings.append(f"inner MessagePack decode failed: {e}")
    elif raw is not None:
        inner=raw
    if isinstance(inner,dict):
        for k in ("frame_id","time","key","data"):
            if k not in inner:warnings.append(f"inner missing key: {k}")
        key=inner.get("key")
        if key in SCHEMAS:
            body=inner.get("data")
            expected=SCHEMAS[key]
            if key in {"vehicleMeasure","pedestrians"}:
                if isinstance(body,list):
                    for i,item in enumerate(body[:50]):
                        if isinstance(item,dict):
                            missing=expected-set(item)
                            extra=set(item)-expected
                            if missing:warnings.append(f"{key}[{i}] missing: {sorted(missing)}")
                            if extra:warnings.append(f"{key}[{i}] extra: {sorted(extra)}")
                else:warnings.append(f"{key} data is not an array")
            elif isinstance(body,dict):
                missing=expected-set(body); extra=set(body)-expected
                if missing:warnings.append(f"{key} missing: {sorted(missing)}")
                if extra:warnings.append(f"{key} extra: {sorted(extra)}")
        elif key is not None:
            warnings.append(f"unknown inner key: {key}")
    return DecodeResult(outer,inner,warnings)
