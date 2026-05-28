import sys
import time
import unittest
from unittest.mock import patch

# Set path so we can import modules
sys.path.insert(0, r"c:\Users\Quark\PycharmProjects\GOOSE\backend")

from core.autopilot import AutoPilot, PHASE_CENTER, PHASE_DESCENT, PHASE_DONE

class TestDownwardAutoPilot(unittest.TestCase):
    def setUp(self):
        self.autopilot = AutoPilot()

    def test_downward_engagement_and_flow(self):
        print("\n--- Running Downward Autopilot State Machine Test ---")
        
        # 1. Engage downward autopilot
        self.autopilot.engage_downward()
        self.assertTrue(self.autopilot.active)
        self.assertEqual(self.autopilot.phase, PHASE_CENTER)
        
        # 2. Check centering commands when ring is to the top-left (e.g. center at (100, 90))
        # Downward camera frame center is (160, 120).
        # x_err = 100 - 160 = -60. Since |x_err| > 32 (CENTER_X_TOL), it's not centered.
        # y_err = 90 - 120 = -30. Since |y_err| > 24 (CENTER_Y_TOL), it's not centered.
        now = time.monotonic()
        lr, fb, ud, yv = self.autopilot.compute(pose=None, bbox_center=(100, 90), bbox_ratio=0.1)
        
        # We expect positive lr to move right (to correct negative error)
        # We expect positive fb to move forward (to correct negative error)
        print(f"Off-center inputs: bbox=(100, 90) -> commands: lr={lr}, fb={fb}, ud={ud}, yv={yv}")
        self.assertGreater(lr, 0, "Should strafe right to center the target")
        self.assertGreater(fb, 0, "Should fly forward to center the target")
        self.assertEqual(ud, 0, "Should not adjust vertical height while centering")
        self.assertEqual(yv, 0, "Should not yaw while centering")
        self.assertEqual(self.autopilot.phase, PHASE_CENTER, "Should remain in CENTER phase")

        # 3. Simulate target being perfectly centered (160, 120)
        # x_err = 0, y_err = 0. This is within CENTER_X_TOL (32) and CENTER_Y_TOL (24).
        # The stability hold timer should start.
        print("\nSending centered target...")
        t0 = time.monotonic()
        with patch('time.monotonic', return_value=t0):
            lr, fb, ud, yv = self.autopilot.compute(pose=None, bbox_center=(160, 120), bbox_ratio=0.1)
            self.assertEqual((lr, fb, ud, yv), (0, 0, 0, 0))
            self.assertEqual(self.autopilot.phase, PHASE_CENTER, "Should stay in CENTER phase initially to verify stability")
            self.assertIsNotNone(self.autopilot._center_stable_since, "Stability timer should have started")

        # 4. Fast forward time by 0.5s (less than CENTER_HOLD_TIME = 1.0s)
        t1 = t0 + 0.5
        print(f"Advancing time by 0.5s (elapsed = 0.5s / hold time = 1.0s)...")
        with patch('time.monotonic', return_value=t1):
            lr, fb, ud, yv = self.autopilot.compute(pose=None, bbox_center=(160, 120), bbox_ratio=0.1)
            self.assertEqual(self.autopilot.phase, PHASE_CENTER, "Should still be in CENTER phase")

        # 5. Fast forward time past the 1.0s hold duration (e.g. 1.2s total)
        t2 = t0 + 1.2
        print(f"Advancing time by 1.2s (elapsed = 1.2s / hold time = 1.0s)...")
        with patch('time.monotonic', return_value=t2):
            lr, fb, ud, yv = self.autopilot.compute(pose=None, bbox_center=(160, 120), bbox_ratio=0.1)
            # The transition command should be (0, 0, 0, 0)
            self.assertEqual((lr, fb, ud, yv), (0, 0, 0, 0))
            self.assertEqual(self.autopilot.phase, PHASE_DESCENT, "Should transition to DESCENT phase")
            self.assertEqual(self.autopilot._descent_start_time, t2, "Descent timer should be initialized")

        # 6. Compute descent commands
        # Constant vertical descent command should be DESCENT_SPEED (-25)
        t3 = t2 + 1.0
        print("\nComputing descent command...")
        with patch('time.monotonic', return_value=t3):
            lr, fb, ud, yv = self.autopilot.compute(pose=None, bbox_center=(160, 120), bbox_ratio=0.1)
            print(f"Descent command: lr={lr}, fb={fb}, ud={ud}, yv={yv}")
            self.assertEqual(ud, -25, "Descent speed should be -25 (downward)")
            self.assertEqual(lr, 0)
            self.assertEqual(fb, 0)
            self.assertEqual(yv, 0)
            self.assertEqual(self.autopilot.phase, PHASE_DESCENT)

        # 7. Check transition to DONE after DESCENT_DURATION (4.0s)
        t4 = t2 + 4.1
        print("Advancing time past DESCENT_DURATION (4.0s)...")
        with patch('time.monotonic', return_value=t4):
            lr, fb, ud, yv = self.autopilot.compute(pose=None, bbox_center=None, bbox_ratio=0.0)
            self.assertEqual((lr, fb, ud, yv), (0, 0, 0, 0))
            self.assertEqual(self.autopilot.phase, PHASE_DONE, "Should transition to DONE phase")

        print("SUCCESS: Downward Autopilot State Machine passed all checks!")

if __name__ == "__main__":
    unittest.main()
