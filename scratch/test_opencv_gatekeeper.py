"""
scratch/test_opencv_gatekeeper.py
Analyze OpenCV features (saturation, edge density, horizontal lines) for zero-LLM filtering.
"""
import sys
from pathlib import Path
import cv2
import numpy as np

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Real bill
bill_path = Path("tests/fixtures/bills/sample_bill_SBT_2026_081.jpg")
bill_img = cv2.imread(str(bill_path))

# Dummy meme
meme = np.zeros((400, 400, 3), dtype=np.uint8)
meme[:] = (240, 200, 150)
cv2.circle(meme, (200, 200), 100, (0, 255, 255), -1)
cv2.putText(meme, "GOOD MORNING!", (60, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (50, 50, 200), 3)

def analyze_image_cv(img, label):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    mean_sat = float(saturation.mean())
    std_sat = float(saturation.std())

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = float(np.count_nonzero(edges) / (edges.shape[0] * edges.shape[1]))

    # Horizontal lines
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 1))
    morph = cv2.morphologyEx(edges, cv2.MORPH_OPEN, kernel)
    horiz_line_pixels = int(np.count_nonzero(morph))

    print(f"[{label}]")
    print(f"  Mean Saturation: {mean_sat:.2f} (Paper bills usually < 45, colorful images > 60)")
    print(f"  Edge Density:    {edge_density:.4f}")
    print(f"  Horizontal line pixels: {horiz_line_pixels}")

analyze_image_cv(bill_img, "REAL BILL")
analyze_image_cv(meme, "MEME IMAGE")
