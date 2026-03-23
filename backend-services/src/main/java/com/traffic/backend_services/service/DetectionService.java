package com.traffic.backend_services.service;

import com.traffic.backend_services.api.DetectionRequest;
import com.traffic.backend_services.api.DetectionResponse;
import com.traffic.backend_services.domain.Detection;
import com.traffic.backend_services.exception.DetectionNotFoundException;
import com.traffic.backend_services.infrastructure.DetectionRepository;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Core business‑logic layer for traffic detection events.
 *
 * <p>Responsibilities:
 * <ul>
 *   <li>Convert inbound DTOs to domain entities and vice‑versa</li>
 *   <li>Apply business rules (e.g. violation detection)</li>
 *   <li>Delegate persistence to {@link DetectionRepository}</li>
 * </ul>
 */
@Service
public class DetectionService {

    private final DetectionRepository repository;

    public DetectionService(DetectionRepository repository) {
        this.repository = repository;
    }

    // ---- Commands ----

    /**
     * Create a new detection from the inbound request DTO.
     */
    public DetectionResponse create(DetectionRequest request) {
        Detection entity = toEntity(request);

        // Default timestamp if the client didn't supply one
        if (entity.getTimestamp() == null) {
            entity.setTimestamp(LocalDateTime.now());
        }

        // Business rule: trucks in Zone_A are violations
        if ("Truck".equalsIgnoreCase(entity.getVehicleType())
                && "Zone_A".equals(entity.getLocationId())) {
            entity.setViolation(true);
        }

        Detection saved = repository.save(entity);
        return toResponse(saved);
    }

    // ---- Queries ----

    /**
     * Retrieve a single detection by its MongoDB {@code _id}.
     *
     * @throws DetectionNotFoundException if no document matches
     */
    public DetectionResponse findById(String id) {
        Detection entity = repository.findById(id)
                .orElseThrow(() -> new DetectionNotFoundException(id));
        return toResponse(entity);
    }

    /**
     * Return every detection in the collection (newest first).
     */
    public List<DetectionResponse> findAll() {
        return repository.findAll().stream()
                .map(this::toResponse)
                .toList();
    }

    // ---- Mappers ----

    private Detection toEntity(DetectionRequest req) {
        Detection d = new Detection();
        d.setPlateNumber(req.getPlateNumber());
        d.setVehicleType(req.getVehicleType());
        d.setLocationId(req.getLocationId());

        if (req.getTimestamp() != null) {
            d.setTimestamp(req.getTimestamp());
        }
        return d;
    }

    private DetectionResponse toResponse(Detection d) {
        return DetectionResponse.builder()
                .id(d.getId())
                .plateNumber(d.getPlateNumber())
                .vehicleType(d.getVehicleType())
                .locationId(d.getLocationId())
                .timestamp(d.getTimestamp())
                .violation(d.isViolation())
                .build();
    }
}
