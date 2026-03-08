package com.traffic.backend_services.Entity;

import lombok.Data;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import java.time.LocalDateTime;

@Data
@Document(collection = "traffic_logs")
public class Detection {
    @Id
    private String id;
    private String plateNumber;   // Stabilized text from OCR
    private String vehicleType;   // Car, Truck, etc.
    private String locationId;    // e.g., "Intersection_01"
    private LocalDateTime timestamp;
    private boolean isViolation;  // Logic for restricted zones
}