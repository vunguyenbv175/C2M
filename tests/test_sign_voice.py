#!/usr/bin/env python3
"""Source gates + host synthetic test for the D4 C2M sign voice bridge.

The production bridge reads a fixed /tmp status and writes cardv's FIFO. This
test never touches a camera, cardv, a real FIFO, audio, or stock files. On
Linux it copies the script to a temp directory, substitutes temp paths and a
regular-file FIFO fixture, and verifies one play per new event_id, no replay
on the D4 hold, the end-area WAV, and no playback while inactive.

The private WAV bytes are not part of this test; tiny regular-file markers are
used only to prove path selection.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "fw" / "voice" / "sign_voice.sh"
D4_BOOT = ROOT / "fw" / "d4" / "d4_boot.sh"


class SignVoiceSourceTests(unittest.TestCase):
    def test_source_boundaries(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for token in (
            'audioplay 0 dev0',
            '/tmp/c2m_d4_status',
            'if [ "$_state" = ready ]',
            '[ "$_gps" = 1 ]',
            '[ "$_active" = 1 ]',
            '[ "$_eid" -gt 0 ]',
            '_field event_id',
            'residential_start',
            'residential_end',
            'Sign_Residential_Start.wav',
            'Sign_Residential_End.wav',
            'c2m-sign-voice.lock',
            'timeout -t',
            'sleep "$_interval"',
        ):
            self.assertIn(token, text, f"missing sign-voice source pin: {token}")
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("nc ", text)

    def test_d4_boot_launches_bridge_after_producer(self) -> None:
        text = D4_BOOT.read_text(encoding="utf-8")
        self.assertIn("/customer/c2m/c2m-signs --serve", text)
        self.assertIn("/customer/c2m/sign_voice.sh", text)
        self.assertLess(text.index("/customer/c2m/c2m-signs --serve"),
                        text.index("/customer/c2m/sign_voice.sh"))


@unittest.skipUnless(sys.platform.startswith("linux"), "host bridge test uses Linux sh/stat")
class SignVoiceHostTests(unittest.TestCase):
    def _wait(self, predicate, timeout: float = 4.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.1)
        return False

    def test_event_once_and_end_event(self) -> None:
        sh = shutil.which("sh")
        self.assertIsNotNone(sh)
        with tempfile.TemporaryDirectory(prefix="c2m-sign-voice-") as td_raw:
            td = Path(td_raw)
            voice = td / "voice"
            voice.mkdir()
            (voice / "Sign_Residential_Start.wav").write_bytes(b"start")
            (voice / "Sign_Residential_End.wav").write_bytes(b"end")
            fifo = td / "fifo"
            fifo.write_bytes(b"")
            status = td / "status"
            voice_status = td / "voice-status"
            voice_log = td / "voice-log"
            lock = td / "lock"
            text = SCRIPT.read_text(encoding="utf-8")
            replacements = {
                "_dir=/customer/c2m": f"_dir={voice.as_posix()}",
                "_fifo=/tmp/cardv_fifo": f"_fifo={fifo.as_posix()}",
                "_status=/tmp/c2m_d4_status": f"_status={status.as_posix()}",
                "_voice_status=/tmp/c2m_sign_voice_status": f"_voice_status={voice_status.as_posix()}",
                "_voice_log=/tmp/c2m_sign_voice.log": f"_voice_log={voice_log.as_posix()}",
                "_lock=/tmp/c2m-sign-voice.lock": f"_lock={lock.as_posix()}",
                '[ -p "$_fifo" ]': '[ -f "$_fifo" ]',
            }
            for old, new in replacements.items():
                self.assertIn(old, text)
                text = text.replace(old, new)
            script = td / "sign_voice.sh"
            script.write_text(text, encoding="utf-8")
            proc = subprocess.Popen([sh, str(script)], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            try:
                status.write_text(
                    "version=1\nsource=gps_offline\nstate=ready\ngps_fresh=1\n"
                    "active=1\nsequence=1\ncode=residential_start\n"
                    "speed_kmh=0\ndistance_m=180\nevent_id=42\n"
                    "monotonic_ms=1000\n", encoding="utf-8")
                self.assertTrue(self._wait(lambda: voice_log.is_file() and
                                           "event=42 code=residential_start advisory=played"
                                           in voice_log.read_text(encoding="utf-8")),
                                voice_log.read_text(encoding="utf-8") if voice_log.exists() else "")
                self.assertIn("Sign_Residential_Start.wav",
                              fifo.read_text(encoding="utf-8"))
                self.assertEqual(voice_log.read_text(encoding="utf-8").count(
                    "event=42 code=residential_start advisory=played"), 1)
                # D4's 5 s hold must not replay the same event_id.
                time.sleep(1.6)
                self.assertEqual(voice_log.read_text(encoding="utf-8").count(
                    "event=42 code=residential_start advisory=played"), 1)
                status.write_text(
                    "version=1\nsource=gps_offline\nstate=ready\ngps_fresh=1\n"
                    "active=1\nsequence=2\ncode=residential_end\n"
                    "speed_kmh=0\ndistance_m=150\nevent_id=43\n"
                    "monotonic_ms=2000\n", encoding="utf-8")
                self.assertTrue(self._wait(lambda:
                    "event=43 code=residential_end advisory=played"
                    in voice_log.read_text(encoding="utf-8")),
                    voice_log.read_text(encoding="utf-8"))
                self.assertIn("Sign_Residential_End.wav",
                              fifo.read_text(encoding="utf-8"))
                # Inactive/stopped status must not latch or repeat.
                status.write_text(
                    "version=1\nsource=gps_offline\nstate=ready\ngps_fresh=1\n"
                    "active=0\nsequence=3\ncode=none\nspeed_kmh=0\n"
                    "distance_m=0\nevent_id=0\nmonotonic_ms=3000\n",
                    encoding="utf-8")
                time.sleep(1.6)
                self.assertEqual(voice_log.read_text(encoding="utf-8").count(
                    "advisory=played"), 2)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
