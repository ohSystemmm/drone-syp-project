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
    lr, fb, ud, yv = 0, 0, 0, 0
    speed = 100

    keys = pygame.key.get_pressed()

    if keys[]


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