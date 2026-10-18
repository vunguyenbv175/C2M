#!/usr/bin/env python3
"""Synthetic model of selected statically traced VI ADAS speed branches.

No device, network, private fixture, speed injection or vendor code execution.
This is NOT a full ADAS emulator or evidence of the live input/activation state.
Evidence: docs/runtime/D5_VI_GPS_ADAS_PATH_20261018.md.
"""
import math
import struct
import unittest


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def received_speed(value):
    # VehicleInfoRecv::recv: float subtraction/abs, double comparison to 0.1.
    speed = f32(value)
    delta = abs(f32(speed - f32(65535.0)))
    return f32(0.0) if delta < 0.1 else speed


def frame_speed_mps(speed_kmh):
    # RingbufReader::GetFrame converts the received float km/h via double /3.6.
    return f32(f32(speed_kmh) / 3.6)


def hmw_line_mps(threshold_kmh):
    # HeadwayWarning constructor converts the environment threshold via /3.6.
    return f32(threshold_kmh / 3.6)


def hmw_below_speed_line(speed, threshold):
    # Only the first conditional return in HeadwayWarning::OnStateOff.
    # False does NOT mean a warning will fire: other gates are not modeled.
    return f32(speed) < f32(threshold)


def fcw_speed_fit(speed, low, high):
    # FcwState::IsSpeedFitFcw, finite synthetic inputs only.
    if not all(math.isfinite(x) for x in (speed, low, high)):
        raise ValueError('model is restricted to finite synthetic values')
    speed, low, high = map(f32, (speed, low, high))
    if speed <= -99.999:
        return True
    return low <= speed <= high


class SpeedBranchModelTests(unittest.TestCase):
    def test_invalid_sender_sentinel_maps_to_zero(self):
        self.assertEqual(received_speed(65535), 0)

    def test_sentinel_epsilon_is_strict(self):
        self.assertEqual(received_speed(65535.05), 0)
        self.assertEqual(received_speed(65535.2), f32(65535.2))

    def test_normal_speeds_not_scaled_in_receiver_branch(self):
        for speed in [0, 10, 29, 30, 60, 100]:
            self.assertEqual(received_speed(speed), f32(speed))

    def test_invalid_sentinel_blocks_hmw_at_30(self):
        self.assertTrue(hmw_below_speed_line(received_speed(65535), 30))

    def test_hmw_speed_boundary_only(self):
        self.assertTrue(hmw_below_speed_line(29.9, 30))
        self.assertFalse(hmw_below_speed_line(30, 30))
        self.assertFalse(hmw_below_speed_line(31, 30))

    def test_hmw_input_and_threshold_share_mps_conversion(self):
        line = hmw_line_mps(30)
        self.assertTrue(hmw_below_speed_line(frame_speed_mps(29), line))
        self.assertFalse(hmw_below_speed_line(frame_speed_mps(30), line))
        self.assertFalse(hmw_below_speed_line(frame_speed_mps(31), line))
        self.assertTrue(hmw_below_speed_line(frame_speed_mps(received_speed(65535)), line))

    def test_fcw_configured_range_is_independent_of_hmw(self):
        # Synthetic limits, NOT recovered actual FCW limits.
        self.assertFalse(fcw_speed_fit(0, 20, 120))
        self.assertTrue(fcw_speed_fit(20, 20, 120))
        self.assertTrue(fcw_speed_fit(120, 20, 120))
        self.assertFalse(fcw_speed_fit(121, 20, 120))

    def test_negative_unknown_speed_branch_is_not_zero_branch(self):
        self.assertTrue(fcw_speed_fit(-360, 20, 120))
        self.assertFalse(fcw_speed_fit(0, 20, 120))

    def test_nonfinite_fcw_model_rejected(self):
        with self.assertRaises(ValueError):
            fcw_speed_fit(float('nan'), 20, 120)


if __name__ == '__main__':
    unittest.main(verbosity=2)
