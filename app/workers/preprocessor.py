"""
app/workers/preprocessor.py
High-performance OpenCV pipeline to normalize noisy, low-light, or skewed Kirana bill photos.
"""
import logging
from typing import Tuple
import cv2
import numpy as np

logger = logging.getLogger(__name__)


def decode_image_bytes(image_bytes: bytes) -> np.ndarray:
    """Decodes raw image bytes into a BGR OpenCV NumPy array."""
    np_arr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Failed to decode image bytes: input data is corrupted or unsupported format.")
    return image


def compute_skew_angle(image: np.ndarray) -> float:
    """
    Estimates the skew angle (in degrees) of a document image using Canny edges and Hough lines.
    Returns 0.0 if no dominant text orientation is found.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=10)

    if lines is None or len(lines) == 0:
        return 0.0

    angles = []
    for line in lines:
        pts = line.reshape(-1)
        if len(pts) >= 4:
            x1, y1, x2, y2 = float(pts[0]), float(pts[1]), float(pts[2]), float(pts[3])
            angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            # Keep horizontal-ish lines within +/- 45 degrees
            if -45.0 <= angle <= 45.0:
                angles.append(angle)

    if not angles:
        return 0.0

    median_angle = float(np.median(angles))
    # Threshold tiny skews to avoid unnecessary interpolation artifacts
    if abs(median_angle) < 0.5:
        return 0.0
    return median_angle


def rotate_image(image: np.ndarray, angle: float) -> np.ndarray:
    """Rotates an image around its center by a specified angle in degrees with white border fill."""
    if abs(angle) < 0.1:
        return image

    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)

    rot_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = np.abs(rot_matrix[0, 0])
    sin = np.abs(rot_matrix[0, 1])

    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))

    rot_matrix[0, 2] += (new_w / 2) - center[0]
    rot_matrix[1, 2] += (new_h / 2) - center[1]

    rotated = cv2.warpAffine(
        image,
        rot_matrix,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return rotated


def preprocess_bill_image(
    image_bytes: bytes,
    enable_deskew: bool = True,
    apply_clahe: bool = True,
    apply_bilateral: bool = False,
    max_dimension: int = 1600,
    output_jpeg_quality: int = 85,
) -> bytes:
    """
    Executes high-speed vision enhancement pipeline:
    1. Decodes image bytes.
    2. Downscales high-resolution camera photos (e.g. 12MP/48MP) to 1600px max dimension (<20ms).
    3. Fast auto-deskew if noticeable skew (>1.0 deg).
    4. Grayscale conversion + CLAHE for harsh lighting/shadows.
    5. Re-encodes enhanced image to lightweight JPEG bytes for fast AI inference.
    """
    try:
        img = decode_image_bytes(image_bytes)

        # Fast downscale if photo is huge (e.g. 4000x3000 from mobile camera)
        h, w = img.shape[:2]
        if max(h, w) > max_dimension:
            scale = max_dimension / float(max(h, w))
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        # 1. Deskew only if noticeable skew (> 1.0 degree)
        if enable_deskew:
            angle = compute_skew_angle(img)
            if abs(angle) > 1.0:
                logger.debug("Deskewing bill image by %.2f degrees", angle)
                img = rotate_image(img, angle)

        # 2. Convert to Grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 3. Bilateral Filtering (only if explicitly enabled, skipped by default for speed)
        if apply_bilateral:
            gray = cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)

        # 4. CLAHE for localized illumination balancing
        if apply_clahe:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)

        # 5. Encode to JPEG
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), output_jpeg_quality]
        success, encoded_img = cv2.imencode(".jpg", gray, encode_params)
        if not success:
            return image_bytes

        return encoded_img.tobytes()
    except Exception as e:
        logger.warning(f"Image preprocessing warning: {e}. Falling back to raw bytes.")
        return image_bytes
