import cv2
import numpy as np
import math
from typing import Optional, Dict, List, Tuple

class SectorPoseSolver:
    """
    Estimates 3D pose using the relative area ratios of 8 circular sectors.
    Based on the principle that sectors closer to the camera appear larger 
    under perspective projection.
    """
    def __init__(self, camera_matrix: np.ndarray, real_radius_cm: float = 25.0):
        self.camera_matrix = camera_matrix
        self.fx = camera_matrix[0, 0]
        self.fy = camera_matrix[1, 1]
        self.cx = camera_matrix[0, 2]
        self.cy = camera_matrix[1, 2]
        self.real_radius = real_radius_cm

    def solve_from_mask(self, mask: np.ndarray, centroid: Tuple[float, float]) -> Optional[Dict]:
        """
        Calculates areas of 8 sectors around the centroid and estimates pose.
        
        :param mask: Binary mask of the ring.
        :param centroid: (x, y) center of the ring in image coordinates.
        :return: Dict containing pose estimation data.
        """
        h, w = mask.shape
        cx, cy = centroid
        
        # 1. Define 8 sectors (45 degrees each)
        # Coordinate system: 0 radians is 'Right' (+X), goes clockwise.
        sector_areas = []
        
        # Create a coordinate grid relative to centroid
        y_grid, x_grid = np.ogrid[:h, :w]
        rel_x = x_grid - cx
        rel_y = y_grid - cy
        
        # Calculate angles for all pixels
        angles = np.arctan2(rel_y, rel_x) # Range [-pi, pi]
        
        for i in range(8):
            # Shift range to [0, 2*pi] for easier indexing
            start_angle = -math.pi + (i * math.pi / 4)
            end_angle = -math.pi + ((i + 1) * math.pi / 4)
            
            # Create a boolean mask for this sector
            sector_mask = (angles >= start_angle) & (angles < end_angle)
            
            # Intersect with the ring mask and count pixels
            area = np.sum(mask[sector_mask] > 0)
            sector_areas.append(float(area))

        if sum(sector_areas) == 0:
            return None

        # 2. Analyze Area Distribution
        # The sector with the maximum area is the "closest" part of the ring.
        max_idx = np.argmax(sector_areas)
        
        # 3. Estimate Tilt (Differential Area Analysis)
        # Opposite sectors: (0, 4), (1, 5), (2, 6), (3, 7)
        # Area difference ratio is proportional to tilt.
        def get_ratio(i1, i2):
            a1, a2 = sector_areas[i1], sector_areas[i2]
            return (a1 - a2) / (a1 + a2 + 1e-6)

        ratios = [get_ratio(i, (i + 4) % 8) for i in range(4)]
        
        # Map ratios to tilt components
        # Index 0/4: Horizontal (Right vs Left) -> tilt_y (rotation around Y)
        # Index 2/6: Vertical (Bottom vs Top) -> tilt_x (rotation around X)
        tilt_y_factor = ratios[0] 
        tilt_x_factor = ratios[2]

        return {
            'sector_areas': sector_areas,
            'closest_sector_idx': int(max_idx),
            'tilt_x_factor': float(tilt_x_factor),
            'tilt_y_factor': float(tilt_y_factor),
            'total_area': float(sum(sector_areas))
        }

    def visualize(self, frame: np.ndarray, centroid: Tuple[float, float], sector_data: Dict) -> np.ndarray:
        """Draws the sector boundaries and areas for debugging."""
        cx, cy = int(centroid[0]), int(centroid[1])
        areas = sector_data['sector_areas']
        max_idx = sector_data['closest_sector_idx']
        
        overlay = frame.copy()
        for i in range(8):
            angle_rad = -math.pi + (i * math.pi / 4) + (math.pi / 8)
            # Draw sector lines
            line_angle = -math.pi + (i * math.pi / 4)
            lx = int(cx + 200 * math.cos(line_angle))
            ly = int(cy + 200 * math.sin(line_angle))
            cv2.line(overlay, (cx, cy), (lx, ly), (255, 255, 255), 1)
            
            # Label area
            tx = int(cx + 80 * math.cos(angle_rad))
            ty = int(cy + 80 * math.sin(angle_rad))
            color = (0, 255, 0) if i == max_idx else (200, 200, 200)
            cv2.putText(overlay, f"{int(areas[i])}", (tx-20, ty), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            
        return overlay
