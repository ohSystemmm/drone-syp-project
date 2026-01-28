import robomaster
from robomaster import robot

if __name__ == '__main__':
    # Try to set the specific IP if it exists on the host
    import netifaces
    target_ip = "192.168.10.2"
    found_ip = False
    try:
        for interface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                for addr_info in addrs[netifaces.AF_INET]:
                    if addr_info['addr'] == target_ip:
                        robomaster.config.LOCAL_IP_STR = target_ip
                        found_ip = True
                        break
            if found_ip:
                break
    except Exception:
        pass
    
    if not found_ip:
        print(f"Warning: IP {target_ip} not found on local interfaces. Using default/auto-detected IP.")

    drone = robot.Drone()
    drone.initialize(conn_type='ap')

    flight = drone.flight
    version = drone.get_sdk_version()
    sn = drone.get_sn()
    print("Robot version: {0}".format(version))
    print("Sn: {0}".format(sn))

    flight.takeoff().wait_for_completed()
    flight_action = flight.forward(distance=50)
    flight.land().wait_for_completed()
    drone.close()