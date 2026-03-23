// backend-services/src/main/java/com/traffic/backend_services/api/dto/VehicleCountEventRequest.java
package com.traffic.backend_services.api.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

/**
 * DTO that mirrors the JSON body sent by ai-services to
 * {@code POST /api/detections/vehicle-count}.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class VehicleCountEventRequest {

    private String intersectionId;
    private int    timestamp;
    private Map<String, Integer> armCounts;
    private int    totalVehicles;
    private String mostCongestedArm;
    private String mode;
    private String source;
}
