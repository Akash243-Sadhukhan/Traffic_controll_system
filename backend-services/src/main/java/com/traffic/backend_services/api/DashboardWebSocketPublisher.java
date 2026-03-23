// backend-services/src/main/java/com/traffic/backend_services/api/DashboardWebSocketPublisher.java
package com.traffic.backend_services.api;

import com.traffic.backend_services.api.dto.*;
import com.traffic.backend_services.domain.SignalDecision;
import com.traffic.backend_services.domain.VehicleCountEvent;
import com.traffic.backend_services.infrastructure.DetectionRepository;
import com.traffic.backend_services.infrastructure.SignalDecisionRepository;
import com.traffic.backend_services.infrastructure.SimControlRepository;
import com.traffic.backend_services.infrastructure.VehicleCountRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Pushes a live snapshot to WebSocket clients every 2 seconds.
 * Subscribers listen on /topic/live.
 */
@Component
public class DashboardWebSocketPublisher {

    private final SimpMessagingTemplate ws;
    private final DetectionRepository     detectionRepo;
    private final VehicleCountRepository  vehicleCountRepo;
    private final SignalDecisionRepository signalRepo;
    private final SimControlRepository    simControlRepo;

    public DashboardWebSocketPublisher(
            SimpMessagingTemplate ws,
            DetectionRepository detectionRepo,
            VehicleCountRepository vehicleCountRepo,
            SignalDecisionRepository signalRepo,
            SimControlRepository simControlRepo) {
        this.ws               = ws;
        this.detectionRepo    = detectionRepo;
        this.vehicleCountRepo = vehicleCountRepo;
        this.signalRepo       = signalRepo;
        this.simControlRepo   = simControlRepo;
    }

    @Scheduled(fixedRate = 2000)
    public void pushLiveUpdate() {
        // 1. Latest 10 detections
        List<DetectionDTO> detections = detectionRepo
                .findAll(PageRequest.of(0, 10)).stream()
                .map(DashboardController::toDto)
                .collect(Collectors.toList());

        // 2. Latest vehicle count event
        VehicleCountSummaryDTO vehicleCount = vehicleCountRepo
                .findTop20ByOrderByTimestampDesc().stream()
                .findFirst()
                .map(v -> new VehicleCountSummaryDTO(
                        v.getIntersectionId(), v.getTimestamp(), v.getArmCounts(),
                        v.getTotalVehicles(), v.getMostCongestedArm(), v.getMode()))
                .orElse(null);

        // 3. Latest RL signal decision
        SignalDecisionSummaryDTO signalDecision = signalRepo
                .findTop50ByOrderByTimestampDesc().stream()
                .findFirst()
                .map(sd -> new SignalDecisionSummaryDTO(
                        sd.getGreenArm(), sd.getPhaseDuration(), sd.getConfidence(),
                        sd.isFallbackUsed(), sd.getReasoning(), sd.getAllQValues()))
                .orElse(null);

        // 4. Stats
        long total       = detectionRepo.count();
        long countEvents = vehicleCountRepo.count();
        long decisions   = signalRepo.count();
        long fallbacks   = signalRepo.countByFallbackUsedTrue();
        double usage     = decisions == 0 ? 0.0
                : ((double)(decisions - fallbacks) / decisions) * 100.0;

        String mostCongested = vehicleCount != null ? vehicleCount.mostCongestedArm() : "—";
        int spawnRate = simControlRepo
                .findTopByAcknowledgedFalseOrderByIssuedAtDesc()
                .filter(c -> "SET_SPAWN_RATE".equals(c.getAction()) && c.getValue() != null)
                .map(c -> c.getValue())
                .orElse(20);

        String mode = signalDecision != null
                ? (signalDecision.fallbackUsed() ? "ADAPTIVE" : "RL")
                : "FIXED";

        DashboardStatsDTO statsDto = new DashboardStatsDTO(
                total, countEvents, decisions, usage,
                mostCongested, spawnRate, mode, 0.0, 0.0, LocalDateTime.now());

        LiveUpdateDTO payload = new LiveUpdateDTO(
                detections, vehicleCount, statsDto, signalDecision);

        ws.convertAndSend("/topic/live", payload);
    }
}
