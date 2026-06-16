import cv2


def draw_detections(frame_bgr, detections):
    """Draw detector boxes on a BGR frame."""
    for det in detections or []:
        try:
            x1, y1, x2, y2 = [int(v) for v in det.get("box", (0, 0, 0, 0))]
            cx, cy = det.get("center", ((x1 + x2) // 2, (y1 + y2) // 2))
            label = det.get("name", "target")
            conf = det.get("conf")
            text = f"{label} {conf:.2f}" if isinstance(conf, (int, float)) else str(label)

            cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), (0, 220, 80), 2)
            cv2.circle(frame_bgr, (int(cx), int(cy)), 4, (0, 220, 255), -1)
            cv2.putText(
                frame_bgr,
                text,
                (x1, max(16, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 220, 80),
                1,
                cv2.LINE_AA,
            )
        except Exception:
            continue
    return frame_bgr
