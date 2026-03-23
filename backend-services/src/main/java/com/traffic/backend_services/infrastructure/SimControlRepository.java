// backend-services/src/main/java/com/traffic/backend_services/infrastructure/SimControlRepository.java
package com.traffic.backend_services.infrastructure;

import com.traffic.backend_services.domain.SimControlCommand;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.Optional;

public interface SimControlRepository extends MongoRepository<SimControlCommand, String> {

    Optional<SimControlCommand> findTopByAcknowledgedFalseOrderByIssuedAtDesc();
}
