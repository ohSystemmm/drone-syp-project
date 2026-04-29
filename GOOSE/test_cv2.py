import os
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "video_codec;h264_cuvid|loglevel;quiet"
import cv2
print(os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS"))
