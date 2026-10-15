#!/usr/bin/env python3
"""Offline guard tests: never connect to cardv without disconnected-M4 consent."""
import io
import unittest
from unittest.mock import patch

import cardv_status_client as client


class ObserverGuardTests(unittest.TestCase):
    def test_default_invocation_is_rejected_before_connection(self):
        with patch('sys.argv', ['cardv_status_client.py', 'fixture.invalid']), \
             patch.object(client.websocket, 'create_connection') as connect, \
             patch('sys.stderr', new_callable=io.StringIO) as stderr:
            with self.assertRaises(SystemExit) as result:
                client.main()
            self.assertEqual(result.exception.code, 2)
            self.assertIn('--confirm-m4-disconnected', stderr.getvalue())
            connect.assert_not_called()

    def test_help_explains_interference_without_connection(self):
        with patch('sys.argv', ['cardv_status_client.py', '--help']), \
             patch.object(client.websocket, 'create_connection') as connect, \
             patch('sys.stdout', new_callable=io.StringIO) as stdout:
            with self.assertRaises(SystemExit) as result:
                client.main()
            self.assertEqual(result.exception.code, 0)
            self.assertIn('steal', stdout.getvalue())
            connect.assert_not_called()

    def test_explicit_disconnected_fixture_only_receives_and_closes(self):
        class FakeSocket:
            def __init__(self):
                self.frames = iter(['{"type":1601,"uuid":"GPSSpeed","speed":0}', None])
                self.closed = False

            def recv(self):
                return next(self.frames)

            def close(self):
                self.closed = True

        fake = FakeSocket()
        with patch('sys.argv', ['cardv_status_client.py', '--confirm-m4-disconnected',
                                'fixture.invalid']), \
             patch.object(client.websocket, 'create_connection', return_value=fake) as connect, \
             patch('sys.stdout', new_callable=io.StringIO) as stdout:
            client.main()
            connect.assert_called_once_with('ws://fixture.invalid:8080/', timeout=10.0,
                                            subprotocols=['minieye-websocket'])
            self.assertIn('GPSSpeed', stdout.getvalue())
            self.assertTrue(fake.closed)


if __name__ == '__main__':
    unittest.main()
