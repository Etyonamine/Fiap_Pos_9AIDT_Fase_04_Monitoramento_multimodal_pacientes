import math
import os
from pathlib import Path

MODEL_PATH = Path(os.environ.get("YOLO_MODEL_PATH", "models/yolov8n-pose.pt"))
DEFAULT_FENCE = {"enabled": True, "x": 0.1, "y": 0.1, "width": 0.8, "height": 0.9}
FISIO_FENCE = {"enabled": True, "x": 0.1, "y": 0.15, "width": 0.8, "height": 0.85}
DEFAULT_THRESHOLDS = {"trunk_angle": 35.0, "knee_angle": 60.0}


def angle(a, b, c):
    u = (a[0] - b[0], a[1] - b[1])
    v = (c[0] - b[0], c[1] - b[1])
    length = math.hypot(*u) * math.hypot(*v)
    if length == 0:
        return None
    return round(math.degrees(math.acos(max(-1, min(1, (u[0]*v[0] + u[1]*v[1]) / length)))), 1)


def pose_anomalies(spine, knee, mode, thresholds):
    anomalies = []
    if mode == "fisio" and spine is not None and spine > thresholds["trunk_angle"]:
        anomalies.append({
            "kind": f"Inclinação de tronco > {thresholds['trunk_angle']:g}°",
            "severity": "warning",
        })
    if mode == "fisio" and knee is not None and knee < thresholds["knee_angle"]:
        anomalies.append({
            "kind": f"Ângulo interno do joelho < {thresholds['knee_angle']:g}°",
            "severity": "warning",
        })
    return anomalies


def analyze_pose(result, width, height, mode, thresholds=None):
    thresholds = thresholds or DEFAULT_THRESHOLDS
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
        anomalies = pose_anomalies(spine, knee, mode, thresholds)
        people.append({
            "box": [box[0]/width, box[1]/height, (box[2]-box[0])/width, (box[3]-box[1])/height],
            "keypoints": normalized, "knee_angle": knee, "spine_angle": spine,
            "anomalies": anomalies,
        })
    return {"people": people}


def update_threshold_anomalies(payload, mode, thresholds):
    for person in payload.get("people", []):
        person["anomalies"] = pose_anomalies(
            person.get("spine_angle"), person.get("knee_angle"), mode, thresholds
        )
    return payload


def hip_position(person):
    hips = [point for point in person["keypoints"][11:13] if point[2] >= 0.5]
    if not hips:
        return None
    return tuple(sum(point[index] for point in hips) / len(hips) for index in (0, 1))


def inside_fence(position, fence):
    x, y = position
    return (fence["x"] <= x <= fence["x"] + fence["width"]
            and fence["y"] <= y <= fence["y"] + fence["height"])


class FenceSubjectTracker:
    def __init__(self, fence):
        self.fence = fence
        self.last_box = None

    def annotate(self, payload):
        payload["_fence_tracking_version"] = 1
        people = payload["people"]
        previous_tracked = next((person for person in people if person.get("fence_subject")), None)
        for person in people:
            person["fence_subject"] = False
        if not self.fence["enabled"] or not people:
            return payload

        candidates = []
        for person in people:
            position = hip_position(person)
            box = person.get("box")
            if position is None or not box:
                continue
            center = (box[0] + box[2] / 2, box[1] + box[3] / 2)
            candidates.append((person, position, center, box))

        if self.last_box is None:
            previous_candidate = next(
                (candidate for candidate in candidates if candidate[0] is previous_tracked), None
            )
            if previous_candidate is not None:
                chosen = previous_candidate
            else:
                candidates = [
                    candidate for candidate in candidates if inside_fence(candidate[1], self.fence)
                ]
                if not candidates:
                    return payload
                # Start with the largest person already inside the selected area.
                chosen = max(candidates, key=lambda candidate: candidate[3][2] * candidate[3][3])
        else:
            previous_center = (
                self.last_box[0] + self.last_box[2] / 2,
                self.last_box[1] + self.last_box[3] / 2,
            )
            chosen = min(
                candidates,
                key=lambda candidate: math.dist(candidate[2], previous_center),
                default=None,
            )
            if chosen is None:
                return payload
            max_distance = max(0.08, math.hypot(self.last_box[2], self.last_box[3]) * 0.75)
            if math.dist(chosen[2], previous_center) > max_distance:
                return payload

        chosen[0]["fence_subject"] = True
        self.last_box = chosen[3]
        return payload


def frame_events(payload, fence):
    events = {(a["kind"], a["severity"]) for p in payload["people"] for a in p["anomalies"]}
    if fence["enabled"]:
        subjects = [person for person in payload["people"] if person.get("fence_subject")]
        has_tracking = any("fence_subject" in person for person in payload["people"])
        if not subjects and not has_tracking:
            # Legacy frames lack tracking metadata. Don't treat bystanders outside the
            # area as an exit when another detected person is already inside it.
            subjects = [
                person for person in payload["people"]
                if (position := hip_position(person)) is not None and inside_fence(position, fence)
            ]
            if len(payload["people"]) == 1 and not subjects:
                subjects = payload["people"]
        for person in subjects:
            position = hip_position(person)
            if position is not None and not inside_fence(position, fence):
                events.add(("Saída da cerca virtual", "critical"))
    return sorted(events)