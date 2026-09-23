import cv2
import time

# --------------------------------------------------
# AprilTag setup
# --------------------------------------------------

# Change this if your tags use a different family.
# Common options:
# DICT_APRILTAG_16h5
# DICT_APRILTAG_25h9
# DICT_APRILTAG_36h10
# DICT_APRILTAG_36h11

dictionary = cv2.aruco.getPredefinedDictionary(
    cv2.aruco.DICT_APRILTAG_36h11
)

detector_params = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(dictionary, detector_params)

# --------------------------------------------------
# Webcam
# --------------------------------------------------

cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)

if not cap.isOpened():
    print("ERROR: Could not open webcam.")
    exit()

print("AprilTag tracker running.")
print("Press Q to quit.")

previous_time = time.time()

while True:
    ret, frame = cap.read()

    if not ret:
        print("Failed to capture frame.")
        break

    # AprilTag detection works on grayscale images
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    corners, ids, rejected = detector.detectMarkers(gray)

    # --------------------------------------------------
    # Draw detected tags
    # --------------------------------------------------

    if ids is not None:

        # Draw tag outlines
        cv2.aruco.drawDetectedMarkers(frame, corners, ids)

        for tag_corners, tag_id in zip(corners, ids.flatten()):

            points = tag_corners.reshape((4, 2))

            # Center of tag
            center_x = int(points[:, 0].mean())
            center_y = int(points[:, 1].mean())

            # Draw center point
            cv2.circle(
                frame,
                (center_x, center_y),
                6,
                (0, 0, 255),
                -1
            )

            # Display ID and pixel coordinates
            text = f"ID {tag_id} ({center_x}, {center_y})"

            cv2.putText(
                frame,
                text,
                (center_x + 10, center_y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2
            )

        # Number of currently visible tags
        cv2.putText(
            frame,
            f"Tags: {len(ids)}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

    else:

        cv2.putText(
            frame,
            "No tags detected",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2
        )

    # --------------------------------------------------
    # FPS counter
    # --------------------------------------------------

    current_time = time.time()

    fps = 1 / (current_time - previous_time)
    previous_time = current_time

    cv2.putText(
        frame,
        f"FPS: {fps:.1f}",
        (10, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 0),
        2
    )

    # --------------------------------------------------
    # Display
    # --------------------------------------------------

    cv2.imshow("AprilTag Live Tracker", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break


cap.release()
cv2.destroyAllWindows()



# import cv2

# CAMERA_INDEX = 1

# cap = cv2.VideoCapture(CAMERA_INDEX)

# if not cap.isOpened():
#     print("Could not open Camo camera")
#     raise SystemExit

# while True:
#     ret, frame = cap.read()
#     if not ret:
#         print("Failed to read frame")
#         break

#     cv2.imshow("Camo / iPhone", frame)

#     if cv2.waitKey(1) & 0xFF == ord("q"):
#         break

# cap.release()
cv2.destroyAllWindows()