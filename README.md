# AI Traffic Management System

**AI-powered adaptive traffic signal control** — a complete end-to-end system that detects vehicles using YOLOv8, analyses per-lane density, and dynamically controls traffic signals with emergency preemption.

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    AI DETECTION LAYER                     │
│  Camera Feed → YOLO Detector → Vehicle Counter            │
├──────────────────────────────────────────────────────────┤
│                    BACKEND SERVICES                       │
│  FastAPI (REST+WebSocket) │ MQTT Bridge │ Signal Control  │
│  SQLite Database          │ History Log │ Density Analyser│
├──────────────────────────────────────────────────────────┤
│                    DISPLAY + OUTPUT                       │
│  React Dashboard │ OpenCV Window │ Terminal Log │ Signals │
├──────────────────────────────────────────────────────────┤
│                  SIGNAL CONTROL LOGIC                     │
│  Density Analyser │ Phase Scheduler │ Priority Override   │
│  History Log (Audit + Replay)                             │
└──────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Python 3.10+ 
- Node.js 18+
- (Optional) SUMO for traffic simulation

### 1. AI Services (Backend)

```bash
cd ai-services
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Server starts at `http://localhost:8001`

### 2. Web Dashboard (Frontend)

```bash
cd web-dashboard
npm install
npm run dev
```

Dashboard opens at `http://localhost:5173`

### 3. Start Detection

Via API:
```bash
# Webcam
curl -X POST http://localhost:8001/detection/start -H "Content-Type: application/json" -d '{"source": "0"}'

# Video file
curl -X POST http://localhost:8001/detection/start -H "Content-Type: application/json" -d '{"source": "/path/to/video.mp4"}'
```

---

## 📡 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Service info |
| GET | `/health` | Health check |
| GET | `/stats` | Current traffic snapshot |
| GET | `/stats/stream` | SSE live stream |
| POST | `/detection/start` | Start detection |
| POST | `/detection/stop` | Stop detection |
| GET | `/detection/status` | Detection status |
| GET | `/signal/status` | Signal states |
| POST | `/signal/override` | Force green on a lane |
| POST | `/vehicle-counts` | Receive external counts |
| GET | `/density` | Density analysis |
| GET | `/history` | Audit trail |
| GET | `/history/phases` | Phase change log |
| GET | `/history/alerts` | Alert log |
| WS | `/ws` | WebSocket (real-time) |

---

## 🧩 Project Structure

```
majour_proj/
├── ai-services/          # Python backend
│   ├── main.py           # FastAPI entry point + TrafficEngine
│   ├── config.py         # Configuration
│   ├── detection/        # Camera, YOLO, vehicle counter
│   ├── signal/           # Density, phase scheduler, priority, history
│   ├── api/              # Routes, WebSocket, MQTT bridge
│   ├── db/               # SQLite models + repository
│   └── display/          # OpenCV window, terminal, signal simulator
├── web-dashboard/        # React frontend (Vite)
│   └── src/
│       ├── components/   # Header, TrafficMap, LiveChart, etc.
│       ├── hooks/        # useWebSocket
│       └── services/     # REST API client
├── simulation/           # SUMO integration (optional)
└── docker-compose.yml
```

---

## 🐳 Docker

```bash
docker-compose up --build
```

---

## 📜 License

MIT
