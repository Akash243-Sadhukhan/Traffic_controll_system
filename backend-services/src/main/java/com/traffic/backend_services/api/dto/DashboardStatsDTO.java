// backend-services/src/main/java/com/traffic/backend_services/api/dto/DashboardStatsDTO.java
package com.traffic.backend_services.api.dto;

import java.time.LocalDateTime;

/**
 * Aggregated stats snapshot for the dashboard header metrics.
 */
public record DashboardStatsDTO(
        long   totalDetections,
        long   totalVehicleCountEvents,
        long   totalSignalDecisions,
        double modelUsageRate,           // percentage of non-fallback decisions
        String mostCongestedArm,
        int    currentSpawnRate,
        String activeMode,               // FIXED | ADAPTIVE | RL
        double avgWaitFixed,
        double avgWaitAdaptive,
        LocalDateTime lastUpdated
) {}
