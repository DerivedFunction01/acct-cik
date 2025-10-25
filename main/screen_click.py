import importlib
import pyautogui
import random
import time
import cv2
import numpy as np

# Settings
min_delay = 60        # minimum delay between clicks
max_delay = 60 * 10        # maximum delay between clicks

# Take a screenshot to show your screen
screenshot = pyautogui.screenshot()
img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
clone = img.copy()

# Variables for selecting region
ref_point = []
cropping = False

def click_and_crop(event, x, y, flags, param):
    global ref_point, cropping, img

    if event == cv2.EVENT_LBUTTONDOWN:
        ref_point = [(x, y)]
        cropping = True

    elif event == cv2.EVENT_LBUTTONUP:
        ref_point.append((x, y))
        cropping = False
        cv2.rectangle(img, ref_point[0], ref_point[1], (0, 255, 0), 2)
        cv2.imshow("Select Area", img)

# Show the screen for selecting area
cv2.namedWindow("Select Area")
cv2.setMouseCallback("Select Area", click_and_crop)

while True:
    cv2.imshow("Select Area", img)
    key = cv2.waitKey(1) & 0xFF

    # Reset selection
    if key == ord("r"):
        img = clone.copy()
        ref_point = []

    # Confirm selection
    elif key == ord("c"):
        break

    # Exit without selecting
    elif key == 27:  # ESC key
        cv2.destroyAllWindows()
        exit()

cv2.destroyAllWindows()

if len(ref_point) != 2:
    print("No area selected. Exiting.")
    exit()

# Normalize coordinates
x1, y1 = ref_point[0]
x2, y2 = ref_point[1]
bounds = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

print(f"Selected area: {bounds}")
print("Starting random autoclicker... Press Ctrl+C to stop.")

start_time = time.time()

try:
    while True:
        x = random.randint(bounds[0], bounds[2])
        y = random.randint(bounds[1], bounds[3])

        pyautogui.moveTo(x, y, duration=random.uniform(0.1, 0.5))
        pyautogui.click()

        time.sleep(random.uniform(min_delay, max_delay))

except KeyboardInterrupt:
    print("\nStopped by user.")
