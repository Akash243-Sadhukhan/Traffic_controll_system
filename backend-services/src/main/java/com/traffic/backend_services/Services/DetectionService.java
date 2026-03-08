package com.traffic.backend_services.Services;

import com.traffic.backend_services.Entity.Detection;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import java.time.LocalDateTime;

@Service
public class DetectionService {
    @Autowired
    private DetectionRepository repository;

    public Detection processDetection(Detection data) {
        if (data.getTimestamp() == null) {
            data.setTimestamp(LocalDateTime.now());
        }
        // Business Logic: Identify violations (Example: Trucks in certain zones)
        if ("Truck".equalsIgnoreCase(data.getVehicleType()) && "Zone_A".equals(data.getLocationId())) {
            data.setViolation(true);
        }
        return repository.save(data);
    }
}
