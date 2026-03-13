package com.traffic.backend_services.api;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * Inbound DTO for creating a new detection event.
 *
 * <p>The {@code timestamp} field is optional; the service will default it to
 * {@code LocalDateTime.now()} when absent.</p>
 */
@Data
public class DetectionRequest {

    @NotBlank(message = "plateNumber is required")
    private String plateNumber;

    @NotBlank(message = "vehicleType is required")
    private String vehicleType;

    @NotBlank(message = "locationId is required")
    private String locationId;

    /** ISO-8601 timestamp string (optional). */
    private String timestamp;
}
