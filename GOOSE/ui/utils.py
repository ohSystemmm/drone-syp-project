import cv2
import pygame
import numpy as np

def draw_osd_text(surface, text, position, font_obj, text_color=(255, 255, 255), bg_color=(0, 0, 0, 150)):
    text_surf = font_obj.render(text, True, text_color)
    x, y = position
    bg_rect = pygame.Rect(x - 5, y - 5, text_surf.get_width() + 10, text_surf.get_height() + 10)
    shape_surf = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
    pygame.draw.rect(shape_surf, bg_color, shape_surf.get_rect(), border_radius=5)
    surface.blit(shape_surf, bg_rect.topleft)
    surface.blit(text_surf, position)

def draw_detections(frame, detections):
    for d in detections:
        box = d['box']
        x1, y1, x2, y2 = box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cx, cy = d['center']
        cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1) 
        track_id = d.get('track_id')
        id_text = f"ID: {track_id} " if track_id is not None else ""
        label = f"{id_text}{d['name']} {d['conf']:.2f}"
        cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    return frame

def draw_sticks(surface, sticks, x, y, size=80):
    roll, pitch, throttle, yaw = sticks
    surface.fill((0, 0, 0, 150), pygame.Rect(x, y, size, size))
    surface.fill((0, 0, 0, 150), pygame.Rect(x + size + 20, y, size, size))
    lx = x + size//2 + int(yaw * size//2)
    ly = y + size//2 - int(throttle * size//2)
    rx = x + size + 20 + size//2 + int(roll * size//2)
    ry = y + size//2 + int(pitch * size//2)
    pygame.draw.circle(surface, (255, 255, 255), (lx, ly), 6)
    pygame.draw.circle(surface, (255, 255, 255), (rx, ry), 6)
