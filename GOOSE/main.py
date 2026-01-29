import pygame
from core.drone import DroneController

# NOTE: This Pygame window is a temporary placeholder for testing RC logic.
# The final implementation will use Kivy for the user interface.

# Constants
SCREEN_WIDTH = 400
SCREEN_HEIGHT = 400
SPEED = 50
YAW_SPEED = 60
UD_SPEED = 60 

def init_window():
    pygame.init()
    pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Tello Control Center")

def get_keyboard_input(controller):
    lr, fb, ud, yv = 0, 0, 0, 0
    
    keys = pygame.key.get_pressed()

    # Movement Controls (WASD / Arrows)
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        lr = -SPEED
    elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        lr = SPEED

    if keys[pygame.K_UP] or keys[pygame.K_w]:
        fb = SPEED
    elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
        fb = -SPEED

    # Altitude Controls (Space/Shift)
    if keys[pygame.K_SPACE]:
        ud = UD_SPEED
    elif keys[pygame.K_LSHIFT]:
        ud = -UD_SPEED

    # Rotation Controls (Q/E)
    if keys[pygame.K_q]:
        yv = -YAW_SPEED
    elif keys[pygame.K_e]:
        yv = YAW_SPEED

    # Management Controls
    if keys[pygame.K_t]: 
        controller.takeoff()
    
    if keys[pygame.K_l]:
        controller.land()

    return [lr, fb, ud, yv]

def main():
    controller = DroneController()
    controller.connect()

    init_window()

    run = True
    while run:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False

        vals = get_keyboard_input(controller)
        controller.send_rc_control(vals[0], vals[1], vals[2], vals[3])

        pygame.time.delay(50) 

    controller.cleanup()
    pygame.quit()

if __name__ == "__main__":
    main()
