import os
import time
import threading
import cv2
import numpy as np
from flask import Flask, render_template, request, session, redirect, url_for, Response, jsonify
from utils import logger
from recognition import FaceRecognizer
from gpio_control import AccessController, EnvironmentSensors

app = Flask(__name__)
# Secure secret key for admin session (could be env var in production)
app.secret_key = "samatma_isfcr_admin_secret"

# Initialize Hardware and Recognition
recognizer = FaceRecognizer(tolerance=0.88) # Tighter threshold to prevent multiple false identifications
access_controller = AccessController()
# Default IR pin to 18, and alarm threshold to 45C
env_sensors = EnvironmentSensors(ir_pin=18, temp_threshold=45.0)

# Global State Management
GLOBAL_AWAKE_UNTIL = 0
last_poll_time = time.time()

# Store frames and state for each active network camera
# Structure: { cam_id: {'frame': bytes, 'unrec_start': float, 'recent_rec': [bool], 'boxes': []} }
cameras = {}
events = []

def log_ui_event(msg):
    event = f"[{time.strftime('%H:%M:%S')}] {msg}"
    events.insert(0, event)
    # Keep last 50 events to prevent memory bloat
    if len(events) > 50:
        events.pop()
    logger.info(msg)

def background_processing_loop():
    """
    Background worker thread. Runs infinitely.
    Polls the sensors, manages deep sleep to save CPU, and processes uploaded camera frames.
    """
    global GLOBAL_AWAKE_UNTIL, last_poll_time
    
    # Ensures database has at least 1 user before processing to prevent blind runtime
    if not recognizer.db.names:
        log_ui_event("WARNING: No users in face database. Access will never unlock.")

    while True:
        time.sleep(0.1) # Small sleep to prevent CPU hogging
        current_time = time.time()
        
        # 1. Temperature Warning Check
        if int(current_time) % 5 == 0:
            if env_sensors.check_temp_alarm(access_controller):
                # Will trigger Buzzer automatically via the class method
                log_ui_event(f"TEMP ALARM! Exceeded safe limit ({env_sensors.get_temperature():.1f}C)")
        
        # 2. Check Physical IR Sensor (Primary Wake Trigger)
        if env_sensors.is_ir_triggered():
            if current_time >= GLOBAL_AWAKE_UNTIL:
                log_ui_event("IR Sensor detected motion! Waking up for 30s.")
            GLOBAL_AWAKE_UNTIL = current_time + 30
            
        # 3. Determine if system should process frames based on Wake states
        is_awake = current_time < GLOBAL_AWAKE_UNTIL
        should_poll = False
        
        if not is_awake and (current_time - last_poll_time) >= 30:
            should_poll = True
            last_poll_time = current_time
            log_ui_event("30s Poll trigger: Checking all active webcams for faces...")
            
        # If neither IR actively tripped nor our 30-sec poll triggered, skip processing completely
        if not is_awake and not should_poll:
            continue
            
        # 4. Heavy Lifting: Process 1 frame from EACH connected camera node
        faces_detected_in_poll = False
        
        for cam_id, cam_data in list(cameras.items()):
            frame_bytes = cam_data.get('frame')
            if not frame_bytes: continue
            
            # Decode the network byte feed into an OpenCV format array
            arr = np.frombuffer(frame_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None: continue
            
            # Compress to speed up face recognition matching
            small_frame = cv2.resize(frame, (0, 0), fx=(1/4), fy=(1/4))
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            
            results = recognizer.check_faces(rgb_small_frame)
            
            if len(results) > 0:
                faces_detected_in_poll = True
                frame_auth = any([auth for (_, _, auth) in results])
                
                # Check for an authorized face
                if frame_auth:
                    cam_data['unrec_start'] = None
                    cam_data['recent_rec'].append(True)
                else:
                    # Treat as unidentified presence
                    cam_data['recent_rec'].append(False)
                    if cam_data.get('unrec_start') is None:
                        cam_data['unrec_start'] = current_time
            else:
                cam_data['unrec_start'] = None
                
            # Buffer constraint to avoid running out of memory bounds
            req_frames = 3
            rec = cam_data['recent_rec']
            if len(rec) > req_frames:
                rec.pop(0)
                
            # 5. Access Evaluators (Per Camera Basis)
            
            # Approval
            if len(rec) == req_frames and all(rec):
                log_ui_event(f"[{cam_id}] ACCESS APPROVED. Unlocking!")
                access_controller.approve_access()
                rec.clear() # Reset consecutive counter after approval
                
            # Rejection (Unrecognized Intruder Timer)
            if cam_data['unrec_start'] and current_time - cam_data['unrec_start'] >= 2.5:
                log_ui_event(f"[{cam_id}] INTRUDER ALARM triggered!")
                access_controller.reject_access()
                cam_data['unrec_start'] = None
                rec.clear()
                
            # Cache the physical boxes for the web stream renderer
            cam_data['boxes'] = results
            cam_data['processed_time'] = current_time
            
        # If the passive 30-sec poll discovered a face anywhere, we stay awake for the next 30s continuously
        if should_poll and faces_detected_in_poll:
            log_ui_event("Face found during passive poll! System waking up for 30s.")
            GLOBAL_AWAKE_UNTIL = current_time + 30

def generate_video_feed(cam_id):
    """
    Generator function designed for HTTP chunked Response streaming.
    Takes the latest raw byte frame uploaded, injects the colored boxes visually, and yields.
    """
    while True:
        cam_data = cameras.get(cam_id)
        if not cam_data or not cam_data.get('frame'):
            time.sleep(0.5)
            continue
            
        frame_bytes = cam_data['frame']
        
        # Start drawing the bounding boxes (if any) onto the stream image
        arr = np.frombuffer(frame_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        
        boxes = cam_data.get('boxes', [])
        for (top, right, bottom, left), name, is_auth in boxes:
            t, r, b, l = top*4, right*4, bottom*4, left*4
            color = (0, 255, 0) if is_auth else (0, 0, 255)
            
            # Draw Main Wrapper Box
            cv2.rectangle(img, (l, t), (r, b), color, 2)
            # Draw Filled Text Container
            cv2.rectangle(img, (l, b - 30), (r, b), color, cv2.FILLED)
            cv2.putText(img, name, (l + 5, b - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
        # Draw status text overlaid on the image
        current_time = time.time()
        is_awake = current_time < GLOBAL_AWAKE_UNTIL
        status = "AWAKE" if is_awake else "SLEEPING (POLL MODE)"
        cv2.putText(img, f"State: {status}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,0), 2)
        
        # Transcode back to jpg sequence component
        ret, jpeg = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
        frame_out = jpeg.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_out + b'\r\n')
        
        # Output rate limited to prevent network exhaustion
        time.sleep(0.1) 


# ==================================
# FLASK WEB SERVER ROUTES
# ==================================

@app.route("/", methods=["GET", "POST"])
def login():
    """Secure Portal entry point."""
    if request.method == "POST":
        if request.form.get("username") == "admin" and request.form.get("password") == "samatma_isfcr_head":
            session["logged_in"] = True
            log_ui_event("Admin logged into dashboard.")
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Invalid credentials")
        
    # Skip login immediately if authenticated
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
        
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    """The central control panel."""
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("index.html", cameras=cameras.keys(), events=events)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/api/upload/<cam_id>", methods=["POST"])
def api_upload(cam_id):
    """
    Node Reception Endpoint.
    Remote machines (like a secondary laptop capturing webcam) 
    send a POST containing a JPEG byte string here to be ingested by the background Pi processor.
    """
    if 'frame' not in request.files:
        return jsonify({"error": "No frame part provided."}), 400
        
    # Dynamically register the camera node
    if cam_id not in cameras:
        cameras[cam_id] = {'recent_rec': [], 'unrec_start': None, 'boxes': [], 'frame': None}
        log_ui_event(f"New camera node successfully registered: {cam_id}")
        
    cameras[cam_id]['frame'] = request.files['frame'].read()
    return jsonify({"status": "received"})

@app.route("/video_feed/<cam_id>")
def video_feed(cam_id):
    """The stream endpoint sourced by the img dom blocks"""
    if not session.get("logged_in"): return "Unauthorized", 401
    return Response(generate_video_feed(cam_id), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/api/events")
def api_events():
    """Data endpoint to refresh the Web UI autonomously"""
    if not session.get("logged_in"): return "Unauthorized", 401
    return jsonify({
        "events": events, 
        "temp": env_sensors.get_temperature(), 
        'awake': time.time() < GLOBAL_AWAKE_UNTIL
    })
    
if __name__ == "__main__":
    # Ignite the AI orchestrator async thread to preserve the web loop
    t = threading.Thread(target=background_processing_loop, daemon=True)
    t.start()
    
    logger.info("Initializing Flask Multi-Camera Node Stream Server.")
    
    # Host 0.0.0.0 will naturally bridge Tailscale IPs (100.x.x.x) alongside wlan0/eth0 IPs.
    app.run(host="0.0.0.0", port=5000, threaded=True)
