// backend-services/src/main/java/com/traffic/backend_services/infrastructure/SignalDecisionRepository.java
package com.traffic.backend_services.infrastructure;

import com.traffic.backend_services.domain.SignalDecision;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;

public interface SignalDecisionRepository extends MongoRepository<SignalDecision, String> {

    List<SignalDecision> findTop50ByOrderByTimestampDesc();

    List<SignalDecision> findByIntersectionIdOrderByTimestampDesc(
            String intersectionId, Pageable pageable);

    long countByFallbackUsedTrue();

    /** For "most frequent green arm" aggregation — returns all decisions. */
    List<SignalDecision> findAllByOrderByTimestampDesc(Pageable pageable);
}
