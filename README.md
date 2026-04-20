# Samatma ISFCR: Centralised Access Control & Dashboard

## High-Level Overview
The Samatma ISFCR project is a scalable, distributed smart-lock and multi-camera ecosystem. The core architecture uses a unified **Server (Raspberry Pi)** and multiple lightweight **Nodes** streaming visual data via HTTP API.

At its core, a central Flask-based web engine runs an asynchronous AI thread. This thread controls CPU usage by entering deep sleep and wakes up using environmental cues—either dynamically triggered by an **Infrared Obstacle/Motion Sensor**, or through an automated 30-second passive check-in sweep. When woken up, the system inspects all camera nodes. By capturing patterns and executing facial recognition models temporally across consecutive frames, it controls electronic relays on the Raspberry Pi to authenticate recognized faces or sounds a buzzer alarm for intruders.

Furthermore, it integrates safety checks including a **Temperature Sensor** system, buzzing if the environment breaches fixed safety margins.

## Hardware Requirements & Wiring Pinout

To fully utilize this system on the Raspberry Pi, the following minimal hardware configuration is expected. **WARNING: Ensure all logic modules are powered via the 3.3V (3V3) pin, and NEVER the 5V pin, to avoid destroying your Pi.**

### Required Hardware:
1. **Raspberry Pi** (Running standard RaspiOS)
2. **DHT-11 Sensor Module** (For environmental monitoring)
3. **IR Obstacle Avoidance / PIR Sensor** (Digital module)
4. **Relay Module** (Controls electronic door locks/access)
5. **Active Buzzer Module** (Used for pulsing intruder alarm)
6. **USB Webcams / Secondary Computers** (To act as stream nodes)

### Complete Wiring Map:
- **DHT-11 Temperature Sensor** 
  - VCC: 3.3V
  - GND: Ground
  - DATA: **GPIO 4** (Physical Pin 7)
- **IR Motion/Obstacle Sensor**
  - VCC: 3.3V
  - GND: Ground
  - OUT: **GPIO 18** (Physical Pin 12)
- **Unlock Relay Controller**
  - IN/Signal: **GPIO 17** (Physical Pin 11)
- **Buzzer Alarm**
  - Positive/I-O: **GPIO 27** (Physical Pin 13)

## Features Implemented

1. **Flask API Dashboard & Real-Time Orchestration:**
   - Instead of basic sockets, the architecture has transitioned to a fully scalable HTTP (`POST`) infrastructure.
   - Provides a comprehensive, secure web portal on port `5000` bound to the local network and Tailscale interface (i.e. `100.67.122.47`).
   - Admin access is protected via robust session logic mechanism. (Credentials: `admin` / `samatma_isfcr_head`).

2. **Infinite Distributed Camera Nodes:**
   - Any hardware device running Python can beam camera data to the Pi using `node_client.py`.
   - The AI natively ingests dynamic feeds coming off `/api/upload/<cam_id>` and multiplexes inference without locking resources.
   - You can add infinite cameras from infinite rooms simply by providing a new `--cam` label string in the command!

3. **IR-Based Core Awakening / CPU Power Management:**
   - Machine Learning on video feeds rapidly throttles Pi temperature and CPU constraints.
   - Data streams are cached locally in the HTTP framework but silently ignored by the `FaceRecognizer` thread unless:
     A) The physical GPIO IR hardware sensor dynamically triggers an immediate physical wakeup sequence.
     B) A passive background sweep once every 30 seconds detects a face.
   - If either trigger occurs, it wakes for 30 seconds and processes frames in high-fidelity mode.

4. **Temperature Threshold Alarm:**
   - Integrated logic mapped through `EnvironmentSensors` inside `gpio_control.py`. Checks system temperature and overrides the buzzer relay for 3 continuous seconds if critical thresholds are broken (e.g. `> 45°C`).

5. **Premium Modern Glassmorphism UI:**
   - Web interface uses extremely modern design standards: dark mode, ambient background glow orbs, CSS grid, system monitoring updates via AJAX `fetch`, and pulsing status identifiers without needing active page reloads.

## Environment Breakdown for LLMs

- **`main.py`**: The definitive entrypoint. Boots the webserver and spawns the `background_processing_loop`. It controls hardware authentication bounds, manages temporal stability arrays `[True, False, ...]`, assesses temperature alarms, and binds `0.0.0.0:5000`.
- **`node_client.py`**: A drop-in Python executable designed purely to send network camera byte streams. Runs infinitely, encodes feeds aggressively to JPEG for 0-latency HTTP transfer logic.
- **`gpio_control.py`**: Acts as a HAL (Hardware Abstraction Layer). Houses `AccessController` for Relay/Buzzer manipulation, and explicitly contains the `EnvironmentSensors` class acting as an abstraction payload for standard Digital IR sensors and CPUTemperature reads. 
- **`recognition.py` / `face_database.py`**: Standard L2 normalization vector comparison libraries relying on OpenCV Cascade detection. Data preserved permanently on disk as `.pkl`.
- **`templates/`**: Hosts Jinja2 standard HTML structures designed explicitly with modern embedded CSS aesthetics.

### Launch Commands
**Boot Server on Pi:** `python main.py`
**Launch Node on Mac/PC:** `python node_client.py --url http://<PI_TAILSCALE_OR_LOCAL_IP>:5000 --cam Door_Camera`
