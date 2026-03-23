// backend-services/src/main/java/com/traffic/backend_services/api/dto/LiveUpdateDTO.java
package com.traffic.backend_services.api.dto;

import java.util.List;

/**
 * Payload pushed over WebSocket to /topic/live every 2 seconds.
 */
public record LiveUpdateDTO(
        List<DetectionDTO>      detections,
        VehicleCountSummaryDTO  vehicleCount,
        DashboardStatsDTO       stats,
        SignalDecisionSummaryDTO signalDecision
) {}
