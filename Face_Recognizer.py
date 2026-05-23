# --------------------------
# Facial Emotion Recognition
# --------------------------

import cv2
import numpy as np
import os
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Conv2D, MaxPooling2D, Flatten, Dense, Dropout
from tensorflow.keras.preprocessing.image import ImageDataGenerator

# --------------------------
# 1. Load Haar Cascade Classifier (Face Detector)
# --------------------------
cascade_path = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
face_classifier = cv2.CascadeClassifier(cascade_path)

if face_classifier.empty():
    raise IOError("Failed to load Haar Cascade XML file. Check your OpenCV installation.")

# --------------------------
# 2. Define Emotion Labels
# --------------------------
emotion_labels = ['Angry', 'Disgust', 'Fear', 'Happy', 'Sad', 'Surprise', 'Neutral']

# --------------------------
# 3. Build the CNN Model
# --------------------------
def build_model():
    model = Sequential([
        Conv2D(32, (3, 3), activation='relu', input_shape=(48, 48, 1)),
        MaxPooling2D(2, 2),
        Conv2D(64, (3, 3), activation='relu'),
        MaxPooling2D(2, 2),
        Conv2D(128, (3, 3), activation='relu'),
        Flatten(),
        Dense(128, activation='relu'),
        Dropout(0.5),
        Dense(7, activation='softmax')
    ])
    model.compile(optimizer='adam', loss='categorical_crossentropy', metrics=['accuracy'])
    return model

model = build_model()

# --------------------------
# 4. Load Pretrained Model (Optional)
# --------------------------
# --------------------------
# 4. Load Pretrained Model
# --------------------------
from tensorflow.keras.models import load_model
model = load_model('emotion_model.h5')
print("[INFO] Loaded trained emotion model successfully.")


# --------------------------
# 5. Real-Time Emotion Detection
# --------------------------
cap = cv2.VideoCapture(0)

print("\n[INFO] Starting real-time facial emotion recognition...")
print("Press 'q' to quit the camera window.\n")

while True:
    ret, frame = cap.read()
    if not ret:
        print("[ERROR] Failed to grab frame from camera.")
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_classifier.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)

    for (x, y, w, h) in faces:
        roi_gray = gray[y:y + h, x:x + w]
        roi_gray = cv2.resize(roi_gray, (48, 48))
        roi = roi_gray.astype('float') / 255.0
        roi = np.expand_dims(roi, axis=0)
        roi = np.expand_dims(roi, axis=-1)

        # Predict emotion
        prediction = model.predict(roi, verbose=0)[0]
        emotion = emotion_labels[np.argmax(prediction)]

        # Draw on frame
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
        cv2.putText(frame, emotion, (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2, cv2.LINE_AA)

    cv2.imshow('Facial Emotion Recognition', frame)

    # Exit loop on 'q' key
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# --------------------------
# 6. Cleanup
# --------------------------
cap.release()
cv2.destroyAllWindows()
print("\n[INFO] Program closed successfully.")
