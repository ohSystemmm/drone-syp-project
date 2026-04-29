# Position Estimator Module

This document describes how `PositionEstimator` converts a detected ROI into a stable 3D pose estimate for ring alignment and control.

## Purpose

The estimator in `vision/position_estimator.py` does three core jobs:

1. Build camera intrinsics for the active frame size.
2. Estimate ring pose from contour geometry in the ROI.
3. Smooth output using a Kalman filter with coast mode for short detection dropouts.

## High-Level Pipeline

`estimate(frame_bgr, roi_box)` follows this sequence:

1. Validate ROI. If ROI is missing, return a coasted Kalman prediction.
2. Expand ROI by 20 percent on each side to improve contour capture robustness.
3. Run edge-based pose extraction in ROI coordinates.
4. Shift contour points back into full-frame coordinates.
5. Undistort only contour points using camera matrix and distortion coefficients.
6. Fit an ellipse on undistorted points.
7. Solve analytical pose from the ellipse under the pinhole camera model.
8. Apply optional Z scaling (`Z_SCALE`).
9. Update Kalman filter for smoothed `x_cm`, `y_cm`, `z_cm`.
10. Return a `PoseEstimate` dataclass instance.

## Core Data Types

### PoseEstimate

`PoseEstimate` is the output contract used by downstream control and visualization:

- `x_cm`, `y_cm`, `z_cm`: Smoothed position in centimeters.
- `angle_deg`: Magnitude of tilt from `tilt_x` and `tilt_y`.
- `confidence`: Pose confidence from the geometric solver.
- `tilt_x_deg`, `tilt_y_deg`: Component tilt angles.
- `normal`: Estimated ring normal vector.
- `is_coasted`: True when output comes from prediction only.
- `is_partial`: Reserved flag for partial detections.
- `ellipse`: Fitted ellipse tuple from OpenCV.
- `best_contour`: Best contour in full-frame coordinates.
- `target_px`: Pixel center used for UI overlay.

### PoseKalmanFilter

State model: constant velocity with 6-state vector and 3D position measurements.

- State: `[x, y, z, vx, vy, vz]`
- Measurement: `[x, y, z]`
- Dynamic dt: computed from `time.monotonic()` and clamped to `[0.001, 0.1]`
- Innovation gate: rejects updates when measurement jump exceeds 60 cm on any axis
- Coast window: up to `MAX_COAST_FRAMES` (45) prediction-only frames before reset

## Calibration and Geometry Constants

The module defines camera and target constants near class level:

- Ring outer diameter: `50.0 cm`
- Effective ring radius: `25.0 cm`
- Calibrated intrinsics for base resolution: `fx=fy=921`, `cx=480`, `cy=360`
- Distortion coefficients: `[-0.044, 0.124, 0.0, 0.0, -0.158]`

Intrinsics are scaled at runtime from the active frame size relative to 960x720.

## Performance Notes

This implementation avoids full-frame remapping and undistorts only contour points. That keeps CPU load low while preserving geometric accuracy where it matters.

## Coasted Output Behavior

When detection fails for a short period:

- `estimate` returns `_coast_kalman()` output.
- `confidence` is fixed at `0.3` for coasted values.
- `is_coasted` is set to `True`.
- After prolonged misses, filter state resets and estimator returns `None` until a valid measurement reinitializes tracking.

## Drawing and Debug Overlay

`draw_estimate(frame, est)` renders:

- Contour and ellipse when available
- Crosshair marker at `target_px`
- HUD text for X, Y, Z, and confidence

Color coding:

- Active estimate: cyan-like `(255, 255, 0)`
- Coasted estimate: gray `(100, 100, 100)`

## Tuning Guide

Adjust these values based on flight behavior:

- `process_noise` in `PoseKalmanFilter`: increase for faster responsiveness, decrease for smoother output.
- `measurement_noise`: increase if detector is jittery, decrease if detector is stable.
- Innovation threshold (`60 cm`): lower for stricter outlier rejection, higher for aggressive maneuvers.
- `MAX_COAST_FRAMES`: lower to fail fast, higher to ride through temporary occlusion.
- `Z_SCALE`: apply only if empirical depth bias is observed.

## Common Failure Modes

- `fitEllipse` throws: contour may be too sparse or degenerate.
- Frequent coast mode: ROI input or contour extraction quality is likely unstable.
- Large Z bias: verify camera calibration, ring diameter assumption, and `Z_SCALE`.

## Minimal Usage Example

```python
from vision.position_estimator import PositionEstimator

estimator = PositionEstimator(frame_width=960, frame_height=720)

# roi_box format: (x1, y1, x2, y2)
est = estimator.estimate(frame_bgr, roi_box)
if est is not None:
    frame_bgr = estimator.draw_estimate(frame_bgr, est)
```

## Related Module

This module depends on `vision/edge_pose.py` (`EdgePoseSolver`) for contour-based geometric pose extraction and analytical solving.
