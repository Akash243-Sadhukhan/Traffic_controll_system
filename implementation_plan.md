# Spring Boot Backend — Layered Architecture Refactor

Refactor the [backend-services](file:///Users/akash/Desktop/minor/._backend-services) Java project from its current flat package structure into a clean, production-grade layered architecture with DTOs, input validation, global error handling, and proper separation of concerns.

## Current State

The existing code has 5 classes across inconsistently named packages:

```
com.traffic.backend_services/
├── Config/WebSocketConfig.java          ← OK, keep
├── Controller/DetectionController.java  ← uses entity as request/response body
├── Entity/Detection.java               ← Lombok @Data entity
├── Services/DetectionService.java       ← thin service, no error handling
├── Services/DetectionRepository.java    ← repository in wrong package
└── TrafficManagementBakcendApplication.java
```

**Problems:** no DTOs (entity exposed directly), no input validation, no error handling, no query endpoints (only POST), uppercase package names (Java convention is lowercase), repository in the services package.

## Proposed Changes

All files under `backend-services/src/main/java/com/traffic/backend_services/`.

---

### api (new package — replaces `Controller/`)

#### [MODIFY] [DetectionController.java](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/api/DetectionController.java)
- Move from `Controller/` → `api/`
- Accept `DetectionRequest` DTO, return `DetectionResponse` DTO
- Add `GET /api/detections` (list all) and `GET /api/detections/{id}` endpoints
- Use constructor injection instead of `@Autowired` field injection
- Add `@Valid` on request body

#### [NEW] [DetectionRequest.java](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/api/DetectionRequest.java)
- Inbound DTO with `@NotBlank` validation on `plateNumber`, `vehicleType`, `locationId`
- Optional `timestamp` field (defaults to now if absent)

#### [NEW] [DetectionResponse.java](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/api/DetectionResponse.java)
- Outbound DTO exposing: `id`, `plateNumber`, `vehicleType`, `locationId`, `timestamp`, `violation`

---

### service (rename from `Services/`)

#### [MODIFY] [DetectionService.java](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/service/DetectionService.java)
- Move from `Services/` → `service/`
- Constructor injection instead of `@Autowired`
- Methods: `create(DetectionRequest)`, `findById(String)`, `findAll()`
- Conversion between DTO ↔ entity happens here
- `findById` throws `DetectionNotFoundException` if missing

---

### domain (rename from `Entity/`)

#### [MODIFY] [Detection.java](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/domain/Detection.java)
- Move from `Entity/` → `domain/`
- Keep existing fields, rename `isViolation` → `violation` for consistency with Lombok getter naming

---

### infrastructure (new package — replaces repo in `Services/`)

#### [MODIFY] [DetectionRepository.java](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/infrastructure/DetectionRepository.java)
- Move from `Services/` → `infrastructure/`
- Add custom query: `findByPlateNumber(String)`

---

### exception (new package)

#### [NEW] [DetectionNotFoundException.java](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/exception/DetectionNotFoundException.java)
- Runtime exception for missing detection lookups

#### [NEW] [GlobalExceptionHandler.java](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/exception/GlobalExceptionHandler.java)
- `@ControllerAdvice` with handlers for:
  - `DetectionNotFoundException` → 404
  - `MethodArgumentNotValidException` → 400 with field-level errors
  - Generic `Exception` → 500

#### [NEW] [ErrorResponse.java](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/exception/ErrorResponse.java)
- Standard JSON error envelope: `status`, `error`, `message`, `timestamp`

---

### config (rename from `Config/`)

#### [MODIFY] [WebSocketConfig.java](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/config/WebSocketConfig.java)
- Move from `Config/` → `config/` (lowercase)
- No logic changes

---

### Deletions

#### [DELETE] [Controller/](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/Controller/)
#### [DELETE] [Entity/](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/Entity/)
#### [DELETE] [Services/](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/Services/)
#### [DELETE] [Config/](file:///Users/akash/Desktop/minor/backend-services/src/main/java/com/traffic/backend_services/Config/)

## Final Package Tree

```
com.traffic.backend_services/
├── TrafficManagementBakcendApplication.java   (unchanged)
├── api/
│   ├── DetectionController.java    ← @RestController, DTOs in/out
│   ├── DetectionRequest.java       ← inbound DTO with @Valid
│   └── DetectionResponse.java      ← outbound DTO
├── service/
│   └── DetectionService.java       ← business logic, DTO ↔ entity
├── domain/
│   └── Detection.java              ← MongoDB @Document entity
├── infrastructure/
│   └── DetectionRepository.java    ← MongoRepository interface
├── exception/
│   ├── DetectionNotFoundException.java
│   ├── GlobalExceptionHandler.java ← @ControllerAdvice
│   └── ErrorResponse.java          ← standard error envelope
└── config/
    └── WebSocketConfig.java        ← WebSocket/STOMP config
```

## Verification Plan

### Automated — Maven Compile
```bash
cd /Users/akash/Desktop/minor/backend-services && ./mvnw -DskipTests clean compile
```
A successful `BUILD SUCCESS` confirms all imports resolve, DTOs compile, and Spring component scanning finds all beans.

> [!NOTE]
> Full integration tests (`./mvnw test`) require a running MongoDB instance. The existing test class `TrafficManagementBakcendApplicationTests` uses `@SpringBootTest` and will need MongoDB. We'll run compile-only as the primary gate.
