"""
Generate printable ArUco markers for ring calibration.

Generates 4 markers (IDs 0-3) from DICT_4X4_50 at 36mm size.
Saves individual PNGs and a combined sheet for easy printing.

Usage:
    python generate_aruco.py

Output:
    GOOSE/assets/aruco/marker_0.png  (through marker_3.png)
    GOOSE/assets/aruco/aruco_sheet.png  (all 4 on one page)
"""

import cv2
import numpy as np
import os


MARKER_IDS = [0, 1, 2, 3]
DICT_TYPE = cv2.aruco.DICT_4X4_50
MARKER_SIZE_PX = 180   # pixels per marker (36mm at ~127 DPI)
BORDER_BITS = 1

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "aruco")


def generate_markers():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    dictionary = cv2.aruco.getPredefinedDictionary(DICT_TYPE)

    markers = []
    labels = ["TOP (ID:0)", "RIGHT (ID:1)", "BOTTOM (ID:2)", "LEFT (ID:3)"]

    for marker_id in MARKER_IDS:
        img = cv2.aruco.generateImageMarker(dictionary, marker_id, MARKER_SIZE_PX)

        # Add white border for cutting guide
        bordered = cv2.copyMakeBorder(img, 20, 20, 20, 20,
                                      cv2.BORDER_CONSTANT, value=255)

        # Save individual marker
        path = os.path.join(OUTPUT_DIR, f"marker_{marker_id}.png")
        cv2.imwrite(path, bordered)
        print(f"Saved {path}")
        markers.append(bordered)

    # Create combined sheet (2x2 grid)
    gap = 40
    mh, mw = markers[0].shape[:2]
    sheet_w = mw * 2 + gap * 3
    sheet_h = mh * 2 + gap * 3 + 80  # extra space for title

    sheet = np.ones((sheet_h, sheet_w), dtype=np.uint8) * 255

    # Title
    cv2.putText(sheet, "ArUco Calibration Markers (36mm, DICT_4X4_50)", (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 2)
    cv2.putText(sheet, "Cut out and place at ring cardinal points", (20, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, 80, 1)

    positions = [
        (gap, 80 + gap),                     # top-left
        (gap + mw + gap, 80 + gap),           # top-right
        (gap, 80 + gap + mh + gap),           # bottom-left
        (gap + mw + gap, 80 + gap + mh + gap) # bottom-right
    ]

    for i, (x, y) in enumerate(positions):
        sheet[y:y+mh, x:x+mw] = markers[i]
        # Label
        cv2.putText(sheet, labels[i], (x + 10, y + mh + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1)

    sheet_path = os.path.join(OUTPUT_DIR, "aruco_sheet.png")
    cv2.imwrite(sheet_path, sheet)
    print(f"\nSaved combined sheet: {sheet_path}")
    print("\nInstructions:")
    print("  1. Print at 100% scale (no fit-to-page)")
    print("  2. Cut out the 4 markers")
    print("  3. Place on ring: ID0=top, ID1=right, ID2=bottom, ID3=left")
    print("  4. Run calibration with F5/F6")


if __name__ == "__main__":
    generate_markers()
