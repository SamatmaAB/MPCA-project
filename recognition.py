import cv2
import numpy as np
from utils import logger
from face_database import FaceDatabase

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

class FaceRecognizer:
    def __init__(self, tolerance=0.75):
        """
        tolerance: In this context using cosine similarity, we need a similarity threshold.
        Higher is a tighter match. We use 0.75 as a generic testing threshold for PC.
        """
        self.db = FaceDatabase()
        self.similarity_threshold = tolerance
        
    def check_faces(self, rgb_small_frame):
        """
        Takes an RGB, scaled-down frame.
        Returns a list of tuples: (face_location, Name, Is_Authorized)
        """
        if not self.db.encodings:
            return []

        gray_frame = cv2.cvtColor(rgb_small_frame, cv2.COLOR_RGB2GRAY)
        faces = face_cascade.detectMultiScale(gray_frame, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        if len(faces) == 0:
            return []

        face_results = []
        
        for (x, y, w, h) in faces:
            x, y = max(0, x), max(0, y)
            
            face_crop = gray_frame[y:y+h, x:x+w]
            if face_crop.size == 0:
                continue
                
            # Convert to grayscale and resize to 100x100
            face_resized = cv2.resize(face_crop, (100, 100))
            
            # L2 Normalize
            encoding = face_resized.flatten().astype(float)
            norm = np.linalg.norm(encoding)
            if norm == 0:
                continue
            encoding /= norm
            
            face_location = (y, x+w, y+h, x) # (top, right, bottom, left)
            name = "Unknown"
            is_authorized = False

            # Cosine similarity matching
            best_score = -1
            best_match_index = -1
            
            for i, known_encoding in enumerate(self.db.encodings):
                score = np.dot(known_encoding, encoding)
                if score > best_score:
                    best_score = score
                    best_match_index = i
                    
            if best_score >= self.similarity_threshold:
                name = self.db.names[best_match_index]
                is_authorized = True

            face_results.append((face_location, name, is_authorized))
            
        return face_results
