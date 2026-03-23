// backend-services/src/main/java/com/traffic/backend_services/api/DashboardController.java
package com.traffic.backend_services.api;

import com.traffic.backend_services.api.dto.*;
import com.traffic.backend_services.domain.Detection;
import com.traffic.backend_services.domain.SignalDecision;
import com.traffic.backend_services.domain.SimControlCommand;
import com.traffic.backend_services.domain.VehicleCountEvent;
import com.traffic.backend_services.infrastructure.DetectionRepository;
import com.traffic.backend_services.infrastructure.SignalDecisionRepository;
import com.traffic.backend_services.infrastructure.SimControlRepository;
import com.traffic.backend_services.infrastructure.VehicleCountRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

/**
 * REST endpoints powering the live React dashboard.
 */
@RestController
@RequestMapping("/api/dashboard")
@CrossOrigin("*")
public class DashboardController {

    private final DetectionRepository     detectionRepo;
    private final VehicleCountRepository  vehicleCountRepo;
    private final SignalDecisionRepository signalRepo;
    private final SimControlRepository    simControlRepo;

    public DashboardController(
            DetectionRepository detectionRepo,
            VehicleCountRepository vehicleCountRepo,
            SignalDecisionRepository signalRepo,
            SimControlRepository simControlRepo) {
        this.detectionRepo    = detectionRepo;
        this.vehicleCountRepo = vehicleCountRepo;
        this.signalRepo       = signalRepo;
        this.simControlRepo   = simControlRepo;
    }

    // ── Detections ────────────────────────────────────────────────────────────

    @GetMapping("/detections/live")
    public List<DetectionDTO> liveDetections() {
        // Use findAll with PageRequest since Detection has no timestamp index sorting yet
        return detectionRepo.findAll(PageRequest.of(0, 50)).stream()
                .sorted((a, b) -> {
                    if (a.getTimestamp() == null) return 1;
                    if (b.getTimestamp() == null) return -1;
                    return b.getTimestamp().compareTo(a.getTimestamp());
                })
                .map(d -> new DetectionDTO(
                        d.getId(),
                        d.getPlateNumber(),
                        d.getVehicleType(),
                        d.getLocationId(),
                        d.getTimestamp(),
                        d.isViolation()    // violation → flagged
                ))
                .collect(Collectors.toList());
    }

    // ── Vehicle counts ────────────────────────────────────────────────────────

    @GetMapping("/vehicle-counts/live")
    public List<VehicleCountSummaryDTO> liveVehicleCounts() {
        return vehicleCountRepo.findTop20ByOrderByTimestampDesc().stream()
                .map(v -> new VehicleCountSummaryDTO(
                        v.getIntersectionId(),
                        v.getTimestamp(),
                        v.getArmCounts(),
                        v.getTotalVehicles(),
                        v.getMostCongestedArm(),
                        v.getMode()
                ))
                .collect(Collectors.toList());
    }

    // ── Aggregated stats ──────────────────────────────────────────────────────

    @GetMapping("/stats")
    public DashboardStatsDTO stats() {
        long totalDetections     = detectionRepo.count();
        long totalCountEvents    = vehicleCountRepo.count();
        long totalSignalDecisions = signalRepo.count();
        long fallbacks           = signalRepo.countByFallbackUsedTrue();
        double modelUsageRate    = totalSignalDecisions == 0 ? 0.0
                : ((double)(totalSignalDecisions - fallbacks) / totalSignalDecisions) * 100.0;

        // Latest congestion info
        String mostCongested = vehicleCountRepo.findTop20ByOrderByTimestampDesc()
                .stream().findFirst()
                .map(VehicleCountEvent::getMostCongestedArm)
                .orElse("unknown");

        // Latest sim command for spawn rate
        int spawnRate = simControlRepo.findTopByAcknowledgedFalseOrderByIssuedAtDesc()
                .filter(cmd -> "SET_SPAWN_RATE".equals(cmd.getAction()) && cmd.getValue() != null)
                .map(SimControlCommand::getValue)
                .orElse(20);

        // Active mode (from latest SET_MODE command if any)
        String activeMode = signalRepo.findTop50ByOrderByTimestampDesc()
                .stream().findFirst()
                .map(sd -> {
                    // Infer mode from fallback flag
                    return sd.isFallbackUsed() ? "ADAPTIVE" : "RL";
                })
                .orElse("FIXED");

        return new DashboardStatsDTO(
                totalDetections, totalCountEvents, totalSignalDecisions, modelUsageRate,
                mostCongested, spawnRate, activeMode, 0.0, 0.0, LocalDateTime.now()
        );
    }

    // ── Helper: map Detection to DetectionDTO ─────────────────────────────────
    static DetectionDTO toDto(Detection d) {
        return new DetectionDTO(
                d.getId(), d.getPlateNumber(), d.getVehicleType(),
                d.getLocationId(), d.getTimestamp(), d.isViolation());
    }
}
