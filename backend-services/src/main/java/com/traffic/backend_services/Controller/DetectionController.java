package com.traffic.backend_services.Controller;

import com.traffic.backend_services.Entity.Detection;
import com.traffic.backend_services.Services.DetectionService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/detections")
@CrossOrigin(origins = "*") // Allows Python script to connect easily
public class DetectionController {

    @Autowired
    private DetectionService service;

    @Autowired
    private SimpMessagingTemplate messagingTemplate;

    @PostMapping
    public Detection handleNewDetection(@RequestBody Detection detection) {
        // 1. Process and Save to MongoDB
        Detection savedData = service.processDetection(detection);

        // 2. Push to WebSocket Dashboard
        messagingTemplate.convertAndSend("/topic/live-traffic", savedData);

        return savedData;
    }
}