import cv2
import numpy as np

class ObjectDetector:
    def __init__(self, model_path):
        """
        Initialize the Object Detector.
        Supports both .pt (PyTorch) and .onnx (ONNX) models via Ultralytics API.
        
        :param model_path: Path to the .pt or .onnx model file.
        """
        self.model_path = model_path
        self.model = None
        self.is_onnx = model_path.lower().endswith('.onnx')

    def load_model(self):
        """
        Loads the model. 
        """
        print(f"Loading model from {self.model_path}...")
        try:
            from ultralytics import YOLO
            self.model = YOLO(self.model_path, task='detect')
            print("Model loaded successfully.")
        except ImportError:
            print("Error: 'ultralytics' library not found. Please install requirements.")
        except Exception as e:
            print(f"Failed to load model: {e}")

    def detect(self, frame, conf_threshold=0.5, draw_center=True):
        """
        Performs inference on a single frame.
        :param frame: The video frame (numpy array).
        :param conf_threshold: Confidence threshold for detections.
        :param draw_center: Whether to draw the center point of the bounding box.
        :return: Tuple(Annotated Frame, List of Detections)
        """
        if self.model is None:
            return frame, []

        # Use .predict instead of .track to avoid 'lap' dependency
        results = self.model.predict(frame, conf=conf_threshold, verbose=False)
        
        detections = []
        # plot() returns the image in BGR
        annotated_frame = results[0].plot() 

        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls = int(box.cls[0])
                name = self.model.names[cls]
                
                # track_id is not available in .predict mode
                track_id = None

                # Calculate center
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)

                if draw_center:
                    # Draw a bright green circle at the center
                    cv2.circle(annotated_frame, (cx, cy), 5, (0, 255, 0), -1)
                    # Optional: Draw coordinates text
                    cv2.putText(annotated_frame, f"{cx},{cy}", (cx + 10, cy), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

                detections.append({
                    'box': [int(x1), int(y1), int(x2), int(y2)],
                    'center': (cx, cy),
                    'conf': conf,
                    'class': cls,
                    'name': name,
                    'track_id': track_id
                })

        return annotated_frame, detections
