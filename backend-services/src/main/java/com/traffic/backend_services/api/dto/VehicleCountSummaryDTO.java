// backend-services/src/main/java/com/traffic/backend_services/api/dto/VehicleCountSummaryDTO.java
package com.traffic.backend_services.api.dto;

import java.util.Map;

/**
 * Lightweight summary of a VehicleCountEvent for the live dashboard.
 */
public record VehicleCountSummaryDTO(
        String intersectionId,
        int    timestamp,
        Map<String, Integer> armCounts,
        int    totalVehicles,
        String mostCongestedArm,
        String mode
) {}
