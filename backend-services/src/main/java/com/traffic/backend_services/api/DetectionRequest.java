package com.traffic.backend_services.api;

import com.traffic.backend_services.validation.PlateNumber;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;
import java.time.LocalDateTime;

/**
 * Inbound DTO for creating a new detection event.
 */
@Data
public class DetectionRequest {

    @NotBlank(message = "plateNumber is required")
    @PlateNumber
    private String plateNumber;

    @NotNull(message = "timestamp is required")
    private LocalDateTime timestamp;

    @NotBlank(message = "vehicleType is required")
    private String vehicleType;

    @NotBlank(message = "locationId is required")
    private String locationId;
}
