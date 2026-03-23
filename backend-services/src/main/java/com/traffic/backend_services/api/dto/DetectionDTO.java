// backend-services/src/main/java/com/traffic/backend_services/api/dto/DetectionDTO.java
package com.traffic.backend_services.api.dto;

import java.time.LocalDateTime;

/**
 * Read-only view of a Detection document for the live dashboard.
 */
public record DetectionDTO(
        String id,
        String plateNumber,
        String vehicleType,
        String locationId,
        LocalDateTime timestamp,
        boolean flagged          // true when violation=true on the source document
) {}
