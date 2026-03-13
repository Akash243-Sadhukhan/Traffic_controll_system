package com.traffic.backend_services.api;

import com.traffic.backend_services.service.DetectionService;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * REST controller for traffic detection events.
 *
 * <p>Endpoints:
 * <ul>
 *   <li>{@code POST   /api/detections}       — create a new detection</li>
 *   <li>{@code GET    /api/detections}        — list all detections</li>
 *   <li>{@code GET    /api/detections/{id}}   — get a single detection</li>
 * </ul>
 */
@RestController
@RequestMapping("/api/detections")
@CrossOrigin(origins = "*")
public class DetectionController {

    private final DetectionService service;
    private final SimpMessagingTemplate messagingTemplate;

    public DetectionController(DetectionService service,
                               @Autowired(required = false) SimpMessagingTemplate messagingTemplate) {
        this.service = service;
        this.messagingTemplate = messagingTemplate;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public DetectionResponse create(@Valid @RequestBody DetectionRequest request) {
        DetectionResponse response = service.create(request);

        // Push to WebSocket dashboard in real‑time (if WebSocket is configured)
        if (messagingTemplate != null) {
            messagingTemplate.convertAndSend("/topic/live-traffic", response);
        }

        return response;
    }

    @GetMapping
    public List<DetectionResponse> listAll() {
        return service.findAll();
    }

    @GetMapping("/{id}")
    public DetectionResponse getById(@PathVariable String id) {
        return service.findById(id);
    }
}
