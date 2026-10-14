#!/usr/bin/env python3
"""Offline mocks prove identity-first TSR subscription; no network/device use."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import msgpack
import websocket
import capture_tsr_readonly as capture

ROOT = Path(__file__).resolve().parents[2]


class FakeSocket:
    def __init__(self, payload):
        self.payload = payload
        self.sent = []
        self.closed = False

    def send(self, data, opcode):
        self.sent.append((msgpack.unpackb(data, raw=False), opcode))

    def settimeout(self, seconds):
        assert seconds > 0

    def recv_data(self, control_frame):
        assert control_frame
        if self.payload is not None:
            data, self.payload = self.payload, None
            return websocket.ABNF.OPCODE_BINARY, data
        return websocket.ABNF.OPCODE_CLOSE, b''

    def close(self):
        self.closed = True


class CaptureTests(unittest.TestCase):
    def arguments(self, out):
        return ['capture_tsr_readonly.py', '--expected-uuid', 'private-test-identity',
                '--stationary-authorized', '--out', str(out), '--seconds', '1']

    def test_no_ws_or_evidence_before_identity(self):
        (ROOT / 'build').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as td:
            out = Path(td) / 'evidence'
            with patch('sys.argv', self.arguments(out)), \
                 patch.object(capture, 'check_identity', side_effect=ValueError('private-response')), \
                 patch.object(capture.websocket, 'create_connection') as connect, \
                 patch('sys.stdout', new_callable=io.StringIO) as stdout:
                self.assertEqual(capture.main(), 1)
                connect.assert_not_called()
                self.assertFalse(out.exists())
                self.assertNotIn('private-response', stdout.getvalue())
                self.assertNotIn('private-test-identity', stdout.getvalue())

    def test_only_stock_tsr_subscription(self):
        inner = {'frame_id': 1, 'time': 2, 'key': 'tsr_warning', 'data': {'opaque': True}}
        payload = msgpack.packb({'time': 2, 'source': 'AdasCollectService', 'topic': 'tsr',
                                'data': msgpack.packb(inner, use_bin_type=True)}, use_bin_type=True)
        fake = FakeSocket(payload)
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as td:
            out = Path(td) / 'evidence'
            with patch('sys.argv', self.arguments(out)), \
                 patch.object(capture, 'check_identity', return_value={'identity_verified': True}), \
                 patch.object(capture.websocket, 'create_connection', return_value=fake), \
                 patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(capture.main(), 0)
            self.assertEqual(fake.sent, [({'source': 'c2m-tsr-readonly', 'topic': 'subscribe', 'data': 'tsr'},
                                         websocket.ABNF.OPCODE_BINARY)])
            self.assertTrue(fake.closed)
            report = json.loads((out / 'report.json').read_text())
            self.assertEqual(report['verdict'], 'CAPTURED_UNVERIFIED')
            self.assertFalse(report['device_settings_writes'])
            self.assertFalse(report['warning_injection'])
            self.assertFalse(report['runtime_schema_verified'])
            self.assertEqual(report['frames'][0]['inner_key'], 'tsr_warning')
            self.assertEqual((out / 'frame-000.msgpack').read_bytes(), payload)

    def test_no_frames_does_not_mean_detection_failed(self):
        fake = FakeSocket(None)
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as td:
            out = Path(td) / 'evidence'
            with patch('sys.argv', self.arguments(out)), \
                 patch.object(capture, 'check_identity', return_value={'identity_verified': True}), \
                 patch.object(capture.websocket, 'create_connection', return_value=fake), \
                 patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(capture.main(), 0)
            self.assertEqual(json.loads((out / 'report.json').read_text())['verdict'],
                             'NO_FRAMES_NOT_DETECTION_FAILURE')

    def test_requires_authorization(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as td:
            out = Path(td) / 'evidence'
            arguments = self.arguments(out)
            arguments.remove('--stationary-authorized')
            with patch('sys.argv', arguments), patch.object(capture, 'check_identity') as identity, \
                 patch('sys.stderr', new_callable=io.StringIO):
                with self.assertRaises(SystemExit):
                    capture.main()
                identity.assert_not_called()
                self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
