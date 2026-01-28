from djitellopy import Tello
import pygame
import time

tello = Tello(host="192.168.10.1")
tello.connect()
print(f"Battery: {tello.get_battery()}%")

pygame.init()
win = pygame.display.set_mode((400, 400))
pygame.display.set_caption("Tello Control")

def get_keyboard_input():
    lr, fb, ud, yv = 0, 0, 0, 0 # left/right, forward/backward, up/down, yaw velocity
    speed = 100
    yaw_rate = 90

    keys = pygame.key.get_pressed()

    if keys[pygame.K_w]:
        fb = speed
    if keys[pygame.K_s]:
        fb = -speed
    if keys[pygame.K_a]:
        lr = -speed
    if keys[pygame.K_d]:
        lr = speed
    if keys[pygame.K_e]:
        if not tello.is_flying:
            tello.takeoff()
        else:
            ud = speed  # Go up if already in the air
    if keys[pygame.K_q]:
        ud = -speed
    if keys[pygame.K_RIGHT]:
        yv = yaw_rate
    if keys[pygame.K_LEFT]:
        yv = -yaw_rate
    if keys[pygame.K_LCTRL+pygame.K_q]:
        if tello.is_flying:
            tello.land()

    return [lr, fb, ud, yv]

run = True
while run:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            run = False

    vals = get_keyboard_input()
    tello.send_rc_control(vals[0], vals[1], vals[2], vals[3])

    pygame.time.delay(20)

pygame.quit()