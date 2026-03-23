// backend-services/src/main/java/com/traffic/backend_services/infrastructure/VehicleCountRepository.java
package com.traffic.backend_services.infrastructure;

import com.traffic.backend_services.domain.VehicleCountEvent;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;

/**
 * Spring Data MongoDB repository for {@link VehicleCountEvent}.
 */
public interface VehicleCountRepository
        extends MongoRepository<VehicleCountEvent, String> {

    /**
     * Returns the 20 most recent vehicle-count events ordered by
     * descending timestamp (most recent first).
     */
    List<VehicleCountEvent> findTop20ByOrderByTimestampDesc();
}
