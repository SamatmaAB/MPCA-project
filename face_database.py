import pickle
import os
import cv2
import numpy as np
from utils import DB_FILE, logger

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

class FaceDatabase:
    def __init__(self):
        self.encodings = []
        self.names = []
        self.load()

    def load(self):
        """Loads encodings from the pickle file efficiently."""
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, 'rb') as f:
                    data = pickle.load(f)
                    self.encodings = data.get("encodings", [])
                    self.names = data.get("names", [])
                logger.info(f"Loaded {len(self.names)} faces from database.")
            except Exception as e:
                logger.error(f"Error loading face database: {e}")
        else:
            logger.info("No existing face database found. Starting fresh.")

    def save(self):
        """Saves current encodings to the pickle file."""
        try:
            with open(DB_FILE, 'wb') as f:
                pickle.dump({"encodings": self.encodings, "names": self.names}, f)
            logger.info(f"Saved {len(self.names)} faces to database.")
        except Exception as e:
            logger.error(f"Error saving face database: {e}")

    def add_user(self, name, encoding):
        """Adds a new user to the internal state and saves to disk."""
        self.encodings.append(encoding)
        self.names.append(name)
        self.save()

# --- Utility to register a new user locally via WebCam ---
def get_face_encoding(rgb_frame):
    gray_frame = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2GRAY)
    faces = face_cascade.detectMultiScale(gray_frame, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
    
    if len(faces) == 0:
        return None, []
        
    if len(faces) > 1:
        return "multiple", []
        
    (x, y, w, h) = faces[0]
    
    # Ensure bounds are within image
    x, y = max(0, x), max(0, y)
    
    face_crop = gray_frame[y:y+h, x:x+w]
    if face_crop.size == 0:
        return None, []
        
    # Resize to a 100x100 standard
    face_resized = cv2.resize(face_crop, (100, 100))
    
    # L2 Normalize the flattened array for cosine similarity matching
    encoding = face_resized.flatten().astype(float)
    norm = np.linalg.norm(encoding)
    if norm > 0:
        encoding /= norm
    
    return [(y, x+w, y+h, x)], [encoding]

def register_new_user_cli():
    name = input("Enter the name of the new authorized user: ").strip()
    if not name:
        print("Name cannot be empty.")
        return

    print("Initializing camera... Please look at the camera.")
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Error: Could not open camera.")
        return
        
    db = FaceDatabase()
    
    registered = False
    print("Press 'c' to capture face, or 'q' to quit.")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        display_frame = frame.copy()
        cv2.putText(display_frame, "Press 'c' to Capture, 'q' to Quit", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
        cv2.imshow("Register User", display_frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('c'):
            # Process for face
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Using MediaPipe logic
            face_locations, encodings = get_face_encoding(rgb_frame)
            
            if face_locations == "multiple":
                print("Multiple faces detected! Please ensure only one person is in frame.")
            elif not face_locations or len(encodings) == 0:
                print("No face detected! Please try again.")
            else:
                db.add_user(name, encodings[0])
                print(f"Successfully registered user: {name}")
                registered = True
                break
                    
    cap.release()
    cv2.destroyAllWindows()
    
if __name__ == "__main__":
    register_new_user_cli()
