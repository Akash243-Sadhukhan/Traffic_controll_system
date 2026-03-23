# Live Vehicle Count & ANPR Dashboard — Walkthrough

![Dashboard Preview](/Users/akash/.gemini/antigravity/brain/289f4677-0a1e-4ace-a55b-e723182df223/traffic_dashboard_preview_1774203046164.png)

## What was built

Four files were created or modified:

| File | Change |
|------|--------|
| [state_store.py](file:///Users/akash/Desktop/minor/ai-services/src/state_store.py) | **NEW** — thread-safe shared in-memory state (vehicle count, plates, arm queues) |
| [processor.py](file:///Users/akash/Desktop/minor/ai-services/src/processor.py) | **MODIFIED** — writes vehicle count per-frame and every stable plate read |
| [vehicle_count_routes.py](file:///Users/akash/Desktop/minor/ai-services/src/vehicle_count_routes.py) | **MODIFIED** — mirrors SUMO arm counts into state store |
| [main.py](file:///Users/akash/Desktop/minor/ai-services/src/main.py) | **MODIFIED** — serves `/stats`, `/stats/stream` (SSE), and `/dashboard` |

## How it works

```
Video stream  ──► processor.py ──► state_store.state  ──► /stats/stream (SSE)
SUMO publisher ──► vehicle_count_routes.py ──► state_store.state  ──┘
                                                                      │
                                                              Dashboard JS (EventSource)
                                                              auto-updates every 1 s
```

## New API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/stats` | JSON snapshot of current state |
| `GET` | `/stats/stream` | SSE push — new JSON every 1s |
| `GET` | `/dashboard` | Browser dashboard UI |

## Running

```bash
cd /Users/akash/Desktop/minor/ai-services
source ../venv/bin/activate
uvicorn src.main:app --reload --port 8000
```

Then open **http://localhost:8000/dashboard** in your browser.

### Test with a manual payload
```bash
curl -s -X POST http://localhost:8000/ai/vehicle-counts \
  -H "Content-Type: application/json" \
  -d '{"timestamp":1,"intersection_id":"A1",
       "arm_counts":{"north":5,"south":2,"east":9,"west":1},
       "total_vehicles":17,"mode":"ADAPTIVE","source":"sumo_simulation"}' | python3 -m json.tool
```
The Vehicle Count card and arm bars update immediately in the open browser tab.
