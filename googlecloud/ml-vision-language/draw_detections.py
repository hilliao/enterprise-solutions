"""Draw MediaPipe object detection results on a frame."""
import cv2
import numpy as np


# Label and box drawing parameters
LABEL_MARGIN = 10  # pixels
LABEL_ROW_HEIGHT = 10  # pixels
FONT_SIZE = 1
FONT_THICKNESS = 1
BOX_THICKNESS = 3
COLOR = (255, 0, 0)  # blue, because frames from OpenCV are BGR


def draw_detection_boxes(image, detection_result) -> np.ndarray:
    """Draws a bounding box, label and score for each detection on the image and returns it.
    Args:
      image: The frame to draw on, as read by OpenCV.
      detection_result: The list of all "Detection" entities to be drawn.
    Returns:
      Image with bounding boxes.
    """
    for detection in detection_result.detections:
        # Draw bounding_box
        box = detection.bounding_box
        top_left = box.origin_x, box.origin_y
        bottom_right = box.origin_x + box.width, box.origin_y + box.height
        cv2.rectangle(image, top_left, bottom_right, COLOR, BOX_THICKNESS)

        # Draw label and score
        category = detection.categories[0]
        score = round(category.score, 2)
        label = f"{category.category_name} ({score})"
        label_position = (LABEL_MARGIN + box.origin_x,
                          LABEL_MARGIN + LABEL_ROW_HEIGHT + box.origin_y)
        cv2.putText(image, label, label_position, cv2.FONT_HERSHEY_PLAIN,
                    FONT_SIZE, COLOR, FONT_THICKNESS)

    return image
