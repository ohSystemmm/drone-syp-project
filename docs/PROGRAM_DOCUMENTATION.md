# GOOSE Program Documentation

This document provides a full-system view of the GOOSE project: architecture, runtime flow, controls, data pipeline, and operations.

## 1. What GOOSE Does

GOOSE is a real-time drone control system for DJI Tello that combines:

- live object detection (YOLO)
- geometric pose estimation (ring/ellipse)
- autonomous control (finite-state autopilot)
- manual override and joystick input
- dataset collection for iterative model improvement

## 2. Main Entry Points

### Primary Runtime

- GOOSE/main.py
  - Starts the full app loop (drone, vision, control, UI).
  - Accepts runtime flags:
    - --model: onnx, pt, auto
    - --ip: drone IP (default 192.168.10.1)
    - --port: drone UDP command port (default 8889)

### Utility Scripts

- GOOSE/upload_model.py
  - Uploads trained model artifacts to Roboflow.
- GOOSE/upload_uncertain_data.py
  - Uploads uncertain samples for relabeling.
- GOOSE/fix_recordings.py
  - Repairs color channel issues in recordings.

## 3. High-Level Architecture

### Control and Runtime Core

- GOOSE/core/drone.py
  - Drone connectivity, stream handling, RC command interface.
- GOOSE/core/autopilot.py
  - Autonomous flight behavior and control outputs.
- GOOSE/core/control_center.py
  - Runtime HUD and operator-facing status.
- GOOSE/core/joystick.py
  - Joystick input abstraction.
- GOOSE/core/joystick_calibration.py
  - Joystick calibration workflow and mapping.
- GOOSE/core/calibration.py
  - Ground-truth driven calibration mode (depth scaling).
- GOOSE/core/data_factory.py
  - Captures frames plus metadata for training sets.

### Vision and Perception

- GOOSE/vision/detector.py
  - YOLO inference wrapper for .pt and .onnx models.
- GOOSE/vision/position_estimator.py
  - 3D pose estimation and temporal smoothing.
- GOOSE/vision/edge_pose.py
  - Circle/ellipse geometry solver.
- GOOSE/vision/aruco_calibrator.py
  - ArUco marker support and calibration helpers.
- GOOSE/vision/sampler.py
  - Confidence-based sampling for data curation.
- GOOSE/vision/room_3d_view.py
  - Optional 3D visualization utilities.

## 4. Runtime Flow

At startup, the program initializes drone communication, loads the model, creates vision and control subsystems, and enters a real-time loop.

1. Initialization
- parse CLI args
- connect to Tello and start video stream
- load detector backend (auto, onnx, or pt)
- initialize autopilot, calibration, joystick, and data components

2. Per-frame processing
- acquire latest frame
- run detector for candidate targets
- estimate pose for each candidate using geometric pipeline
- select best target with stability/confidence heuristics
- update autopilot or manual control output
- send RC command
- draw overlays and status

3. Optional side workflows
- calibration mode updates depth scale
- data capture saves training context and metadata
- uncertain-frame sampling stores hard cases for relabeling

4. Shutdown
- stop worker threads/streams
- close writers and windows
- disconnect from drone safely

## 5. Autopilot Behavior

Autopilot is a staged controller with phase transitions based on pose quality and alignment thresholds.

- ALIGN phase
  - centers target and adjusts orientation.
- APPROACH phase
  - closes distance while maintaining alignment.
- PUNCH phase
  - executes final, fast forward pass.

Operator control remains available so manual override is always possible.

## 6. Pose Estimation Pipeline

The pose estimator receives frame plus ROI and produces a smoothed pose struct.

1. Expand ROI for contour robustness.
2. Extract contour from distorted image domain.
3. Undistort contour points using camera intrinsics.
4. Fit ellipse to corrected points.
5. Solve 3D pose analytically from ellipse geometry.
6. Apply Kalman filtering and outlier rejection.
7. Return stable x/y/z and confidence values.

Coasting is used briefly when detections drop out, then state resets after sustained misses.

## 7. Inputs and Operator Controls

Input sources:

- keyboard bindings
- joystick/controller bindings
- UI toggles for operation modes

Configuration files:

- GOOSE/flight_data/keybindings.json
- GOOSE/flight_data/joystick_config.json

Typical actions include takeoff, land, emergency stop, autopilot toggle, calibration toggle, and data collection toggle.

## 8. Data and Storage Layout

### Models and Assets

- GOOSE/assets/models
- GOOSE/assets/aruco

### Runtime Output

- GOOSE/logs
- GOOSE/recordings

### Training and Curation Data

- GOOSE/flight_data/context
- GOOSE/flight_data/uncertain
- flight_data/training_set

The top-level flight_data directory stores historical training sessions and associated metadata.

## 9. External Dependencies

Core stack includes:

- Python runtime and scientific stack (numpy)
- OpenCV for vision and geometry
- Ultralytics YOLO and ONNX Runtime for inference
- Pygame for loop/input/UI layers
- djitellopy for Tello communication
- Roboflow integration utilities for data/model workflows

Dependency versions are defined in requirements.txt.

## 10. Configuration and Environment

- requirements.txt
  - canonical package list for setup.
- .env (local, not committed)
  - expected for API credentials and external service identifiers.

Recommended operational checks:

- verify model file exists in GOOSE/assets/models
- verify drone IP/port values
- verify joystick mappings when using controller input
- verify writable directories for logs and recordings

## 11. Typical Operation Checklist

1. Install dependencies from requirements.txt.
2. Ensure drone and host are on same network.
3. Confirm model artifacts are present.
4. Launch app with chosen model backend.
5. Verify live video, detections, and control response.
6. Toggle autopilot only after stable pose/confidence.
7. Record and curate uncertain samples for retraining.

## 12. Related Documentation

Project docs in conductor:

- conductor/product.md
- conductor/tech-stack.md
- conductor/workflow.md
- conductor/code_styleguides/general.md
- conductor/code_styleguides/python.md

Module-level estimator reference:

- GOOSE/vision/position_estimator.md
