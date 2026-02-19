import cv2
import os
import glob
import sys

def fix_video(input_path):
    directory, filename = os.path.split(input_path)
    name, ext = os.path.splitext(filename)
    
    # Avoid re-fixing already fixed files
    if name.endswith("_fixed"):
        print(f"Skipping {filename} (appears to be already fixed)")
        return

    output_path = os.path.join(directory, f"{name}_fixed{ext}")
    
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"Error opening {filename}")
        return

    # Get video properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if fps == 0: fps = 30.0 # Fallback

    # Define codec (avc1 is H.264, universally supported by browsers/Roboflow)
    # If this fails, try 'mp4v' again or ensure openh264 is installed.
    fourcc = cv2.VideoWriter_fourcc(*'avc1')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    print(f"Processing {filename}...")
    print(f"  > Output: {os.path.basename(output_path)}")
    print(f"  > Resolution: {width}x{height}, FPS: {fps}")

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # --- THE FIX ---
        # The original video has Red and Blue channels swapped.
        # Calling cvtColor with BGR2RGB swaps them back.
        fixed_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        out.write(fixed_frame)
        
        frame_count += 1
        if frame_count % 100 == 0:
            print(f"  > Processed {frame_count}/{total_frames} frames", end='\r')

    print(f"  > Done! {frame_count} frames processed.")
    
    cap.release()
    out.release()

def main():
    # Default to the recordings directory in the GOOSE project
    recordings_dir = os.path.join(os.path.dirname(__file__), "recordings")
    
    # Check if a specific file/folder was passed as an argument
    if len(sys.argv) > 1:
        target = sys.argv[1]
        if os.path.isfile(target):
            fix_video(target)
            return
        elif os.path.isdir(target):
            recordings_dir = target

    print(f"Scanning directory: {recordings_dir}")
    if not os.path.exists(recordings_dir):
        print("Directory not found.")
        return

    # Find all MP4s
    videos = glob.glob(os.path.join(recordings_dir, "*.mp4"))
    
    if not videos:
        print("No .mp4 files found.")
        return

    for video in videos:
        fix_video(video)

if __name__ == "__main__":
    main()
