import cv2
import numpy as np
import pickle
import os

IMAGE_PATH = os.path.join(os.path.dirname(__file__), "parking_map.jpg")

width, height = 90, 110
width_img, height_img = 640, 480
MIRROR_FLIP = 0

posList = []

def mouseClick(event, x, y, flags, params):
    global posList
    if event == cv2.EVENT_LBUTTONDOWN:
        posList.append((x, y))
        print(f"Clicked at: x={x}, y={y}")
    elif event == cv2.EVENT_RBUTTONDOWN:
        for i, (x1, y1) in enumerate(posList):
            if x1 <= x <= x1 + width and y1 <= y <= y1 + height:
                print(f"Removed at: x={x}, y={y}")
                posList.pop(i)
                break

print("IMAGE_PATH =", IMAGE_PATH)
print("File exists =", os.path.exists(IMAGE_PATH))

baseImg = cv2.imread(IMAGE_PATH)

if baseImg is None:
    print("Cannot open image:", IMAGE_PATH)
    exit()

if MIRROR_FLIP is not None:
    baseImg = cv2.flip(baseImg, MIRROR_FLIP)

#baseImg = cv2.resize(baseImg, (width_img, height_img))

cv2.namedWindow("Image")
cv2.setMouseCallback("Image", mouseClick)

while True:
    img = baseImg.copy()

    for pos in posList:
        cv2.rectangle(img, pos, (pos[0] + width, pos[1] + height), (255, 0, 255), 2)

    cv2.imshow("Image", img)

    key = cv2.waitKey(1)
    if key == ord('q'):
        break

cv2.destroyAllWindows()