# Smart Traffic Control System — SETUP.md

> Full setup guide for all five services: Backend, AI, Simulation, RL Model, Dashboard.

---

## 1. Prerequisites

| Tool | Minimum version | macOS install |
|------|----------------|---------------|
| Java | 21 | `brew install openjdk@21` |
| Maven | 3.9 | `brew install maven` |
| Python | 3.13 | `brew install python@3.13` |
| MongoDB Community | 7.x | `brew tap mongodb/brew && brew install mongodb-community` |
| SUMO | 1.19 | [sumo.dlr.de](https://sumo.dlr.de/docs/Downloads.php) `.pkg` **or** `brew install sumo` |
| Node.js | — | **NOT required** — dashboard is pure HTML |

---

## 2. Environment setup

```bash
# From project root (minor/)
python3.13 -m venv venv
source venv/bin/activate

pip install -r ai-services/requirements.txt     # FastAPI, uvicorn, httpx …
pip install stable-baselines3 gymnasium torch   # RL dependencies
pip install traci sumolib rich pynput httpx     # Simulation dependencies

# SUMO_HOME — macOS Homebrew
export SUMO_HOME="$(brew --prefix sumo)/share/sumo"
echo 'export SUMO_HOME="$(brew --prefix sumo)/share/sumo"' >> ~/.zshrc

# Verify
which sumo && which sumo-gui       # should print paths
python -c "import traci; print('traci OK')"
mongosh --eval "db.runCommand({ping:1})"
```

---

## 3. RL model — train before first run

The RL controller requires a trained PPO model. Run training **once** before starting the system.

```bash
cd ai-services
source ../venv/bin/activate

# Quick smoke test (~2 min on CPU)
python src/rl/train_rl_model.py --timesteps 10000

# Full training (~45 min on CPU, recommended)
python src/rl/train_rl_model.py
```

Expected output at completion:
```
Training complete. Model saved to models/weights/rl_signal/
  best_model.zip  ← used by inference engine
  final_model.zip ← final checkpoint
```

Evaluate a saved model (10 episodes, prints mean reward):
```bash
python src/rl/train_rl_model.py --evaluate
```

> **Note**: If `best_model.zip` is missing, the AI service falls back to a queue-length heuristic automatically — the system still runs.

---

## 4. Start all services (correct order)

Open **four** terminal tabs:

### Terminal 1 — MongoDB
```bash
brew services start mongodb-community
# Verify: mongosh --eval "db.adminCommand('ping')"
```

### Terminal 2 — Backend (Spring Boot)
```bash
cd backend-services
mvn spring-boot:run
# Listening on http://localhost:8080
# Dashboard available at http://localhost:8080/index.html
```

### Terminal 3 — AI Services (FastAPI)
```bash
cd ai-services
source ../venv/bin/activate
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
# API docs at http://localhost:8001/docs
```

### Terminal 4 — SUMO Simulation
```bash
cd Sumo_simulation/scripts
source ../../venv/bin/activate

# With GUI (default)
python traffic_demo.py

# Headless (CI/server)
python traffic_demo.py --nogui
```

---

## 5. Verify data flow

After all services are running, run these checks:

```bash
# 1. Backend health
curl http://localhost:8080/api/dashboard/stats

# 2. AI service health
curl http://localhost:8001/health

# 3. RL model status
curl http://localhost:8001/ai/rl/status

# 4. Send a test RL prediction
curl -X POST http://localhost:8001/ai/rl/predict \
  -H "Content-Type: application/json" \
  -d '{"intersection_id":"TEST","timestamp":0,"north_count":5,"south_count":2,"east_count":8,"west_count":1}'

# 5. Check stored decisions
curl http://localhost:8080/api/signal-decisions/latest
```

| Test | Expected result |
|------|----------------|
| Dashboard loads | `http://localhost:8080` shows dark UI, live dot turns green |
| arm bars update | Bars animate within 5s of sim start |
| ANPR table fills | Plates appear with timestamps |
| RL panel shows decision | Green arm + confidence visible |
| WS connected | "LIVE" label with pulsing dot |

---

## 6. Switching AI input source

**Via Dashboard UI:**
1. Open the "AI Input Source" panel
2. Select Simulation / Camera / Video
3. Click **Connect** or **Load**

**Via `curl`:**
```bash
# Switch to camera 0
curl -X POST http://localhost:8001/ai/source/switch \
  -H "Content-Type: application/json" \
  -d '{"source":"camera","camera_index":0}'

# Switch to video file
curl -X POST http://localhost:8001/ai/source/switch \
  -H "Content-Type: application/json" \
  -d '{"source":"video","video_path":"Data/traffic.mp4"}'

# Switch back to SUMO simulation webhook
curl -X POST http://localhost:8001/ai/source/switch \
  -H "Content-Type: application/json" \
  -d '{"source":"simulation"}'
```

---

## 7. Traffic Control Panel

| Control | Action | Backend endpoint |
|---------|--------|-----------------|
| Spawn Rate slider | Set vehicles/min (5–60) | `POST /api/sim/spawn-rate` |
| Signal Mode radio | FIXED / ADAPTIVE / RL | `POST /api/sim/set-mode` |
| Emergency button | Inject priority vehicle | `POST /api/sim/spawn-emergency` |
| Flagged button | Inject flagged plate vehicle | `POST /api/sim/spawn-flagged` |
| Reset button | Restore default spawn rate | `POST /api/sim/reset` |

The simulation polls `GET /api/sim/commands/latest` every 5 steps and applies the command, then calls `DELETE /api/sim/commands/latest` to acknowledge it.

---

## 8. Keyboard shortcuts (simulation terminal)

| Key | Effect |
|-----|--------|
| `+` / `=` | Increase spawn rate by 5 |
| `-` | Decrease spawn rate by 5 |
| `e` | Spawn emergency vehicle |
| `f` | Spawn flagged vehicle |
| `r` | Reset spawn rate |
| `m` | Cycle mode: FIXED → ADAPTIVE → RL → FIXED |
| `q` / `Esc` | Quit simulation |

---

## 9. RL Controller — how it works

```
SUMO TraCI loop
  │  every CFG.adaptive_check_every steps, when mode == "RL"
  ▼
request_rl_signal()          ← traffic_demo.py
  │  POST /ai/rl/predict
  ▼
RLSignalController.predict() ← rl_inference.py
  │  PPO model (stable-baselines3)
  ▼
SignalDecisionResponse        ← returned in <2s
  │  also POSTed to /api/signal-decisions (async, non-blocking)
  ▼
traci.trafficlight.setPhase() ← applies green arm
traci.trafficlight.setPhaseDuration()
```

Mode progression:
- **t = 0 – 29 s** → FIXED (30s green / 5s yellow)
- **t = 30 – 59 s** → ADAPTIVE (queue-length heuristic)
- **t ≥ 60 s** → RL (PPO model)
- Dashboard "Set Mode" button overrides at any time

---

## 10. Project file map

```
minor/
├── backend-services/
│   └── src/main/java/com/traffic/backend_services/
│       ├── api/
│       │   ├── DashboardController.java        ← GET /api/dashboard/*
│       │   ├── DashboardWebSocketPublisher.java ← pushes /topic/live
│       │   ├── SignalDecisionController.java   ← POST/GET /api/signal-decisions
│       │   ├── SimControlController.java       ← POST /api/sim/*
│       │   └── dto/                            ← Java 21 record DTOs
│       ├── Config/
│       │   └── WebSocketConfig.java            ← STOMP broker
│       ├── domain/
│       │   ├── Detection.java
│       │   ├── SignalDecision.java              ← RL decisions (MongoDB)
│       │   ├── SimControlCommand.java           ← dashboard commands
│       │   └── VehicleCountEvent.java
│       └── infrastructure/                     ← Spring Data repositories
│   └── src/main/resources/static/
│       └── index.html                          ← React dashboard SPA
│
├── ai-services/src/
│   ├── rl/
│   │   ├── traffic_env.py                      ← Gymnasium environment
│   │   ├── train_rl_model.py                   ← PPO training script
│   │   └── rl_inference.py                     ← Inference singleton
│   ├── api/
│   │   ├── rl_routes.py                        ← POST /ai/rl/predict
│   │   ├── source_routes.py                    ← /ai/source/*
│   │   └── vehicle_count_routes.py             ← /ai/vehicle-counts
│   ├── models/
│   │   ├── rl_models.py                        ← Pydantic request/response
│   │   └── vehicle_count.py
│   ├── input_selector.py                       ← SIMULATION/CAMERA/VIDEO
│   ├── state_store.py                          ← Thread-safe live state
│   ├── processor.py                            ← ANPR + detection pipeline
│   └── main.py                                 ← FastAPI app entry point
│
├── Sumo_simulation/scripts/
│   ├── traffic_demo.py                         ← Main SUMO loop
│   ├── config.py                               ← CFG + STATE singletons
│   └── publisher.py                            ← Vehicle count HTTP publisher
│
└── SETUP.md                                    ← This file
```

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `sumo-gui` not found | SUMO not in PATH | `export SUMO_HOME=...` + reopen terminal |
| RL panel shows "Not found" | Model not trained | Run `train_rl_model.py --timesteps 10000` |
| WS never connects | Backend not running / wrong port | Check Terminal 2, port 8080 |
| ANPR table empty | SUMO not publishing to AI | Check Terminal 3 + Terminal 4 logs |
| `stable_baselines3` ImportError | Missing pip package | `pip install stable-baselines3` |
| Spring Boot fails on MongoDB | Atlas URI not set | Check `application.properties` |
