# Traffic_controll_system

**Traffic Control System** — A small end-to-end project that detects vehicles and license plates using YOLO models and OCR, persists detections in a Spring Boot + MongoDB backend, and provides a simple pipeline for real-time video processing and reporting.

---

## 🚀 Project Overview
- **Backend**: Spring Boot service (`backend-services`) that exposes an API to accept detection payloads and store them in MongoDB.
- **AI Services**: Lightweight Python pipeline (`ai-services`) that runs YOLO-based vehicle & plate detection, performs OCR (EasyOCR), and sends detections to the backend asynchronously.
- **Data & Models**: Model weights and labeled data live under `ai-services/Data/` (sample datasets and `weights` folder).

---

## 📋 Contents
- `backend-services/` — Java Spring Boot application (Maven project)
- `ai-services/` — Python detection + OCR pipeline and notebooks
- `data_set/` — Misc datasets and usage notes
- Notebooks for experimentation: `car_object_detattion.ipynb`, `yolov11.ipynb`, etc.

---

## ✅ Prerequisites
- Java 21 (recommended)
- Maven (or use the included `./mvnw` wrapper)
- Python 3.10+ (use 3.11 if possible)
- pip and virtualenv/venv
- PyTorch (install per your platform from https://pytorch.org/)
- A MongoDB instance for the backend (local or cloud)

Python packages used (see `ai-services/requirements.txt`):
- `opencv-python`, `numpy`, `ultralytics`, `easyocr`, `httpx`, `fastapi`, `uvicorn`

> Tip: On macOS, enable MPS-capable PyTorch if you have Apple Silicon for faster inference.

---

## 🛠️ Setup & Run (Step-by-step)

### 1) Backend (Spring Boot)
1. Configure MongoDB connection in: `backend-services/src/main/resources/application.properties` (set `spring.data.mongodb.uri` or host/port)
2. Build the backend (from repo root):

```bash
cd backend-services
./mvnw -DskipTests clean package
```

3. Run the backend jar (after successful package):

```bash
java -jar target/backend-services-0.0.1-SNAPSHOT.jar
```

Alternatively, use the helper script (made executable):

```bash
./backend-services/run_backend.sh
```

4. Health check: open `http://localhost:8080/actuator/health` (if actuator is enabled) and POST detections to `POST /api/detections`.

> Note: If you see classpath scanning or ASM-related build issues with newer Java versions, the plugin already includes an explicit `<start-class>` to avoid scanning problems.


### 2) AI Services (Python)
1. Create & activate a virtual environment (recommended):

```bash
python -m venv ~/venvs/tcs
source ~/venvs/tcs/bin/activate
```

2. Install dependencies:

```bash
pip install --upgrade pip
pip install -r ai-services/requirements.txt
# If you need torch, install it per your platform instructions (see https://pytorch.org/)
```

3. Prepare model weights
- Place your YOLO model weights under `ai-services/Data/weights/` (e.g., `best.pt` for plate model and a vehicle model file).

4. Run detection pipeline (example):

```python
# simple runner example
from ai_services.src.processor import TrafficPipeline
import asyncio

pipeline = TrafficPipeline('ai-services/Data/weights/yolov8n.pt', 'ai-services/Data/weights/best.pt', 'http://localhost:8080')
asyncio.run(pipeline.process_stream(0))  # 0 uses default webcam; supply path to video file otherwise
```

5. If you prefer notebooks, open `ai-services/*.ipynb` with Jupyter and follow the cells.

---

## 🧪 Testing
- Backend: Use `curl` or Postman to POST JSON payloads to `http://localhost:8080/api/detections`.
- AI: Run the `processor` on a short video or a single image and verify that the backend receives the JSON payload.

Example payload schema:
```json
{
  "plateNumber": "ABC1234",
  "vehicleType": "Car",
  "locationId": "INTERSECTION_A1",
  "timestamp": "2026-01-31T12:34:56"
}
```

---

## 🔧 Troubleshooting & Notes
- If the backend fails to start and reports missing Spring packages, run a full `./mvnw clean package` to ensure dependencies are fetched.
- If YOLO inference is slow, verify that PyTorch is using MPS (macOS) or CUDA (Linux/GPU). Otherwise force CPU by setting device to `cpu`.
- If OCR returns empty results often, inspect the `ai-services/src/processor.py` preprocessing helpers and provide higher-quality plate crops.

---

## 📈 Next Steps (Suggested)
1. Add Dockerfiles for both `backend-services` and `ai-services` for reproducible deployment. ✅
2. Add unit tests for `recognize_and_clean` and backend controllers; add CI (GitHub Actions). ✅
3. Expand plate-format normalization for locale-specific rules and confidence scoring.
4. Add a simple UI (map / live feed) subscribing to a WebSocket topic for real-time visualization.

---

## 🤝 Contributing
- Please open issues or PRs. Keep changes small & documented.

---

## 📜 License
Add an appropriate license if you plan to share this repo publicly.

---

If you'd like, I can:
- Add a sample script to `ai-services` that runs a single-frame test and asserts output ✅
- Create Dockerfiles and a `docker-compose.yml` to run the whole stack locally ✅

Let me know what you want next! ✨
