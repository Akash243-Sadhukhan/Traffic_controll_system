// backend-services/src/main/java/com/traffic/backend_services/service/VehicleCountService.java
package com.traffic.backend_services.service;

import com.traffic.backend_services.api.dto.VehicleCountEventRequest;
import com.traffic.backend_services.domain.VehicleCountEvent;
import com.traffic.backend_services.infrastructure.VehicleCountRepository;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Business-logic service for vehicle-count events.
 *
 * <ul>
 *   <li>{@link #save} — map DTO → document and persist to MongoDB.</li>
 *   <li>{@link #getLatest} — return the 20 most recent events.</li>
 * </ul>
 */
@Service
public class VehicleCountService {

    private final VehicleCountRepository repository;

    public VehicleCountService(VehicleCountRepository repository) {
        this.repository = repository;
    }

    /**
     * Persist a new vehicle-count event.
     *
     * @param req the DTO received from the controller.
     * @return the saved {@link VehicleCountEvent} (with generated id + createdAt).
     */
    public VehicleCountEvent save(VehicleCountEventRequest req) {
        VehicleCountEvent event = new VehicleCountEvent();
        event.setIntersectionId(req.getIntersectionId());
        event.setTimestamp(req.getTimestamp());
        event.setArmCounts(req.getArmCounts());
        event.setTotalVehicles(req.getTotalVehicles());
        event.setMostCongestedArm(req.getMostCongestedArm());
        event.setMode(req.getMode());
        event.setSource(req.getSource());
        event.setCreatedAt(LocalDateTime.now());
        
        System.out.println("\n==================================================");
        System.out.println("✅ BACKEND: Received Vehicle Count Data!");
        System.out.println("   Intersection : " + req.getIntersectionId());
        System.out.println("   Timestamp    : " + req.getTimestamp());
        System.out.println("   Total Count  : " + req.getTotalVehicles());
        System.out.println("   Congested Arm: " + req.getMostCongestedArm());
        System.out.println("==================================================\n");
        
        return repository.save(event);
    }

    /**
     * Retrieve the 20 most recent vehicle-count events (newest first).
     */
    public List<VehicleCountEvent> getLatest() {
        return repository.findTop20ByOrderByTimestampDesc();
    }
}
