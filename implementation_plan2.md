# Live Vehicle Count & ANPR Dashboard

Add a self-contained, real-time browser dashboard to the existing [ai-services](file:///Users/akash/Desktop/minor/._ai-services) FastAPI app.  
When a video stream is running, the UI auto-refreshes every second to show the live vehicle count and detected number plates.

## Proposed Changes

### State layer
#### [NEW] `state_store.py`
- A module-level `AppState` dataclass holding:
  - `vehicle_count: int`
  - `plates: deque[dict]` (last 50 detections)
  - `arm_counts: dict` (N/S/E/W, from SUMO)
  - `last_updated: datetime`
- Single shared instance imported everywhere — no DB needed.

---

### Backend changes

#### [MODIFY] [processor.py](file:///Users/akash/Desktop/minor/ai-services/src/processor.py)
- After a stable plate is confirmed (line ~313), push to `state_store.state.plates`.
- After each frame's vehicle detection loop, update `state_store.state.vehicle_count` with the current vehicle bounding-box count.

#### [MODIFY] [vehicle_count_routes.py](file:///Users/akash/Desktop/minor/ai-services/src/vehicle_count_routes.py)
- After computing `arm_analysis`, mirror `arm_counts` and `total_vehicles` into `state_store.state`.

#### [MODIFY] [main.py](file:///Users/akash/Desktop/minor/ai-services/src/main.py)
- Import and mount `state_store`.
- Add three new endpoints:
  | Method | Path | Description |
  |--------|------|-------------|
  | `GET` | `/stats` | JSON snapshot: count, plates, arms, timestamp |
  | `GET` | `/stats/stream` | SSE stream, pushes JSON every 1 s |
  | `GET` | `/dashboard` | Serves the HTML dashboard page |

---

### Frontend (single file)

#### [NEW] `dashboard.html`  (served inline from [main.py](file:///Users/akash/Desktop/minor/ai-services/src/main.py))
A single embedded HTML page with vanilla CSS + JS — no build step, no extra dependencies.

**Layout:**
```
┌──────────────────────────────────────┐
│     🚦 Traffic Control Dashboard     │
├──────────────┬───────────────────────┤
│ Vehicle Count│  Arm Congestion (N/S/E/W) bar chart │
│   [ 42 ]     │                       │
├──────────────┴───────────────────────┤
│  Live ANPR Feed (scrolling table)    │
│  Plate | Type | Location | Time      │
└──────────────────────────────────────┘
```

**Auto-update:** Uses `EventSource` (SSE) so it pushes instantly when the processor emits new data — no polling.  
**Fallback:** Also works if SSE is unavailable via a `setInterval` polling `/stats` every 2 s.

## Verification Plan

### Manual Verification
1. Start the FastAPI service:
   ```bash
   cd /Users/akash/Desktop/minor/ai-services
   source ../venv/bin/activate
   uvicorn src.main:app --reload --port 8000
   ```
2. Open `http://localhost:8000/dashboard` in a browser — the dashboard should render immediately.
3. Open `http://localhost:8000/stats` — should return JSON with [vehicle_count](file:///Users/akash/Desktop/minor/ai-services/src/vehicle_count_routes.py#64-129), `plates`, `arm_counts`.
4. POST a test payload to the vehicle-count endpoint and verify the dashboard updates:
   ```bash
   curl -X POST http://localhost:8000/ai/vehicle-counts \
     -H "Content-Type: application/json" \
     -d '{"timestamp":1,"intersection_id":"A1","arm_counts":{"north":5,"south":2,"east":8,"west":1},"total_vehicles":16,"mode":"ADAPTIVE","source":"sumo_simulation"}'
   ```
   The vehicle count card and arm bars should update live in the browser.
5. (Optional) Start the video stream via `POST /start-stream` with a test video — verify the ANPR table populates with detected plates.
