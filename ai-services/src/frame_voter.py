
from collections import Counter, deque
import time
from typing import List, Dict, Tuple, Optional, Any

# Type alias for a bounding box
BoundingBox = Tuple[int, int, int, int]

class FrameVoter:
    """
    Stabilizes license plate detections over multiple frames to reduce duplicates
    and filter out false positives.

    This class tracks vehicles using bounding box IoU overlap and buffers detections
    for each track. It emits a "final" detection only when a license plate string
    appears with sufficient frequency within the buffer, effectively voting on the
    correct result over a sequence of frames.
    """

    def __init__(
        self,
        buffer_size: int = 5,
        confidence_threshold: int = 3,
        iou_threshold: float = 0.6,
        timeout_seconds: float = 2.0,
    ):
        """
        Initializes the FrameVoter.

        Args:
            buffer_size (int): The number of recent frames to buffer for voting.
            confidence_threshold (int): The minimum number of times a plate string
                                        must appear in the buffer to be emitted.
            iou_threshold (float): The IoU threshold for matching a detection to an
                                   existing track.
            timeout_seconds (float): The duration in seconds after which a track is
                                     considered stale and removed if not updated.
        """
        self.buffer_size = buffer_size
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.timeout_seconds = timeout_seconds

        self.tracked_vehicles: Dict[int, Dict[str, Any]] = {}
        self.next_track_id = 0

    def _calculate_iou(self, box_a: BoundingBox, box_b: BoundingBox) -> float:
        """Calculates the Intersection over Union (IoU) of two bounding boxes."""
        x_a = max(box_a[0], box_b[0])
        y_a = max(box_a[1], box_b[1])
        x_b = min(box_a[2], box_b[2])
        y_b = min(box_a[3], box_b[3])

        inter_area = max(0, x_b - x_a) * max(0, y_b - y_a)
        box_a_area = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        box_b_area = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])

        union_area = float(box_a_area + box_b_area - inter_area)
        return inter_area / union_area if union_area > 0 else 0.0

    def _vote_on_plate(self, track_id: int) -> Optional[str]:
        """
        Performs voting on the plate buffer for a given track and returns the
        winning plate string if it meets the confidence threshold.
        """
        track = self.tracked_vehicles[track_id]
        # Only consider non-empty plate strings for voting
        valid_plates = [p for p in track["plate_buffer"] if p]
        if not valid_plates:
            return None

        # Find the most common plate and its count
        plate_counts = Counter(valid_plates)
        most_common_plate, count = plate_counts.most_common(1)[0]

        # Check if the count meets the required confidence threshold
        if count >= self.confidence_threshold:
            return most_common_plate
        return None

    def process_detections(
        self, frame_detections: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Processes detections from a new frame, updates tracks, and returns
        any newly confirmed license plates.

        Args:
            frame_detections (List[Dict[str, Any]]): A list of detection dicts
                from the current frame. Expected format:
                [{'bbox': (x1, y1, x2, y2), 'text': 'PLATE123'}, ...]

        Returns:
            List[Dict[str, Any]]: A list of confirmed detections that have met
            the voting criteria.
        """
        self._cleanup_stale_tracks()

        matched_track_ids = set()
        emitted_detections: List[Dict[str, Any]] = []

        # Match new detections to existing tracks
        for detection in frame_detections:
            best_match_id = -1
            highest_iou = self.iou_threshold

            for track_id, track_data in self.tracked_vehicles.items():
                iou = self._calculate_iou(detection["bbox"], track_data["bbox"])
                if iou > highest_iou:
                    highest_iou = iou
                    best_match_id = track_id

            if best_match_id != -1:
                # Update an existing track
                self.tracked_vehicles[best_match_id]["bbox"] = detection["bbox"]
                self.tracked_vehicles[best_match_id]["last_seen"] = time.time()
                self.tracked_vehicles[best_match_id]["plate_buffer"].append(detection["text"])
                matched_track_ids.add(best_match_id)
            else:
                # Register a new track
                self.tracked_vehicles[self.next_track_id] = {
                    "bbox": detection["bbox"],
                    "plate_buffer": deque([detection["text"]], maxlen=self.buffer_size),
                    "last_seen": time.time(),
                    "emitted": False,
                }
                self.next_track_id += 1

        # Vote on all updated tracks that have not yet emitted a result
        for track_id in self.tracked_vehicles:
            if not self.tracked_vehicles[track_id]["emitted"]:
                voted_plate = self._vote_on_plate(track_id)
                if voted_plate:
                    # Mark as emitted and add to the output list
                    self.tracked_vehicles[track_id]["emitted"] = True
                    emitted_detections.append(
                        {
                            "bbox": self.tracked_vehicles[track_id]["bbox"],
                            "text": voted_plate,
                            "track_id": track_id,
                        }
                    )
        return emitted_detections

    def _cleanup_stale_tracks(self):
        """Removes tracks that have not been seen for the timeout duration."""
        current_time = time.time()
        stale_ids = [
            track_id
            for track_id, data in self.tracked_vehicles.items()
            if current_time - data["last_seen"] > self.timeout_seconds
        ]
        for track_id in stale_ids:
            del self.tracked_vehicles[track_id]

if __name__ == '__main__':
    # Example Usage
    voter = FrameVoter(buffer_size=5, confidence_threshold=3, iou_threshold=0.5)

    # Detections for Frame 1
    detections_frame_1 = [
        {'bbox': (100, 100, 200, 150), 'text': 'MH20EE1234'},
        {'bbox': (300, 200, 400, 250), 'text': 'DL3CAW5678'}
    ]
    print(f"Frame 1 Detections: {detections_frame_1}")
    confirmed = voter.process_detections(detections_frame_1)
    print(f"Confirmed after Frame 1: {confirmed}\n") # Should be empty

    # Detections for Frame 2 (slight movement, one OCR error)
    detections_frame_2 = [
        {'bbox': (102, 101, 202, 151), 'text': 'MH20EE1234'},
        {'bbox': (305, 203, 405, 253), 'text': 'DL3CAW567B'} # Error 'B'
    ]
    print(f"Frame 2 Detections: {detections_frame_2}")
    confirmed = voter.process_detections(detections_frame_2)
    print(f"Confirmed after Frame 2: {confirmed}\n") # Should be empty

    # Detections for Frame 3 (another good read for the first plate)
    detections_frame_3 = [
        {'bbox': (105, 103, 205, 153), 'text': 'MH20EE1234'}
    ]
    print(f"Frame 3 Detections: {detections_frame_3}")
    confirmed = voter.process_detections(detections_frame_3)
    # The first plate has now been seen 3 times, so it should be emitted.
    print(f"Confirmed after Frame 3: {confirmed}\n")

    # Detections for Frame 4 (it won't be emitted again)
    detections_frame_4 = [
        {'bbox': (107, 105, 207, 155), 'text': 'MH20EE1234'}
    ]
    print(f"Frame 4 Detections: {detections_frame_4}")
    confirmed = voter.process_detections(detections_frame_4)
    print(f"Confirmed after Frame 4: {confirmed}\n") # Should be empty
