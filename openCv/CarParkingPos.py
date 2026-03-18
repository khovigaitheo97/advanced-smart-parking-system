import cv2
import urllib.request
import numpy as np
import pickle

# ====== SAME AS run.py ======
url = "http://172.20.10.6/stream"
stream = urllib.request.urlopen(url)
#Clicked at: x=333, y=457 (539,457) (539,218)
width, height = 120, 90 # size of ROI
width_img, height_img = 640, 480 #resize image
MIRROR_FLIP = 0

try:
    with open("CarParkingPos", "rb") as f:
        posList = pickle.load(f)
except:
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

    with open("CarParkingPos", "wb") as f:
        pickle.dump(posList, f)

def read_mjpeg_frame(stream, buffer):
    buffer += stream.read(1024)
    a = buffer.find(b'\xff\xd8')
    b = buffer.find(b'\xff\xd9')
    if a != -1 and b != -1 and b > a:
        jpg = buffer[a:b+2]
        buffer = buffer[b+2:]
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), -1)
        return img, buffer
    return None, buffer

buffer = b""
cv2.namedWindow("Image")
cv2.setMouseCallback("Image", mouseClick)

while True:
    img, buffer = read_mjpeg_frame(stream, buffer)
    if img is None:
        continue

    if MIRROR_FLIP is not None:
        img = cv2.flip(img, MIRROR_FLIP)

    img = cv2.resize(img, (width_img, height_img))

    for pos in posList:
        cv2.rectangle(img, pos, (pos[0] + width, pos[1] + height), (255, 0, 255), 2)

    cv2.imshow("Image", img)

    key = cv2.waitKey(1)
    if key == ord('q'): #ord used for convert character to ASCII
        break

cv2.destroyAllWindows()