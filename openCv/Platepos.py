import cv2
import urllib.request
import numpy as np
import pickle

# ===== CAMERA STREAM =====
STREAM_URL = "http://172.20.10.5/stream"

# ===== ROI SIZE =====
W1, H1 = 110, 80   # ROI1 (IN)
W2, H2 = 315, 210  # ROI2 (OUT)

# ===== IMAGE SIZE =====
width_img, height_img = 640, 480

# ===== SAVE FILE =====
PICKLE_NAME = "PlatePos"

WIN = "Plate ROI Picker (STREAM)"

# ================= LOAD ROI =================
# Always keep 2 slots: [ROI1, ROI2] where each is (x,y,w,h) or None
posList = [None, None]

try:
    with open(PICKLE_NAME, "rb") as f:
        loaded = pickle.load(f)

        # Old format: [(x,y), (x,y)] -> convert to (x,y,w,h)
        if isinstance(loaded, list) and len(loaded) > 0 and len(loaded[0]) == 2:
            for i, (x, y) in enumerate(loaded[:2]):
                if i == 0:
                    posList[0] = (x, y, W1, H1)
                else:
                    posList[1] = (x, y, W2, H2)

        # New-ish list format could be [(x,y,w,h), (x,y,w,h)]
        elif isinstance(loaded, list):
            if len(loaded) >= 1 and isinstance(loaded[0], tuple) and len(loaded[0]) == 4:
                posList[0] = loaded[0]
            if len(loaded) >= 2 and isinstance(loaded[1], tuple) and len(loaded[1]) == 4:
                posList[1] = loaded[1]

except:
    pass


def save():
    with open(PICKLE_NAME, "wb") as f:
        pickle.dump(posList, f)


def inside_roi(x, y, roi):
    rx, ry, rw, rh = roi
    return (rx <= x <= rx + rw) and (ry <= y <= ry + rh)


# ================= MOUSE =================
def mouseClick(event, x, y, flags, params):
    global posList

    if event == cv2.EVENT_LBUTTONDOWN:
        # Priority: fill ROI1 first, then ROI2, else update ROI1
        if posList[0] is None:
            roi = (x, y, W1, H1)
            posList[0] = roi
            print("Saved ROI1 (IN):", roi)

        elif posList[1] is None:
            roi = (x, y, W2, H2)
            posList[1] = roi
            print("Saved ROI2 (OUT):", roi)

        else:
            # If both exist, update ROI1 by default
            roi = (x, y, W1, H1)
            posList[0] = roi
            print("Updated ROI1 (IN):", roi)

        save()

    elif event == cv2.EVENT_RBUTTONDOWN:
        # Remove ROI without shifting indexes: set slot to None
        if posList[0] is not None and inside_roi(x, y, posList[0]):
            print("Removed ROI1 (IN):", posList[0])
            posList[0] = None
            save()
            return

        if posList[1] is not None and inside_roi(x, y, posList[1]):
            print("Removed ROI2 (OUT):", posList[1])
            posList[1] = None
            save()
            return


# ================= STREAM =================
stream = urllib.request.urlopen(STREAM_URL)
buffer = b""

cv2.namedWindow(WIN)
cv2.setMouseCallback(WIN, mouseClick)

print("Left click = set ROI (ROI1 -> ROI2) | Right click = remove ROI (no shifting) | Press q to quit")

while True:
    buffer += stream.read(4096)

    a = buffer.find(b'\xff\xd8')
    b = buffer.find(b'\xff\xd9')

    if a != -1 and b != -1 and b > a:
        jpg = buffer[a:b + 2]
        buffer = buffer[b + 2:]

        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), -1)
        if img is None:
            continue

        img = cv2.flip(img, 1)  # mirror like your OCR code
        img = cv2.resize(img, (width_img, height_img))

        # ===== DRAW ROI =====
        if posList[0] is not None:
            x1, y1, w1, h1 = posList[0]
            cv2.rectangle(img, (x1, y1), (x1 + w1, y1 + h1), (255, 0, 255), 2)
            cv2.putText(img, "ROI1 (IN)", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

        if posList[1] is not None:
            x2, y2, w2, h2 = posList[1]
            cv2.rectangle(img, (x2, y2), (x2 + w2, y2 + h2), (0, 255, 255), 2)
            cv2.putText(img, "ROI2 (OUT)", (x2, y2 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        cv2.putText(img,
                    "Left: set ROI1->ROI2 | Right: remove (no shift) | q: quit",
                    (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2)

        cv2.imshow(WIN, img)

    if cv2.waitKey(1) == ord('q'):
        break

cv2.destroyAllWindows()