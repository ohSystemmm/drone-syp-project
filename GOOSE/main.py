import os
import sys
import logging
import av

# Disable Kivy argument parser so we can have our own --kivy flag handling
os.environ.setdefault("KIVY_NO_ARGS", "1")
# Set environment variables to suppress OpenCV/FFmpeg noisy UDP decoding warnings
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "loglevel;quiet"
os.environ["OPENCV_LOG_LEVEL"] = "FATAL"

# Silence libavcodec logging to stop the "left block unavailable" spam.
av.logging.set_level(av.logging.FATAL)

from core import setup_logging, parse_args, GooseApp
from ui import Setup

# djitellopy sets LOGGER.setLevel(logging.INFO) when imported.
# We must ensure our level takes effect.
logging.getLogger('djitellopy').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def main():
    args = parse_args()
    
    # Handle Kivy UI mode separately
    if args.kivy:
        logger.info("Starting Kivy UI mode")
        Setup(args)
    else:
        # Standard Pygame/Vision mode
        setup_logging()
        logger.info("Starting Pygame/Vision mode")
        app = GooseApp(args)
        app.start()

if __name__ == "__main__":
    main()
