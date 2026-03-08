import time
import cv2
import numpy as np

class SignalController:
    """Manages the traffic signals for an intersection with multiple lanes/zones.
    
    Dynamically switches green lights based on vehicle density.
    """
    
    def __init__(self, lanes: dict, default_green_time: int = 10, min_green_time: int = 5, yellow_time: int = 3):
        """
        Args:
            lanes: Dict of lane configurations: {"lane_name": {"polygon": [(x,y), ...], "light": "RED"}}
            default_green_time: How many seconds a light stays green usually.
            min_green_time: Minimum seconds a light must stay green before it can switch.
            yellow_time: Duration of yellow light transition.
        """
        self.lanes = lanes
        self.default_green_time = default_green_time
        self.min_green_time = min_green_time
        self.yellow_time = yellow_time
        
        # Initialize all to RED, then set first to GREEN
        self.lane_names = list(self.lanes.keys())
        for name in self.lane_names:
            self.lanes[name]["light"] = "RED"
            self.lanes[name]["count"] = 0
            
        self.active_lane = self.lane_names[0] if self.lane_names else None
        if self.active_lane:
            self.lanes[self.active_lane]["light"] = "GREEN"
            
        self.state_start_time = time.time()
        self.next_lane: str | None = None # Used when transitioning through YELLOW
        
    def update_counts(self, vehicle_centers: list[tuple[int, int]]):
        """Update the vehicle count for each lane based on detected centers."""
        # Reset counts
        for name in self.lane_names:
            self.lanes[name]["count"] = 0
            
        for center in vehicle_centers:
            for name, lane_data in self.lanes.items():
                polygon = np.array(lane_data["polygon"], np.int32)
                # Check if point is inside polygon (measure >= 0 means inside/on edge)
                if cv2.pointPolygonTest(polygon, center, False) >= 0:
                    self.lanes[name]["count"] += 1
                    break # Assign vehicle to exactly one lane
                    
    def tick(self):
        """Evaluate and manage state transitions for traffic lights."""
        if not self.active_lane:
            return
            
        current_time = time.time()
        elapsed = current_time - self.state_start_time
        
        current_light = self.lanes[self.active_lane]["light"]
        
        if current_light == "YELLOW":
            # If Yellow time has expired, switch to the next lane's Green light
            if elapsed >= self.yellow_time:
                self.lanes[self.active_lane]["light"] = "RED"
                self.active_lane = self.next_lane
                self.lanes[self.active_lane]["light"] = "GREEN"
                self.state_start_time = current_time
                self.next_lane = None
                
        elif current_light == "GREEN":
            # Evaluate if we should switch lights
            if elapsed >= self.min_green_time:
                # Find the lane with the highest wait count (excluding current empty lane if max time reached)
                max_count = -1
                best_candidate = None
                
                for name in self.lane_names:
                    if name != self.active_lane:
                        if self.lanes[name]["count"] > max_count:
                            max_count = self.lanes[name]["count"]
                            best_candidate = name
                
                # Switch if another lane has traffic AND (current lane is empty OR default green time elapsed)
                current_lane_count = self.lanes[self.active_lane]["count"]
                
                if best_candidate and max_count > 0:
                   if current_lane_count == 0 or elapsed >= self.default_green_time:
                        self._transition_to_yellow(best_candidate)
                        return
                        
                # Force switch if max time exceeded and there are ANY waiting cars
                if elapsed >= self.default_green_time and best_candidate and max_count > -1:
                       self._transition_to_yellow(best_candidate)
                       
    def _transition_to_yellow(self, next_lane: str):
        self.lanes[self.active_lane]["light"] = "YELLOW"
        self.next_lane = next_lane
        self.state_start_time = time.time()
        
    def draw(self, frame):
        """Draws the lanes, counts, and traffic lights on the frame."""
        overlay = frame.copy()
        for name, lane_data in self.lanes.items():
            pts = np.array(lane_data["polygon"], np.int32).reshape((-1, 1, 2))
            light = lane_data["light"]
            
            # Determine color for the lane polygon and text
            if light == "RED":
                color = (0, 0, 255) # BGR
            elif light == "YELLOW":
                color = (0, 255, 255)
            elif light == "GREEN":
                color = (0, 255, 0)
            else:
                color = (255, 255, 255)
                
            # Draw semi-transparent polygon
            cv2.fillPoly(overlay, [pts], color)
            
            # Text position (using the first point of the polygon as an anchor)
            text_x, text_y = pts[0][0]
            count = lane_data.get("count", 0)
            
            cv2.putText(frame, f"{name}: {light} ({count})", (text_x, max(30, text_y - 10)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                        
        # Apply the overlay
        alpha = 0.3
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
        return frame
