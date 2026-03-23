// backend-services/src/main/java/com/traffic/backend_services/api/DetectionController.java
package com.traffic.backend_services.api;

import com.traffic.backend_services.api.dto.VehicleCountEventRequest;
import com.traffic.backend_services.domain.VehicleCountEvent;
import com.traffic.backend_services.service.DetectionService;
import com.traffic.backend_services.service.VehicleCountService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * REST controller for traffic detection events.
 *
 * <ul>
 *   <li>{@code POST /api/detections}                        — create ANPR detection (existing)</li>
 *   <li>{@code GET  /api/detections}                        — list all detections (existing)</li>
 *   <li>{@code GET  /api/detections/{id}}                   — get single detection (existing)</li>
 *   <li>{@code POST /api/detections/vehicle-count}          — store SUMO vehicle-count event (new)</li>
 *   <li>{@code GET  /api/detections/vehicle-count/latest}   — retrieve 20 most recent events (new)</li>
 * </ul>
 */
@RestController
@RequestMapping("/api/detections")
@CrossOrigin(origins = "*")
public class DetectionController {

    private final DetectionService       detectionService;
    private final VehicleCountService    vehicleCountService;
    private final SimpMessagingTemplate  messagingTemplate;   // may be null

    // ── Constructor injection — no @Autowired on fields ──────────────────────
    public DetectionController(
            DetectionService      detectionService,
            VehicleCountService   vehicleCountService,
            @org.springframework.beans.factory.annotation.Autowired(required = false)
            SimpMessagingTemplate messagingTemplate) {
        this.detectionService    = detectionService;
        this.vehicleCountService = vehicleCountService;
        this.messagingTemplate   = messagingTemplate;
    }

    // ── Existing: ANPR detection ──────────────────────────────────────────────

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public DetectionResponse create(@Valid @RequestBody DetectionRequest request) {
        DetectionResponse response = detectionService.create(request);

        if (messagingTemplate != null) {
            messagingTemplate.convertAndSend("/topic/live-traffic", response);
        }

        return response;
    }

    @GetMapping
    public List<DetectionResponse> listAll() {
        return detectionService.findAll();
    }

    @GetMapping("/{id}")
    public DetectionResponse getById(@PathVariable String id) {
        return detectionService.findById(id);
    }

    // ── New: SUMO vehicle-count event ─────────────────────────────────────────

    /**
     * Receives a vehicle-count event from ai-services, persists it to MongoDB,
     * and returns the saved document.
     *
     * @param request the deserialized payload from ai-services
     * @return HTTP 201 with the saved {@link VehicleCountEvent}
     */
    @PostMapping("/vehicle-count")
    @ResponseStatus(HttpStatus.CREATED)
    public VehicleCountEvent saveVehicleCount(
            @Valid @RequestBody VehicleCountEventRequest request) {
        return vehicleCountService.save(request);
    }

    /**
     * Returns the 20 most recent vehicle-count events (newest first).
     *
     * @return HTTP 200 with a list of {@link VehicleCountEvent}
     */
    @GetMapping("/vehicle-count/latest")
    public List<VehicleCountEvent> getLatestVehicleCounts() {
        return vehicleCountService.getLatest();
    }
}
