import cv2
import urllib.request
import numpy as np
import pickle
import cvzone
import requests
import time
import threading
import pytesseract
import re
import csv
from datetime import datetime
from flask import Flask, Response

# ===================== CONFIG =====================
ESP32_IP = "172.20.10.4"

PARK_URL = "http://172.20.10.6/stream"
PLATE_URL = "http://172.20.10.5/stream"

PARK_POS_FILE = "CarParkingPos"
PLATE_POS_FILE = "PlatePos"

TIMEOUT = 3.0
SEND_KEEPALIVE_SEC = 2.0

ESP32_PLATE_PATH = "/plate"
HTTP_TIMEOUT = 0.8
SEND_ONLY_ON_CHANGE = False
MIN_SEND_INTERVAL = 0.4

CSV_FILE = "parking_log.csv"
DUP_EVENT_SEC = 2.0

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ===================== IMAGE SETTINGS =====================
width_img, height_img = 640, 480
width, height = 130, 100
width_map, height_map = 90, 110

ROI1_W, ROI1_H = 110, 70
ROI2_W, ROI2_H = 190, 95

FLIP_PLATE = 1

# ===================== SYSTEM DATA =====================
ALLOWED_PLATES = {"A6", "V3", "C1"}

ENTRY_POINT = (333, 457)
MAP_ENTRY_POINT = (137, 246)

mapPosList = [
    (206, 290),
    (308, 290),
    (411, 290),
    (202, 91),
    (307, 91),
    (410, 91)
]

# ===================== WEB =====================
app = Flask(__name__)
latest_frame = None
frame_lock = threading.Lock()

# ===================== MJPEG STREAM =====================
class MJPEGStream:
    def __init__(self, url, read_size=4096):
        self.url = url
        self.read_size = read_size
        self._buf = b""
        self._frame = None
        self._lock = threading.Lock()
        self._stop = False
        self._t = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._t.start()
        return self

    def stop(self):
        self._stop = True

    def get_frame(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def _run(self):
        while not self._stop:
            try:
                stream = urllib.request.urlopen(self.url, timeout=5)
                self._buf = b""
                while not self._stop:
                    self._buf += stream.read(self.read_size)
                    a = self._buf.find(b"\xff\xd8")
                    b = self._buf.find(b"\xff\xd9")

                    if a == -1 or b == -1 or b <= a:
                        continue

                    jpg = self._buf[a:b + 2]
                    self._buf = self._buf[b + 2:]

                    img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                    if img is None:
                        continue

                    with self._lock:
                        self._frame = img
            except:
                time.sleep(0.5)

# ===================== LOAD ROI =====================
with open(PARK_POS_FILE, "rb") as f:
    park_posList = pickle.load(f)

with open(PLATE_POS_FILE, "rb") as f:
    plate_posList = pickle.load(f)

px1, py1, w1, h1 = (*plate_posList[-2], ROI1_W, ROI1_H) if len(plate_posList[-2]) == 2 else plate_posList[-2]
px2, py2, w2, h2 = (*plate_posList[-1], ROI2_W, ROI2_H) if len(plate_posList[-1]) == 2 else plate_posList[-1]

# ===================== PARKING =====================
def checkParkingSpace(imgPro):
    freeSpace = 0
    condition = 200
    m = 6
    spotInfo = []

    for i, (x, y) in enumerate(park_posList[:6]):
        spotID = i + 1
        imgCrop = imgPro[y+m:y+height-m, x+m:x+width-m]
        count = cv2.countNonZero(imgCrop)

        status = "free" if count <= condition else "occupied"
        if status == "free":
            freeSpace += 1

        spotInfo.append((spotID, x, y, count, status))

    return freeSpace, spotInfo

def getNearestFreeSpot(spotInfo, entryPoint):
    ex, ey = entryPoint
    nearest, minDist = None, float("inf")

    for (spotID, x, y, _, status) in spotInfo:
        if status != "free":
            continue

        cx, cy = x + width//2, y + height//2
        dist = (cx - ex)**2 + (cy - ey)**2

        if dist < minDist:
            minDist = dist
            nearest = (spotID, x, y, cx, cy)

    return nearest

def mapNearestSpotInfo(nearest):
    if nearest is None:
        return None
    spotID = nearest[0]
    return (spotID, *mapPosList[spotID - 1])

# ===================== ESP32 =====================
def send_led_bulk(s6):
    try:
        r = requests.get(f"http://{ESP32_IP}/led", params={"s": s6}, timeout=TIMEOUT)
        return True
    except:
        return False

def send_msg(spotID, status):
    try:
        requests.get(f"http://{ESP32_IP}/msg",
                     params={"spot": spotID, "status": status},
                     timeout=TIMEOUT)
        return True
    except:
        return False

# ===================== OCR =====================
def preprocess_for_ocr(roi):
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=5, fy=5)
    gray = cv2.GaussianBlur(gray, (3,3), 0)

    thr = cv2.threshold(gray, 0, 255,
                        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN,
                           cv2.getStructuringElement(cv2.MORPH_RECT,(3,3)))

    return cv2.bitwise_not(thr), thr

def fix_plate(letter, digit):
    letter = re.sub(r'[^A-Z]', '', letter.upper())[:1]
    digit  = re.sub(r'[^0-9]', '', digit)[:1]

    return letter + digit if letter and digit else ""

def ocr_plate(frame, x, y, w, h):
    roi = frame[y:y+h, x:x+w]
    if roi.size == 0:
        return "", None

    img, thr = preprocess_for_ocr(roi)

    left = img[:, :img.shape[1]//2]
    right = img[:, img.shape[1]//2:]

    letter = pytesseract.image_to_string(left, config="--psm 10")
    digit  = pytesseract.image_to_string(right, config="--psm 10")

    return fix_plate(letter, digit), thr

# ===================== LOGGING =====================
car_in_time = {}
last_event = {}

def handle_plate_in(p):
    if p not in car_in_time:
        car_in_time[p] = time.time()

def handle_plate_out(p):
    if p in car_in_time:
        duration = time.time() - car_in_time[p]

        with open(CSV_FILE, "a", newline="") as f:
            csv.writer(f).writerow([p, duration])

        del car_in_time[p]

# ===================== WEB STREAM =====================
def mjpeg_generator():
    global latest_frame
    while True:
        with frame_lock:
            frame = None if latest_frame is None else latest_frame.copy()

        if frame is None:
            time.sleep(0.03)
            continue

        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' +
               buffer.tobytes() + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(mjpeg_generator(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

def run_web():
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

# ===================== START =====================
baseMap = cv2.imread("parking_map.jpg")

threading.Thread(target=run_web, daemon=True).start()

park_stream = MJPEGStream(PARK_URL, 1024).start()
plate_stream = MJPEGStream(PLATE_URL, 4096).start()

last_led_s = None
last_time = 0

# ===================== MAIN LOOP =====================
while True:
    park_frame = park_stream.get_frame()
    if park_frame is not None:
        img = cv2.resize(cv2.flip(park_frame, 0), (width_img, height_img))

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (3,3), 1)

        thr = cv2.adaptiveThreshold(
            blur,255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            25,16
        )

        imgPro = cv2.medianBlur(thr, 5)

        free, spotInfo = checkParkingSpace(imgPro)

        s6 = "".join("1" if s=="free" else "0" for *_, s in spotInfo)

        now = time.time()
        if s6 != last_led_s or now - last_time > SEND_KEEPALIVE_SEC:
            if send_led_bulk(s6):
                last_led_s = s6
                last_time = now

        cv2.imshow("Parking", img)

    plate_frame = plate_stream.get_frame()
    if plate_frame is not None:
        frame = cv2.flip(plate_frame, FLIP_PLATE)

        num1, _ = ocr_plate(frame, px1, py1, w1, h1)
        num2, _ = ocr_plate(frame, px2, py2, w2, h2)

        number = num1 or num2

        if number:
            requests.get(f"http://{ESP32_IP}/plate", params={"n": number})
        else:
            requests.get(f"http://{ESP32_IP}/plate", params={"n": "NONE"})

        cv2.imshow("Plate", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cv2.destroyAllWindows()