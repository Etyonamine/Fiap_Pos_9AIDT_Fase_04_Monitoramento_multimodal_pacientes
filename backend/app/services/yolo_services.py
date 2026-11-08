import math
import os
from pathlib import Path

MODEL_PATH = Path(os.environ.get("YOLO_MODEL_PATH", "models/yolov8n-pose.pt"))
DEFAULT_FENCE = {"enabled": True, "x": 0.1, "y": 0.1, "width": 0.8, "height": 0.9}
FISIO_FENCE = {"enabled": True, "x": 0.1, "y": 0.15, "width": 0.8, "height": 0.85}


def angle(a, b, c):
    u = (a[0] - b[0], a[1] - b[1])
    v = (c[0] - b[0], c[1] - b[1])
    length = math.hypot(*u) * math.hypot(*v)
    if length == 0:
        return None
    return round(math.degrees(math.acos(max(-1, min(1, (u[0]*v[0] + u[1]*v[1]) / length)))), 1)


def analyze_pose(result, width, height, mode):
    people = []
    if result.keypoints is None:
        return {"people": people}
    for box, points in zip(result.boxes.xyxy.tolist(), result.keypoints.data.tolist()):
        normalized = [[x / width, y / height, confidence] for x, y, confidence in points]
        knees = [
            angle(points[hip], points[knee], points[ankle])
            for hip, knee, ankle in ((11, 13, 15), (12, 14, 16))
            if all(points[index][2] >= 0.5 for index in (hip, knee, ankle))
        ]
        knees = [value for value in knees if value is not None]
        spine = None
        if all(points[index][2] >= 0.5 for index in (5, 6, 11, 12)):
            dx = (points[5][0] + points[6][0] - points[11][0] - points[12][0]) / 2
            dy = (points[5][1] + points[6][1] - points[11][1] - points[12][1]) / 2
            spine = round(math.degrees(math.atan2(abs(dx), abs(dy))), 1)
        knee = min(knees) if knees else None
        # These are screening heuristics, not a clinically validated diagnosis.
        anomalies = []
        if mode == "fisio" and spine is not None and spine > 35:
            anomalies.append({"kind": "Inclinação de tronco > 35°", "severity": "warning"})
        if mode == "fisio" and knee is not None and knee < 60:
            anomalies.append({"kind": "Flexão de joelho < 60°", "severity": "warning"})
        people.append({
            "box": [box[0]/width, box[1]/height, (box[2]-box[0])/width, (box[3]-box[1])/height],
            "keypoints": normalized, "knee_angle": knee, "spine_angle": spine,
            "anomalies": anomalies,
        })
    return {"people": people}


def frame_events(payload, fence):
    events = {(a["kind"], a["severity"]) for p in payload["people"] for a in p["anomalies"]}
    if fence["enabled"]:
        for person in payload["people"]:
            # Hip midpoint provides a stable bed boundary reference; do not use low-confidence poses.
            hips = [p for p in person["keypoints"][11:13] if p[2] >= 0.5]
            if not hips:
                continue
            x, y = (sum(p[i] for p in hips) / len(hips) for i in (0, 1))
            if not (fence["x"] <= x <= fence["x"] + fence["width"]
                    and fence["y"] <= y <= fence["y"] + fence["height"]):
                events.add(("Saída da cerca virtual", "critical"))
    return sorted(events)