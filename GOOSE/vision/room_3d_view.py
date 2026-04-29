import cv2
import numpy as np
import time
import math
import sys
import os

try:
    from direct.showbase.ShowBase import ShowBase
    from panda3d.core import (WindowProperties, DirectionalLight, AmbientLight,
                               Point3, Vec4, NodePath, CardMaker, LineSegs,
                               OrthographicLens, loadPrcFileData, Filename,
                               get_model_path, TransparencyAttrib)
    from direct.actor.Actor import Actor
    import gltf
    PANDA_AVAILABLE = True
except ImportError:
    PANDA_AVAILABLE = False
    print("[Room3DView] Warning: panda3d or panda3d-gltf not installed, 3D view will be disabled.")

# Room dimensions in cm (1 unit = 1 cm)
ROOM_SIZE = 200  # 2 meters


class PandaApp(ShowBase):
    def __init__(self, width=800, height=600):
        loadPrcFileData("", f"win-size {width} {height}")
        loadPrcFileData("", "window-title GOOSE 3D Isometric View")
        loadPrcFileData("", "sync-video 0")
        
        ShowBase.__init__(self)
        
        self.setBackgroundColor(0.04, 0.04, 0.06)
        self.disableMouse()
        
        # Orthographic iso camera — framed to show the 200cm room nicely
        lens = OrthographicLens()
        lens.setFilmSize(420, 315)
        self.cam.node().setLens(lens)
        
        # PBR shader for GLB materials
        try:
            import simplepbr
            simplepbr.init()
        except ImportError:
            print("[Room3DView] Warning: simplepbr not available, GLB textures may not render.")
        
        # Position camera for isometric view showing 2 back walls + floor
        self.camera.setPos(350, -350, 300)
        self.camera.lookAt(0, 0, 40)
        
        # Build the room
        self._build_room()
        
        # Target ring at center of room (0, 0, ~half height)
        self.target = self.loader.loadModel("models/misc/sphere")
        self.target.setColor(0.0, 0.6, 1.0, 1.0)
        self.target.setScale(5.0)
        self.target.setPos(0, 0, 0)  # Center of room
        self.target.reparentTo(self.render)
        self.target.setTransparency(TransparencyAttrib.MAlpha)
        self._target_blink_state = True
        
        # Load drone model
        self._load_drone()
        
        # Lighting
        alight = AmbientLight('alight')
        alight.setColor(Vec4(0.35, 0.35, 0.4, 1))
        alnp = self.render.attachNewNode(alight)
        self.render.setLight(alnp)

        dlight = DirectionalLight('dlight')
        dlight.setColor(Vec4(0.8, 0.8, 0.75, 1))
        dlnp = self.render.attachNewNode(dlight)
        dlnp.setHpr(45, -45, 0)
        self.render.setLight(dlnp)

        # Second directional for fill
        dlight2 = DirectionalLight('dlight2')
        dlight2.setColor(Vec4(0.3, 0.3, 0.35, 1))
        dlnp2 = self.render.attachNewNode(dlight2)
        dlnp2.setHpr(-135, -30, 0)
        self.render.setLight(dlnp2)

    def _build_room(self):
        """Build a 2m×2m×2m room: floor + 2 back walls (left and back)."""
        hs = ROOM_SIZE / 2  # 100 cm = half-size

        # --- FLOOR ---
        cm = CardMaker('floor')
        cm.setFrame(-hs, hs, -hs, hs)
        floor = self.render.attachNewNode(cm.generate())
        floor.setP(-90)
        floor.setZ(- hs)
        floor.setColor(0.12, 0.12, 0.14, 1)

        # --- BACK WALL (behind target, along X axis at Y = +hs) ---
        cm2 = CardMaker('back_wall')
        cm2.setFrame(-hs, hs, -hs, hs)
        back_wall = self.render.attachNewNode(cm2.generate())
        back_wall.setY(hs)
        back_wall.setColor(0.10, 0.10, 0.13, 1)

        # --- LEFT WALL (along Y axis at X = -hs) ---
        cm3 = CardMaker('left_wall')
        cm3.setFrame(-hs, hs, -hs, hs)
        left_wall = self.render.attachNewNode(cm3.generate())
        left_wall.setH(90)
        left_wall.setX(-hs)
        left_wall.setColor(0.08, 0.08, 0.11, 1)

        # --- Grid lines on floor ---
        ls = LineSegs()
        ls.setThickness(1.0)
        ls.setColor(0.18, 0.18, 0.22, 0.6)
        step = 25  # 25 cm grid
        for i in range(int(-hs), int(hs) + 1, step):
            ls.moveTo(i, -hs, -hs + 0.1)
            ls.drawTo(i, hs, -hs + 0.1)
            ls.moveTo(-hs, i, -hs + 0.1)
            ls.drawTo(hs, i, -hs + 0.1)
        grid = self.render.attachNewNode(ls.create())

        # --- Grid lines on back wall ---
        ls2 = LineSegs()
        ls2.setThickness(0.8)
        ls2.setColor(0.15, 0.15, 0.20, 0.4)
        for i in range(int(-hs), int(hs) + 1, step):
            # horizontal lines
            ls2.moveTo(-hs, hs - 0.1, i)
            ls2.drawTo(hs, hs - 0.1, i)
            # vertical lines
            ls2.moveTo(i, hs - 0.1, -hs)
            ls2.drawTo(i, hs - 0.1, hs)
        self.render.attachNewNode(ls2.create())

        # --- Grid lines on left wall ---
        ls3 = LineSegs()
        ls3.setThickness(0.8)
        ls3.setColor(0.13, 0.13, 0.18, 0.4)
        for i in range(int(-hs), int(hs) + 1, step):
            # horizontal lines
            ls3.moveTo(-hs + 0.1, -hs, i)
            ls3.drawTo(-hs + 0.1, hs, i)
            # vertical lines
            ls3.moveTo(-hs + 0.1, i, -hs)
            ls3.drawTo(-hs + 0.1, i, hs)
        self.render.attachNewNode(ls3.create())

        # --- Room edge lines (visible boundaries) ---
        edge = LineSegs()
        edge.setThickness(2.0)
        edge.setColor(0.25, 0.25, 0.35, 1)
        # Floor edges
        edge.moveTo(-hs, -hs, -hs); edge.drawTo(hs, -hs, -hs)
        edge.moveTo(-hs, -hs, -hs); edge.drawTo(-hs, hs, -hs)
        edge.moveTo(hs, -hs, -hs);  edge.drawTo(hs, hs, -hs)
        edge.moveTo(-hs, hs, -hs);  edge.drawTo(hs, hs, -hs)
        # Vertical edges
        edge.moveTo(-hs, hs, -hs);  edge.drawTo(-hs, hs, hs)
        edge.moveTo(hs, hs, -hs);   edge.drawTo(hs, hs, hs)
        edge.moveTo(-hs, -hs, -hs); edge.drawTo(-hs, -hs, hs)
        # Top edges
        edge.moveTo(-hs, hs, hs);   edge.drawTo(hs, hs, hs)
        edge.moveTo(-hs, -hs, hs);  edge.drawTo(-hs, hs, hs)
        self.render.attachNewNode(edge.create())

    def _load_drone(self):
        """Load the animated drone GLB model."""
        vision_dir = os.path.dirname(os.path.abspath(__file__))
        goose_dir = os.path.dirname(vision_dir)
        project_root = os.path.dirname(goose_dir)

        get_model_path().prepend_directory(Filename.fromOsSpecific(project_root).getFullpath())
        get_model_path().prepend_directory(Filename.fromOsSpecific(goose_dir).getFullpath())
        
        drone_base = os.path.join(goose_dir, "assets", "3dModels", "animated-drone")
        for sub in ("textures", "source"):
            sub_dir = os.path.join(drone_base, sub)
            if os.path.exists(sub_dir):
                get_model_path().prepend_directory(Filename.fromOsSpecific(sub_dir).getFullpath())

        model_rel_path = "GOOSE/assets/3dModels/animated-drone/source/Flying drone_.glb"
        if not os.path.exists(os.path.join(project_root, model_rel_path)):
            model_rel_path = "assets/3dModels/animated-drone/source/Flying drone_.glb"

        try:
            self.drone_actor = Actor(model_rel_path)
            self.drone_actor.reparentTo(self.render)
            self.drone_actor.setScale(2.0)
            self.drone_actor.setH(180)  # Fix model facing direction
            self.anim_names = self.drone_actor.getAnimNames()
            self._current_anim = None
        except Exception as e:
            print(f"[Room3DView] Failed to load drone model: {e}")
            self.drone_actor = self.loader.loadModel("models/box")
            self.drone_actor.setScale(5.0)
            self.drone_actor.setColor(0, 1, 0.5, 1)
            self.drone_actor.reparentTo(self.render)
            self.anim_names = []
            self._current_anim = None


class Room3DView:
    """
    3D diagnostic visualization using Panda3D.
    - 2m×2m×2m room with floor + 2 back walls.
    - Target at room center; drone positioned relative to target.
    - Target blinks red when detection is lost.
    - Smooth lerp interpolation between updates.
    """

    LERP_FACTOR = 0.12

    def __init__(self, width=800, height=600):
        self.width = width
        self.height = height
        self.app = None
        self._window_created = False
        
        # Smoothing state
        self._smooth_pos = np.array([0.0, -80.0, 0.0])
        self._smooth_h = 0.0
        self._smooth_p = 0.0
        self._smooth_r = 0.0
        
        # Target blink state
        self._last_blink_time = 0.0
        self._blink_on = True
        
        if PANDA_AVAILABLE:
            self.app = PandaApp(width, height)
            
    def update(self, pose, autopilot=None, debug_frame=None, is_flying=False):
        if not self.app:
            return
            
        has_target = pose is not None
        
        # --- Target blink logic ---
        now = time.monotonic()
        if has_target:
            # Target detected: solid cyan
            self.app.target.setColor(0.0, 0.6, 1.0, 1.0)
            self._blink_on = True
        else:
            # No target: blink red at 2 Hz
            if now - self._last_blink_time > 0.25:
                self._blink_on = not self._blink_on
                self._last_blink_time = now
            if self._blink_on:
                self.app.target.setColor(1.0, 0.1, 0.1, 1.0)
            else:
                self.app.target.setColor(1.0, 0.1, 0.1, 0.2)
        
        # Default positioning
        target_pos = np.array([0.0, -80.0, 0.0])
        target_h = 0.0
        target_p = 0.0
        target_r = 0.0
        
        if pose:
            # Map pose to room coordinates (1 unit = 1 cm)
            # Clamp to room bounds so drone flies "out" visually at edges
            p_x = pose.x_cm
            p_y = -pose.z_cm        # depth maps to -Y
            p_z = -pose.y_cm        # vertical
            
            target_pos = np.array([p_x, p_y, p_z])
            target_h = pose.angle_deg
            
        if autopilot:
            fb = getattr(autopilot, '_last_fb', 0)
            lr = getattr(autopilot, '_last_lr', 0)
            yv = getattr(autopilot, '_last_yv', 0)
            
            target_p = fb * 0.4
            target_r = -lr * 0.6
            target_h -= yv * 0.3 
            
        # Smooth interpolation (lerp)
        alpha = self.LERP_FACTOR
        self._smooth_pos = self._smooth_pos + alpha * (target_pos - self._smooth_pos)
        self._smooth_h = self._smooth_h + alpha * (target_h - self._smooth_h)
        self._smooth_p = self._smooth_p + alpha * (target_p - self._smooth_p)
        self._smooth_r = self._smooth_r + alpha * (target_r - self._smooth_r)

        # Animation switching
        if self.app.drone_actor and self.app.anim_names:
            target_anim = None
            if is_flying:
                target_anim = next((a for a in self.app.anim_names if 'hover' in a.lower() or 'fly' in a.lower()), self.app.anim_names[0])
            else:
                target_anim = next((a for a in self.app.anim_names if 'static' in a.lower() or 'idle' in a.lower()), None)
            
            if target_anim != self.app._current_anim:
                if target_anim:
                    self.app.drone_actor.loop(target_anim)
                else:
                    self.app.drone_actor.stop()
                self.app._current_anim = target_anim

        if self.app.drone_actor:
            self.app.drone_actor.setPos(self._smooth_pos[0], self._smooth_pos[1], self._smooth_pos[2])
            self.app.drone_actor.setHpr(180 + self._smooth_h, self._smooth_p, self._smooth_r)
            
        # CV2 diagnostic overlay
        if debug_frame is not None:
             m_w, m_h = 240, 180
             diag = cv2.resize(debug_frame, (m_w, m_h))
             if len(diag.shape) == 3:
                 diag = cv2.cvtColor(diag, cv2.COLOR_RGB2BGR)

             if pose and hasattr(pose, 'best_contour') and pose.best_contour is not None:
                 scale_x = m_w / debug_frame.shape[1]
                 scale_y = m_h / debug_frame.shape[0]
                 c_scaled = pose.best_contour.copy()
                 c_scaled[:, 0, 0] = (c_scaled[:, 0, 0] * scale_x).astype(np.int32)
                 c_scaled[:, 0, 1] = (c_scaled[:, 0, 1] * scale_y).astype(np.int32)
                 
                 cv2.drawContours(diag, [c_scaled], -1, (255, 0, 255), 2)
                 overlay = diag.copy()
                 cv2.fillPoly(overlay, [c_scaled], (255, 255, 0))
                 cv2.addWeighted(overlay, 0.3, diag, 0.7, 0, diag)
                 
             cv2.imshow("Mask Diagnostic Overlay", diag)
             self._window_created = True
              
        cv2.waitKey(1)
        self.app.taskMgr.step()
        
    def close(self):
        if self.app:
            self.app.destroy()
            self.app = None
        if self._window_created:
            try:
                cv2.destroyWindow("Mask Diagnostic Overlay")
            except:
                pass
