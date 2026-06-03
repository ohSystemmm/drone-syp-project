#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to probe for downward camera using OpenCV VideoCapture.
DJI Tello may expose the downward camera as a second USB device.
"""
import cv2
import sys
import io

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=" * 70)
print("SCANNING FOR VIDEO DEVICES")
print("=" * 70)

devices = []

# Try camera indices 0-5 (typical USB devices)
for device_id in range(6):
    print(f"\n[Testing] Device index {device_id}...", end=" ")
    try:
        cap = cv2.VideoCapture(device_id)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))

            # Try to get a frame
            ret, frame = cap.read()
            color_depth = f"{frame.shape[2]} channels" if ret and len(frame.shape) > 2 else "Grayscale" if ret else "N/A"

            print("[OK] FOUND")
            print(f"   Resolution: {w}x{h}")
            print(f"   FPS: {fps}")
            print(f"   Color: {color_depth}")
            print(f"   FOURCC: {fourcc} (0x{fourcc:08x})")
            if ret:
                print(f"   Frame shape: {frame.shape}")

            devices.append({
                'id': device_id,
                'width': w,
                'height': h,
                'fps': fps,
                'fourcc': fourcc,
                'color': color_depth,
                'works': ret
            })

            cap.release()
        else:
            print("[NO] Not available")
    except Exception as e:
        print(f"[NO] Error: {e}")

print("\n" + "=" * 70)
if devices:
    print(f"FOUND {len(devices)} DEVICE(S):")
    for dev in devices:
        status = "[OK]" if dev['works'] else "[NO]"
        print(f"  {status} Device {dev['id']}: {dev['width']}x{dev['height']} @ {dev['fps']}fps - {dev['color']}")

    print("\n" + "=" * 70)
    print("TESTING SIMULTANEOUS ACCESS (if 2+ devices available)...")
    if len(devices) >= 2:
        print("\nAttempting to open both devices simultaneously:")
        cap0 = cv2.VideoCapture(devices[0]['id'])
        cap1 = cv2.VideoCapture(devices[1]['id'])

        if cap0.isOpened() and cap1.isOpened():
            print("  [OK] Both devices opened simultaneously!")
            ret0, frame0 = cap0.read()
            ret1, frame1 = cap1.read()
            if ret0 and ret1:
                print(f"  [OK] Can read from both:")
                print(f"    Device {devices[0]['id']}: {frame0.shape}")
                print(f"    Device {devices[1]['id']}: {frame1.shape}")
            else:
                print(f"  [NO] Can open but can't read frames simultaneously")
        else:
            print("  [NO] Cannot open both devices at the same time")

        cap0.release()
        cap1.release()
else:
    print("NO VIDEO DEVICES FOUND")

print("\n" + "=" * 70)
print("CONCLUSION:")
if len(devices) == 1:
    print("  - Only ONE camera device found (front camera)")
    print("  - Downward camera may not be accessible via OpenCV")
    print("  - Check if Tello SDK has camera selection method")
elif len(devices) >= 2:
    print("  - MULTIPLE camera devices found!")
    print("  - Device 0 is likely the front RGB camera")
    print("  - Device 1 (or higher) might be the downward camera")
    print("  - Can potentially run both simultaneously")
else:
    print("  - Unable to detect any video devices")
    print("  - Drone may not be connected")
print("=" * 70)
