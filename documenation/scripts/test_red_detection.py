import cv2
import numpy as np
import sys
import os
import math

# Add parent directory to path to import GOOSE modules if needed
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from GOOSE.vision.detector import ObjectDetector
except ImportError:
    print("Could not import GOOSE.vision.detector. Make sure you're running from the correct directory.")
    sys.exit(1)

def nothing(x):
    pass

def main():
    model_path = r"C:\Users\Quark\PycharmProjects\GOOSE\GOOSE\assets\models\targetModel.onnx"
    video_path = r"C:\Users\Quark\PycharmProjects\GOOSE\GOOSE\recordings\flight_20260422_094847.mp4" 
    
    if len(sys.argv) > 1:
        video_path = sys.argv[1]

    detector = ObjectDetector(model_path)
    detector.load_model()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Failed to open video: {video_path}")
        return

    cv2.namedWindow("Red Detection", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Mask", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Settings", cv2.WINDOW_NORMAL)
    
    # Create trackbars for HSV ranges
    cv2.createTrackbar("H Min 1", "Settings", 0, 180, nothing)
    cv2.createTrackbar("H Max 1", "Settings", 10, 180, nothing)
    cv2.createTrackbar("H Min 2", "Settings", 160, 180, nothing)
    cv2.createTrackbar("H Max 2", "Settings", 180, 180, nothing)
    cv2.createTrackbar("S Min", "Settings", 167, 255, nothing)
    cv2.createTrackbar("S Max", "Settings", 255, 255, nothing)
    cv2.createTrackbar("V Min", "Settings", 0, 255, nothing)
    cv2.createTrackbar("V Max", "Settings", 255, 255, nothing)
    cv2.createTrackbar("Min Area", "Settings", 449, 2000, nothing)
    cv2.createTrackbar("Expand %", "Settings", 5, 50, nothing)
    cv2.createTrackbar("Morph Size", "Settings", 13, 50, nothing)

    paused = False

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                print("End of video. Looping...")
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            
            # Detect target
            _, detections = detector.detect(frame, conf_threshold=0.5)
            frame_disp = frame.copy()
            
        else:
            # Re-draw on the same frame if paused
            frame_disp = frame.copy()
            
        height, width = frame_disp.shape[:2]
        
        try:
            if cv2.getWindowProperty("Settings", cv2.WND_PROP_VISIBLE) < 1:
                break
        except cv2.error:
            break
        
        # Get trackbar values
        h_min1 = cv2.getTrackbarPos("H Min 1", "Settings")
        h_max1 = cv2.getTrackbarPos("H Max 1", "Settings")
        h_min2 = cv2.getTrackbarPos("H Min 2", "Settings")
        h_max2 = cv2.getTrackbarPos("H Max 2", "Settings")
        s_min = cv2.getTrackbarPos("S Min", "Settings")
        s_max = cv2.getTrackbarPos("S Max", "Settings")
        v_min = cv2.getTrackbarPos("V Min", "Settings")
        v_max = cv2.getTrackbarPos("V Max", "Settings")
        min_area = cv2.getTrackbarPos("Min Area", "Settings")
        expand_pct = cv2.getTrackbarPos("Expand %", "Settings") / 100.0
        morph_size = cv2.getTrackbarPos("Morph Size", "Settings")

        full_mask = np.zeros((height, width), dtype=np.uint8)

        for det in detections:
            x1, y1, x2, y2 = det['box']
            
            # Draw original bounding box
            cv2.rectangle(frame_disp, (x1, y1), (x2, y2), (255, 0, 0), 2)
            cv2.putText(frame_disp, "Target", (x1, max(0, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            
            # Calculate expansion
            w = x2 - x1
            h = y2 - y1
            
            exp_w = int(w * expand_pct)
            exp_h = int(h * expand_pct)
            
            ex1 = max(0, x1 - exp_w)
            ey1 = max(0, y1 - exp_h)
            ex2 = min(width, x2 + exp_w)
            ey2 = min(height, y2 + exp_h)
            
            # Draw expanded bounding box
            cv2.rectangle(frame_disp, (ex1, ey1), (ex2, ey2), (0, 255, 255), 2)
            cv2.putText(frame_disp, f"+{int(expand_pct*100)}% Box", (ex1, max(0, ey1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            
            # Crop to expanded box
            roi = frame[ey1:ey2, ex1:ex2]
            if roi.size == 0:
                continue
                
            # Convert ROI to HSV for red detection
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            
            # Red color has two ranges in HSV
            lower_red1 = np.array([h_min1, s_min, v_min])
            upper_red1 = np.array([h_max1, s_max, v_max])
            lower_red2 = np.array([h_min2, s_min, v_min])
            upper_red2 = np.array([h_max2, s_max, v_max])
            
            mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
            mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
            red_mask = cv2.bitwise_or(mask1, mask2)
            
            # Apply morphological operations to combine fragmented parts
            if morph_size > 0:
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (morph_size, morph_size))
                red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)
                red_mask = cv2.dilate(red_mask, kernel, iterations=1)
            
            # Put ROI mask into full mask for visualization
            full_mask[ey1:ey2, ex1:ex2] = cv2.bitwise_or(full_mask[ey1:ey2, ex1:ex2], red_mask)
            
            # Find contours of red areas
            contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            valid_contours = [cnt for cnt in contours if cv2.contourArea(cnt) > min_area]
            
            if valid_contours:
                # Find the largest contour (area with most red)
                largest_contour = max(valid_contours, key=cv2.contourArea)
                
                # Get bounding box for the largest red contour
                rx, ry, rw, rh = cv2.boundingRect(largest_contour)
                
                # Map back to original frame coordinates
                rx_frame = rx + ex1
                ry_frame = ry + ey1
                
                # Center point of the largest red area
                cx = rx_frame + rw // 2
                cy = ry_frame + rh // 2
                
                # Draw bounding box for the largest red target
                cv2.rectangle(frame_disp, (rx_frame, ry_frame), (rx_frame + rw, ry_frame + rh), (0, 0, 255), 2)
                
                # Fit an ellipse to estimate rotation and tilt
                if len(largest_contour) >= 5:
                    ellipse = cv2.fitEllipse(largest_contour)
                    (ell_x, ell_y), (minor_axis, major_axis), ell_angle = ellipse
                    
                    shifted_ellipse = ((ell_x + ex1, ell_y + ey1), (minor_axis, major_axis), ell_angle)
                    cv2.ellipse(frame_disp, shifted_ellipse, (255, 0, 255), 2)
                    
                    if major_axis > 0:
                        ratio = min(1.0, minor_axis / major_axis)
                        tilt_angle = math.degrees(math.acos(ratio))
                        
                        # Distance estimation
                        # Drone camera intrinsic parameters (assuming 960x720)
                        FX = 921.0
                        FY = 921.0
                        CX = width / 2.0
                        CY = height / 2.0
                        REAL_DIAMETER_CM = 50.0 # Standard LDARC ring outer diameter is 50cm
                        
                        z_cm = (REAL_DIAMETER_CM * FX) / major_axis
                        x_cm = ((ell_x + ex1) - CX) * z_cm / FX
                        y_cm = ((ell_y + ey1) - CY) * z_cm / FY
                        
                        info_text = f"Tilt: {int(tilt_angle)} deg | Rot: {int(ell_angle)} deg"
                        pos_text = f"X:{int(x_cm)} Y:{int(y_cm)} Z:{int(z_cm)} cm"
                        
                        # Simulated Autopilot
                        TARGET_Z = 100.0
                        cmd_lr = int(max(-80, min(80, x_cm * 0.6)))
                        cmd_ud = int(max(-80, min(80, -y_cm * 0.8)))
                        cmd_fb = int(max(-80, min(80, (z_cm - TARGET_Z) * 0.7)))
                        ap_text = f"CMD -> LR: {cmd_lr} | UD: {cmd_ud} | FB: {cmd_fb}"
                        
                        # Bottom right alignment
                        text_x = width - 400
                        cv2.putText(frame_disp, pos_text, (text_x, height - 65), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                        cv2.putText(frame_disp, info_text, (text_x, height - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
                        cv2.putText(frame_disp, ap_text, (text_x, height - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        
                        # Draw ellipse axes to show rotation
                        angle_rad = math.radians(ell_angle)
                        center = (int(ell_x + ex1), int(ell_y + ey1))
                        
                        # Ellipse angle in OpenCV is clockwise from the Y axis to the major axis
                        # Major axis line (Blue)
                        dx_major = (major_axis / 2) * math.sin(angle_rad)
                        dy_major = -(major_axis / 2) * math.cos(angle_rad)
                        cv2.line(frame_disp, center, (int(center[0] + dx_major), int(center[1] + dy_major)), (255, 0, 0), 2)
                        
                        # Minor axis line (Cyan)
                        dx_minor = (minor_axis / 2) * math.cos(angle_rad)
                        dy_minor = (minor_axis / 2) * math.sin(angle_rad)
                        cv2.line(frame_disp, center, (int(center[0] + dx_minor), int(center[1] + dy_minor)), (255, 255, 0), 2)
                
                # Draw a point at the center of the largest red area
                cv2.circle(frame_disp, (cx, cy), 5, (0, 255, 0), -1)
                cv2.putText(frame_disp, "Target Center", (cx + 10, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                
                # Draw contour mask on frame
                cv2.drawContours(frame_disp[ey1:ey2, ex1:ex2], [largest_contour], -1, (0, 255, 0), 1)

        cv2.imshow("Red Detection", frame_disp)
        cv2.imshow("Mask", full_mask)
        
        # Keyboard controls
        key = cv2.waitKey(30) & 0xFF
        if key == ord('q'):
            break
        elif key == ord(' '):  # Spacebar to pause
            paused = not paused
            
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
