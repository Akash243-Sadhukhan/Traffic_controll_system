package com.traffic.backend_services.infrastructure;

import com.traffic.backend_services.domain.Detection;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;

/**
 * MongoDB repository for {@link Detection} documents.
 */
public interface DetectionRepository extends MongoRepository<Detection, String> {

    List<Detection> findByPlateNumber(String plateNumber);

    List<Detection> findByLocationId(String locationId);
}
