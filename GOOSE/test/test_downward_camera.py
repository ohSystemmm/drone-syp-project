#!/usr/bin/env python3
"""
Test script to explore Tello downward camera capabilities.
"""
import time
import inspect
from djitellopy import Tello

print("=" * 60)
print("EXPLORING TELLO CAMERA CAPABILITIES")
print("=" * 60)

# Create Tello instance (don't connect yet)
tello = Tello()

# List all methods that might relate to camera/video
print("\n[1] Methods containing 'camera', 'video', 'stream', 'frame':")
all_methods = [method for method in dir(tello) if not method.startswith('_')]
camera_methods = [m for m in all_methods if any(x in m.lower() for x in ['camera', 'video', 'stream', 'frame', 'resolution', 'fps'])]
for method in sorted(camera_methods):
    print(f"  - {method}")

# Check for any attributes related to camera
print("\n[2] All public attributes/methods (first 50):")
for i, method in enumerate(sorted(all_methods)[:50]):
    print(f"  {i+1}. {method}")

# Try to find camera mode or switch methods
print("\n[3] Looking for camera mode/switch methods:")
for method in all_methods:
    if any(x in method.lower() for x in ['mode', 'switch', 'camera', 'ir', 'thermal']):
        print(f"  - {method}")

# Try to connect and check streaming options
print("\n[4] Attempting to connect and check live options...")
try:
    print("  Connecting to Tello...")
    tello.connect()
    print(f"  ✓ Connected! Battery: {tello.get_battery()}%")

    # Check if there's a way to get both cameras
    print("\n[5] Checking get_frame_read():")
    frame_reader = tello.get_frame_read()
    print(f"  Frame reader type: {type(frame_reader)}")
    print(f"  Frame reader methods: {[m for m in dir(frame_reader) if not m.startswith('_')]}")

    # Try to get a frame
    time.sleep(1)
    frame = frame_reader.frame
    if frame is not None:
        print(f"  ✓ Got frame! Shape: {frame.shape}")
    else:
        print(f"  ✗ Frame is None")

    # Check for SDK version or firmware that might support dual camera
    print("\n[6] Tello properties:")
    print(f"  - get_sdk_version(): {tello.get_sdk_version()}")
    try:
        print(f"  - get_hardware(): {tello.get_hardware()}")
    except:
        print(f"  - get_hardware(): Not available")

    tello.end()
    print("\n[7] ✓ Tello disconnected")

except Exception as e:
    print(f"  ✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("If Tello has dual cameras, check:")
print("  1. If there's a set_camera() or camera_select() method")
print("  2. If we can open a second frame reader")
print("  3. If USB cameras show up as cv2.VideoCapture() devices")
print("=" * 60)
