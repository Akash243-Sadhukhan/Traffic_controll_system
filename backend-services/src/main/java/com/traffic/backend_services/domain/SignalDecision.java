// backend-services/src/main/java/com/traffic/backend_services/domain/SignalDecision.java
package com.traffic.backend_services.domain;

import lombok.Data;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.LocalDateTime;
import java.util.List;

/**
 * MongoDB document representing one RL signal controller decision.
 */
@Data
@Document(collection = "signal_decisions")
public class SignalDecision {

    @Id
    private String id;

    private String intersectionId;
    private int    timestamp;
    private String greenArm;
    private int    phaseDuration;
    private int    actionId;
    private double confidence;
    private List<Double> allQValues;
    private boolean fallbackUsed;
    private String reasoning;
    private LocalDateTime receivedAt = LocalDateTime.now();
}
