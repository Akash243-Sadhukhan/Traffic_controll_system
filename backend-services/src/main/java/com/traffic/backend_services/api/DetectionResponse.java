package com.traffic.backend_services.api;

import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * Outbound DTO returned to clients after a detection is created or queried.
 */
@Data
@Builder
public class DetectionResponse {

    private String id;
    private String plateNumber;
    private String vehicleType;
    private String locationId;
    private LocalDateTime timestamp;
    private boolean violation;
}
