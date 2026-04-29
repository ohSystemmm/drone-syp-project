# 🪿 G.O.O.S.E.

**G**arbage **O**perating **O**n **S**hit **E**lectronics

Welcome to the official repository for **Project Horizon**. This software is a specialized application designed to interface with the **DJI RoboMaster TT (Tello Talent)**. Developed at **HTL Saalfelden** for the 2025-2026 academic year, this project focuses on advanced control, telemetry, and autonomous flight maneuvers.

---

## 📋 Project Overview

The **G.O.O.S.E.** system allows users to remotely control a programmable educational drone equipped with an IMU, distance sensor, barometer, and front-facing camera. The software is built using **Python** and a customized SDK to manage real-time flight data and image processing.

* **Project Period:** January 7, 2026 – June 17, 2026.


* **Target Devices:** Desktop systems and mobile mobile devices.


* **Methodology:** Agile development using **SCRUM**.



---

## ✨ Features

### 1. Connection & Safety

* **Manual Handshake:** Users manually input the drone's IP address to establish a connection.


* **Live Status:** Visual indicators for connection health (Connected/Disconnected/Error).


* **Safety Protocol:** In case of connection loss, the drone is programmed to enter a safe state, such as automatic landing.


* **Panic Button:** A dedicated emergency stop to immediately halt flight or land.



### 2. Flight Control

* **Real-time Maneuvers:** Support for Take-off, Landing, Pitch, Roll, Yaw, and Throttle.


* **Flexible Inputs:** Control via virtual joysticks/buttons or keyboard (WASD/Arrows).


* **Course Recording:** Record user commands with timestamps and intensity to save and replay flight paths.



### 3. Telemetry & Vision

* **Data Dashboard:** Real-time display of battery level, altitude, speed, and orientation.


* **Visual Intelligence:** * Live video stream from the front camera.


* Automatic recognition and marking of humans.


* Autonomous detection and navigation through ring-shaped obstacles.




* **Mapping:** 2D visualization of the flight path and current drone position.



### 4. Hardware Interaction

* **LED Feedback:** The drone’s LEDs signal status: Blue (Connecting), Green (Success), and Red (Error).


* **Light Show:** Manual control over LED colors and effects like blinking.



---

## 🛠 Technical Design

The project documentation includes a comprehensive architecture to ensure modularity and extensibility:

* **Sprint 0:** Initial phase covering feasibility studies, time planning, and technical design reviews.



---

## 👥 Authors

* **[@QuarkOS](https://www.github.com/QuarkOS)**
* **[@ohSystemmm](https://www.github.com/ohSystemmm)**
* **[@nvmChris](https://www.github.com/nvmChris)**

---

> 
> **Disclaimer:** This software is for educational use at HTL Saalfelden. Fly responsibly and watch out for geese.
> 
