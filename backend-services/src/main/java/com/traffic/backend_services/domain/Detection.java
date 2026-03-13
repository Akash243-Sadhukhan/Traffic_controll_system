package com.traffic.backend_services.domain;

import lombok.Data;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.LocalDateTime;

/**
 * MongoDB document representing a single traffic detection event.
 */
@Data
@Document(collection = "traffic_logs")
public class Detection {

    @Id
    private String id;

    private String plateNumber;

    private String vehicleType;

    private String locationId;

    private LocalDateTime timestamp;

    private boolean violation;
}
