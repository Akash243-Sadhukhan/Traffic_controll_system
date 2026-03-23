// backend-services/src/main/java/com/traffic/backend_services/api/dto/SignalDecisionSummaryDTO.java
package com.traffic.backend_services.api.dto;

import java.util.List;

/**
 * Summary of the latest RL signal decision for the live dashboard.
 */
public record SignalDecisionSummaryDTO(
        String greenArm,
        int    phaseDuration,
        double confidence,
        boolean fallbackUsed,
        String reasoning,
        List<Double> allQValues
) {}
