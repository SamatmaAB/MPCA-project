import cv2
import time
from utils import logger
from recognition import FaceRecognizer
from gpio_control import AccessController, RegistrationButton
from face_database import get_face_encoding

# --- Configuration ---
# Optimization: Resize frame to 1/SCALE_FACTOR before processing
SCALE_FACTOR = 4 
# Optimization: Skip frames to save CPU load
PROCESS_EVERY_N_FRAMES = 3 

# Temporal Stability Config
CONSECUTIVE_FRAMES_REQUIRED = 3 

def main():
    logger.info("Starting Face Recognition Access Control System...")
    
    # Initialize components
    recognizer = FaceRecognizer(tolerance=0.75)
    access_controller = AccessController()
    
    # Registration Button Setup
    registration_requested = False
    def on_reg_pressed():
        nonlocal registration_requested
        registration_requested = True
        logger.info("[HARDWARE] Registration Button Pressed!")

    reg_button = RegistrationButton(pin=22, callback=on_reg_pressed)
    
    # Check if there are any users in the DB
    if not recognizer.db.names:
        logger.warning(
            "No users found in database! Please run `python face_database.py` first "
            "to register at least one user before starting the system."
        )

    # Try to open webcam
    video_capture = cv2.VideoCapture(0)
    if not video_capture.isOpened():
        logger.error("Failed to open webcam. Please check the connection.")
        return
        
    # We optionally lower resolution at hardware level if possible
    # video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    # video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    frame_count = 0
    
    # Temporal buffer
    # True = Authorized face seen, False = Unrecognized face seen
    recent_recognitions = []
    
    # Cached results to draw bounding boxes accurately during skipped frames
    cached_face_results = []
    
    # Timer for Intruder alarm (2.5 continuous seconds)
    unrecognized_face_start_time = None

    logger.info("System ready. Capturing video...")

    try:
        while True:
            # 1. Capture frame
            ret, frame = video_capture.read()
            if not ret:
                logger.error("Failed to grab frame. Camera disconnected?")
                break
                
            frame_count += 1
            
            # Flip frame horizontally for easier viewing (mirror effect)
            frame = cv2.flip(frame, 1)

            # --- Hardware Registration Logic ---
            if registration_requested:
                registration_requested = False
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                locs, encodings = get_face_encoding(rgb_frame)
                
                if locs == "multiple":
                    logger.warning("[REGISTRATION] Failed: Multiple faces seen.")
                elif not locs or len(encodings) == 0:
                    logger.warning("[REGISTRATION] Failed: No face detected.")
                else:
                    new_name = f"User_{int(time.time())}"
                    recognizer.db.add_user(new_name, encodings[0])
                    logger.info(f">>> NEW USER SAVED: {new_name} <<<")
                    
                    # Optionally Buzz lightly to indicate success
                    if access_controller.buzzer:
                        import threading
                        threading.Thread(target=access_controller._trigger_device, args=(access_controller.buzzer, 0.2, "SUCCESS_BUZZ"), daemon=True).start()

            # 2. Performance Optimization: Only process every N frames
            if frame_count % PROCESS_EVERY_N_FRAMES == 0:
                
                # Resize frame for faster face detection
                small_frame = cv2.resize(frame, (0, 0), fx=(1/SCALE_FACTOR), fy=(1/SCALE_FACTOR))
                rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                
                # 3. Detect and Recognize
                # Returns: [(face_location, name, is_authorized), ...]
                cached_face_results = recognizer.check_faces(rgb_small_frame)
                
                # 4. Decision Logic
                if len(cached_face_results) > 0:
                    # Check if ANY of the detected faces are authorized
                    frame_authorized = any([is_auth for (_, _, is_auth) in cached_face_results])
                    
                    if frame_authorized:
                        unrecognized_face_start_time = None # Reset intruder timer
                        recent_recognitions.append(True)
                    else:
                        recent_recognitions.append(False)
                        logger.debug("Unknown face(s) detected.")
                        # Start timer if not already started
                        if unrecognized_face_start_time is None:
                            unrecognized_face_start_time = time.time()
                else:
                    # No faces detected. Reset intruder timer.
                    unrecognized_face_start_time = None
                    pass
                    
                # Ensure buffer doesn't grow indefinitely
                if len(recent_recognitions) > CONSECUTIVE_FRAMES_REQUIRED:
                    recent_recognitions.pop(0)
                    
                # 5. Evaluate Temporal Buffer explicitly (Quick Unlock)
                if len(recent_recognitions) == CONSECUTIVE_FRAMES_REQUIRED:
                    # If all recent frames match an authorized user == APPROVE
                    if all(recent_recognitions):
                        access_controller.approve_access()
                        # Reset buffer after decision
                        recent_recognitions.clear()
                
                # 6. Evaluate Time-based Intruder Alarm (2.5 continuous seconds)
                if unrecognized_face_start_time is not None:
                    if time.time() - unrecognized_face_start_time >= 2.5:
                        access_controller.reject_access()
                        # Reset timer and buffer after triggering alarm
                        unrecognized_face_start_time = None
                        recent_recognitions.clear()
            
            # --- Draw results on screen (Demo purposes) ---
            # Even if we skip processing the current frame, we draw the cached boxes
            for (top, right, bottom, left), name, is_auth in cached_face_results:
                # Scale back up face locations since the frame we detected in was scaled down
                top *= SCALE_FACTOR
                right *= SCALE_FACTOR
                bottom *= SCALE_FACTOR
                left *= SCALE_FACTOR

                color = (0, 255, 0) if is_auth else (0, 0, 255)
                
                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
                cv2.putText(frame, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
            # Render cooling down UI state
            if access_controller.is_cooling_down:
                cv2.putText(frame, "COOLDOWN ACTIVE", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)

            # Show the resulting image
            cv2.imshow('Antitheft Security Monitor', frame)

            # Hit 'q' on the keyboard to quit!
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                logger.info("Termination requested by user (q key).")
                break
            # Hit 'r' on keyboard to simulate physical registration button 
            elif key == ord('r'):
                reg_button.trigger_mock()

    except KeyboardInterrupt:
        logger.info("Termination requested by user (Ctrl+C).")
    except Exception as e:
        logger.exception("Unexpected error in main loop")
    finally:
        # Release handle to the webcam
        video_capture.release()
        cv2.destroyAllWindows()
        logger.info("System shutting down gracefully.")

if __name__ == '__main__':
    main()
