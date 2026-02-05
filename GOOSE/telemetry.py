from robomaster import robot
import pygame
import socket


# Orientierung 7
# höhe 7
# geschwindigkeit 7
# battiriestand
# IP
# Name zuweisen

# zeit 7
# flugmodus 7
class Telemetry:
    def __init__(self, drone: robot.Drone):
        self.drone = drone
        self.flight = drone.flight
        self.start_time = pygame.time.get_ticks()
        self.total_distance = 0.0
        self.last_position = None
        self.drone_name = None

    def get_battery(self):
        try:
            # Try to get battery from flight status
            return str(self.drone.battery[0])
        except Exception as e:
            print(f"Error getting Battery: {e}")
            return "N/A"  # Battery percentage

    def get_ip_address(self):
        try:
            # Get local IP address
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            return str(local_ip)
        except Exception as e:
            print(f"Error getting IP-adress: {e}")
            return "N/A"  # IPV4 address

    def get_flight_time(self):
        try:
            current_time = pygame.time.get_ticks()
            flight_time = (current_time - self.start_time) / 1000  # in seconds
            return f"{flight_time:.2f}s"
        except Exception as e:
            print(f"Error getting flight time: {e}")
            return "N/A"

    def get_orientation(self):
        try:
            attitude = self.flight.get_attitude()  # Roll, Pitch, Yaw in degrees
            return str(attitude)
        except Exception as e:
            print(f"Error getting orientation: {e}")
            return "N/A"

    def get_altitude(self):
        try:
            height = self.flight.get_height()  # Height in cm
            return str(height)
        except Exception as e:
            print(f"Error getting altitude: {e}")
            return "N/A"

    def update_distance(self):  # Update total distance flown
        try:
            current_position = self.flight.get_position()
            if self.last_position is not None:
                distance = ((current_position[0] - self.last_position[0]) ** 2 +
                            (current_position[1] - self.last_position[1]) ** 2 +
                            (current_position[2] - self.last_position[2]) ** 2) ** 0.5
                self.total_distance += distance
            self.last_position = current_position
            return f"{self.total_distance:.2f}m"
        except Exception as e:
            print(f"Error updating distance: {e}")
            return "N/A"

    def get_total_distance(self):  # Get total distance flown
        try:
            return f"{self.total_distance:.2f}m"
        except Exception as e:
            print(f"Error getting total distance: {e}")
            return "N/A"

    def get_flight_mode(self):
        try:
            flight_mode = self.flight.get_flight_mode()  # Current flight mode
            return str(flight_mode)
        except Exception as e:
            print(f"Error getting flight mode: {e}")
            return "N/A"

    def set_name(self, name: str):  # Set drone name
        try:
            self.drone_name = name
        except Exception as e:
            print(f"Error setting name: {e}")

    def get_name(self):  # Get drone name
        try:
            return str(self.drone_name) if self.drone_name is not None else "Unknown"
        except Exception as e:
            print(f"Error getting name: {e}")
            return "Unknown"

    def get_speed(self):
        try:
            speed = self.flight.get_speed_y()  # Speed in cm/s
            return str(speed)
        except Exception as e:
            print(f"Error getting speed: {e}")
            return "N/A"


