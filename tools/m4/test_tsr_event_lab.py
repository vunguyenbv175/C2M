#!/usr/bin/env python3
"""Offline synthetic tests for the D3 stock TSR frame/schema analyzer."""
import tempfile
import unittest
from pathlib import Path

import msgpack

from tsr_event_lab import analyze, field_shapes, markdown


def packet(topic, key, data):
    inner = {"frame_id": 2, "time": 10, "key": key, "data": data}
    outer = {"time": 10, "source": "AdasCollectService", "topic": topic,
             "data": msgpack.packb(inner, use_bin_type=True)}
    return msgpack.packb(outer, use_bin_type=True)


class D3TSREventTests(unittest.TestCase):
    def test_both_stock_named_keys(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / "frame-000.msgpack").write_bytes(
                packet("tsr", "tsr_warning", {"signal": {"id": 30, "valid": True}}))
            (path / "frame-001.msgpack").write_bytes(
                packet("tsr", "tsr_trace_res_list", [{"confidence": 0.3}]))
            report = analyze(path)
            self.assertEqual(report["stats"]["recognized_tsr_envelopes"], 2)
            self.assertEqual(report["keys"]["tsr_warning"]["data.signal.id:int"], 1)
            self.assertEqual(report["keys"]["tsr_trace_res_list"]["data[].confidence:float"], 1)
            self.assertNotIn("30", markdown(report))
            self.assertNotIn("0.3", markdown(report))

    def test_non_tsr_and_unknown_do_not_claim_recognition(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / "frame-000.msgpack").write_bytes(
                packet("vehicle", "tsr_warning", {"opaque": 1}))
            (path / "frame-001.msgpack").write_bytes(
                packet("tsr", "new_vendor_key", {"opaque": 1}))
            (path / "frame-002.msgpack").write_bytes(
                packet("tsr", "tsr_warning", {}))
            r = analyze(path)
            self.assertEqual(r["stats"]["other_topic"], 1)
            self.assertEqual(r["stats"]["unrecognized_tsr_key"], 1)
            self.assertEqual(r["stats"]["recognized_tsr_envelopes"], 1)
            self.assertFalse(r["frames"][0]["nonempty"])

    def test_malformed_fails_individual_frame(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / "frame-000.msgpack").write_bytes(b"\xc1broken")
            (path / "frame-001.msgpack").write_bytes(
                packet("tsr", "tsr_warning", {"seen": True}))
            r = analyze(path)
            self.assertEqual(r["stats"]["decode_error"], 1)
            self.assertEqual(r["stats"]["recognized_tsr_envelopes"], 1)

    def test_shapes_do_not_reveal_values(self):
        v = {"lat": 10.991, "lon": 106.888, "speed_limit": 70, "known": False}
        s = field_shapes(v)
        self.assertIn("data.lat:float", s)
        self.assertIn("data.known:bool", s)
        self.assertNotIn("10.991", str(s))
        self.assertNotIn("106.888", str(s))


if __name__ == "__main__":
    unittest.main()
