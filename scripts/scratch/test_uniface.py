import uniface
from uniface import SCRFD
import numpy as np

# Create a dummy image
img = np.zeros((320, 320, 3), dtype=np.uint8)
detector = SCRFD()
faces = detector.detect(img)
print("Detected faces:", len(faces))
if faces:
    print("Landmarks shape:", faces[0].landmarks.shape)
