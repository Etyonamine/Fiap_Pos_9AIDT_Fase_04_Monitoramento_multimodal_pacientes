import math
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
MODEL_PATH = Path(os.environ.get("YOLO_MODEL_PATH", "models/yolov8n-pose.pt")).expanduser()
if not MODEL_PATH.is_absolute():
    MODEL_PATH = BACKEND_DIR / MODEL_PATH
MODEL_PATH = MODEL_PATH.resolve()
DEFAULT_FENCE = {"enabled": True, "x": 0.1, "y": 0.1, "width": 0.8, "height": 0.9}
FISIO_FENCE = {"enabled": True, "x": 0.1, "y": 0.15, "width": 0.8, "height": 0.85}
DEFAULT_THRESHOLDS = {"trunk_angle": 35.0, "knee_angle": 60.0}
POSE_ANOMALIES_VERSION = 4
DEFAULT_LYING_TRUNK_ANGLE = 15.0
DEFAULT_LYING_KNEE_FLEXION = 30.0
KEYPOINT_CONFIDENCE = 0.5
POSE_ALERT_FRAMES = 5
KEYPOINT_EMA_ALPHA = 0.4


def angle(a, b, c):
    u = (a[0] - b[0], a[1] - b[1])
    v = (c[0] - b[0], c[1] - b[1])
    length = math.hypot(*u) * math.hypot(*v)
    if length == 0:
        return None
    return round(math.degrees(math.acos(max(-1, min(1, (u[0]*v[0] + u[1]*v[1]) / length)))), 1)


def posture_at(config, timestamp):
    if config is None:
        return "legacy"
    if config["type"] == "hybrid":
        return next(
            (interval["posture"] for interval in config["intervals"]
             if interval["start"] <= timestamp < interval["end"]),
            None,
        )
    return config["type"] if config["type"] != "unclassified" else None


def pose_anomalies(spine, knee, mode, thresholds, posture="legacy", trunk_elevation=None):
    anomalies = []
    if (
        mode == "fisio"
        and posture in ("legacy", "standing", "sitting")
        and spine is not None
        and spine > thresholds["trunk_angle"]
    ):
        anomalies.append({
            "kind": f"Inclinação de tronco > {thresholds['trunk_angle']:g}°",
            "severity": "warning",
        })
    if mode == "fisio" and posture in ("legacy", "standing", "sitting") and knee is not None and knee < thresholds["knee_angle"]:
        anomalies.append({
            "kind": f"Ângulo interno do joelho < {thresholds['knee_angle']:g}°",
            "severity": "warning",
        })
    lying_limit = thresholds.get("lying_trunk_angle", DEFAULT_LYING_TRUNK_ANGLE)
    if mode == "fisio" and posture == "lying" and trunk_elevation is not None and trunk_elevation > lying_limit:
        anomalies.append({
            "kind": f"Elevação do tronco em relação à posição inicial > {lying_limit:g}°",
            "severity": "warning",
        })
    return anomalies


def analyze_pose(result, width, height, mode, thresholds=None, posture="legacy"):
    thresholds = thresholds or DEFAULT_THRESHOLDS
    people = []
    payload = {"people": people, "_pose_anomalies_version": POSE_ANOMALIES_VERSION}
    if mode == "fisio" and posture != "legacy":
        payload["posture"] = posture
    if result.keypoints is None:
        return payload
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
        unavailable_metrics = []
        if knee is None:
            unavailable_metrics.append("knee_angle")
        if spine is None:
            unavailable_metrics.append("spine_angle")
        # These are screening heuristics, not a clinically validated diagnosis.
        anomalies = pose_anomalies(spine, knee, mode, thresholds, posture)
        people.append({
            "box": [box[0]/width, box[1]/height, (box[2]-box[0])/width, (box[3]-box[1])/height],
            "keypoints": normalized, "knee_angle": knee, "spine_angle": spine,
            "anomalies": anomalies, "unavailable_metrics": unavailable_metrics,
        })
    return payload


def update_threshold_anomalies(payload, mode, thresholds):
    for person in payload.get("people", []):
        person["anomalies"] = pose_anomalies(
            person.get("spine_angle"), person.get("knee_angle"), mode, thresholds,
            payload.get("posture", "legacy"),
            person.get("trunk_elevation"),
        )
    payload["_pose_anomalies_version"] = POSE_ANOMALIES_VERSION
    return payload


class LyingTrunkTracker:
    def __init__(self, mode, thresholds, width=1, height=1):
        self.mode = mode
        self.thresholds = thresholds
        self.width = width
        self.height = height
        self.baseline = None
        self.baseline_length = None
        self.baseline_face_angle = None
        self.interval = None

    def annotate(self, payload, interval=None):
        lying = self.mode == "fisio" and payload.get("posture") == "lying"
        if not lying or interval != self.interval:
            self.baseline = None
            self.baseline_length = None
            self.baseline_face_angle = None
        self.interval = interval
        payload.pop("lying_trunk_quality", None)
        if lying:
            payload["lying_trunk_quality"] = {"status": "inconclusive", "reason": "target_unavailable"}
        for person in payload.get("people", []):
            person.pop("trunk_baseline", None)
            person.pop("trunk_elevation", None)
            if lying and person.get("fence_subject"):
                spine = person.get("spine_angle")
                points = person.get("keypoints", [])
                if spine is None or len(points) < 13:
                    reason = "trunk_unavailable"
                elif points[0][2] < 0.7:
                    reason = "face_unreliable"
                else:
                    dx = ((points[5][0] + points[6][0]) - (points[11][0] + points[12][0])) * self.width / 2
                    dy = ((points[5][1] + points[6][1]) - (points[11][1] + points[12][1])) * self.height / 2
                    length = math.hypot(dx, dy)
                    if not length or (self.baseline_length is not None and
                                      not 0.6 <= length / self.baseline_length <= 1.6):
                        reason = "trunk_geometry_changed"
                    else:
                        face_dx = (points[0][0] - (points[11][0] + points[12][0]) / 2) * self.width
                        face_dy = (points[0][1] - (points[11][1] + points[12][1]) / 2) * self.height
                        face_angle = math.degrees(math.atan2(abs(face_dx), abs(face_dy)))
                        if not math.hypot(face_dx, face_dy):
                            reason = "face_geometry_invalid"
                        elif self.baseline is not None and abs(
                            (self.baseline - spine) - (self.baseline_face_angle - face_angle)
                        ) > 10:
                            reason = "head_trunk_disagreement"
                        else:
                            reason = None
                        if reason is None and self.baseline is None:
                            self.baseline = spine
                            self.baseline_length = length
                            self.baseline_face_angle = face_angle
                        if reason is None:
                            person["trunk_baseline"] = self.baseline
                            person["trunk_elevation"] = round(max(0.0, self.baseline - spine), 1)
                payload["lying_trunk_quality"] = (
                    {"status": "inconclusive", "reason": reason}
                    if reason else {"status": "eligible", "reason": None}
                )
        return update_threshold_anomalies(payload, self.mode, self.thresholds)


class PhysiotherapyTracker:
    """Rebuild physiotherapy metrics chronologically from the original keypoints."""

    def __init__(self, mode, thresholds, width, height, fps):
        self.mode = mode
        self.thresholds = thresholds
        self.width = width
        self.height = height
        self.fps = fps
        self.trunk = LyingTrunkTracker(mode, thresholds, width, height)
        self.points = {}
        self.knee_baselines = {}
        self.counts = {}
        self.previous_context = None
        self.previous_timestamp = None

    def annotate(self, payload, timestamp, interval):
        posture = payload.get("posture")
        context = (posture, interval)
        subject = next((p for p in payload.get("people", []) if p.get("fence_subject")), None)
        contiguous = (
            self.previous_timestamp is not None and self.fps > 0
            and 0 < timestamp - self.previous_timestamp <= 1.5 / self.fps
        )
        if context != self.previous_context or not contiguous or subject is None:
            self.points.clear()
            self.counts.clear()
        if context != self.previous_context:
            self.knee_baselines.clear()
        self.previous_context = context
        self.previous_timestamp = timestamp
        payload = self.trunk.annotate(payload, interval)
        if subject is None:
            return payload

        raw = subject.get("keypoints", [])
        side_angles = {}
        lying_pose_unreliable = posture == "lying" and payload["lying_trunk_quality"]["status"] != "eligible"
        for side, indices in (("left", (11, 13, 15)), ("right", (12, 14, 16))):
            if lying_pose_unreliable or len(raw) <= max(indices) or any(
                not all(math.isfinite(value) for value in raw[index][:3])
                or raw[index][2] < KEYPOINT_CONFIDENCE for index in indices
            ):
                for index in indices:
                    self.points.pop(index, None)
                continue
            for index in indices:
                point = raw[index]
                previous = self.points.get(index)
                self.points[index] = (
                    (point[0], point[1]) if previous is None else
                    tuple(KEYPOINT_EMA_ALPHA * point[i] + (1 - KEYPOINT_EMA_ALPHA) * previous[i]
                          for i in (0, 1))
                )
            coords = [(self.points[i][0] * self.width, self.points[i][1] * self.height) for i in indices]
            value = angle(*coords)
            if value is not None:
                side_angles[side] = value
        subject["knee_angle"] = min(side_angles.values()) if side_angles else None
        subject["knee_available_sides"] = list(side_angles)
        subject["knee_unavailable_reason"] = (
            "pose_unreliable" if lying_pose_unreliable else
            "keypoints_unavailable" if not side_angles else None
        )
        unavailable = set(subject.get("unavailable_metrics", []))
        if side_angles:
            unavailable.discard("knee_angle")
        else:
            unavailable.add("knee_angle")
        subject["unavailable_metrics"] = sorted(unavailable)
        subject.pop("knee_baselines", None)
        subject.pop("knee_flexion", None)
        if posture == "lying":
            for side, value in side_angles.items():
                self.knee_baselines.setdefault(side, value)
            if side_angles:
                subject["knee_baselines"] = dict(self.knee_baselines)
                subject["knee_flexion"] = round(max(
                    0.0, *(self.knee_baselines[side] - value for side, value in side_angles.items())
                ), 1)

        anomalies = pose_anomalies(
            subject.get("spine_angle"), None, self.mode, self.thresholds,
            posture, subject.get("trunk_elevation"),
        )
        limit = self.thresholds.get("lying_knee_flexion", DEFAULT_LYING_KNEE_FLEXION)
        current = {item["kind"] for item in anomalies}
        for side, value in side_angles.items():
            if posture == "lying" and self.knee_baselines[side] - value > limit:
                current.add(f"lying_knee_{side}")
            elif posture in ("standing", "sitting") and value < self.thresholds["knee_angle"]:
                current.add(f"absolute_knee_{side}")
        self.counts = {kind: self.counts.get(kind, 0) + 1 for kind in current}
        subject["anomalies"] = [item for item in anomalies if self.counts[item["kind"]] >= POSE_ALERT_FRAMES]
        if any(self.counts.get(f"lying_knee_{side}", 0) >= POSE_ALERT_FRAMES for side in side_angles):
            subject["anomalies"].append({
                "kind": f"Flexão do joelho deitado em relação à posição inicial > {limit:g}°",
                "severity": "warning",
            })
        if any(self.counts.get(f"absolute_knee_{side}", 0) >= POSE_ALERT_FRAMES for side in side_angles):
            subject["anomalies"].append({
                "kind": f"Ângulo interno do joelho < {self.thresholds['knee_angle']:g}°",
                "severity": "warning",
            })
        payload["_pose_anomalies_version"] = POSE_ANOMALIES_VERSION
        return payload


def posture_interval_at(config, timestamp):
    if config and config["type"] == "hybrid":
        return next(
            (index for index, interval in enumerate(config["intervals"])
             if interval["start"] <= timestamp < interval["end"]),
            None,
        )
    return None


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
        payload["_fence_tracking_version"] = 2
        people = payload["people"]
        previous_tracked = next((person for person in people if person.get("fence_subject")), None)
        for person in people:
            person["fence_subject"] = False
        if not people:
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
                if self.fence["enabled"]:
                    candidates = [
                        candidate for candidate in candidates
                        if inside_fence(candidate[1], self.fence)
                    ]
                if not candidates:
                    return payload
                # Start with the largest person in the selected area, or in-frame
                # when the virtual fence is disabled.
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
    tracked = [
        person for person in payload["people"] if person.get("fence_subject")
    ]
    if payload.get("_fence_tracking_version", 0) >= 2:
        analyzed_people = tracked
    else:
        analyzed_people = payload["people"]
    events = {
        (anomaly["kind"], anomaly["severity"])
        for person in analyzed_people
        for anomaly in person.get("anomalies", [])
    }
    if fence["enabled"]:
        subjects = tracked
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