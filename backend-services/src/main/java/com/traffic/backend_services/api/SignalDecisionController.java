// backend-services/src/main/java/com/traffic/backend_services/api/SignalDecisionController.java
package com.traffic.backend_services.api;

import com.traffic.backend_services.api.dto.SignalDecisionSummaryDTO;
import com.traffic.backend_services.domain.SignalDecision;
import com.traffic.backend_services.infrastructure.SignalDecisionRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * REST endpoints for RL signal decisions.
 */
@RestController
@RequestMapping("/api/signal-decisions")
@CrossOrigin("*")
public class SignalDecisionController {

    private final SignalDecisionRepository repo;

    public SignalDecisionController(SignalDecisionRepository repo) {
        this.repo = repo;
    }

    // ── Request body record (mirrors Python SignalDecisionResponse) ───────────
    public record SignalDecisionRequest(
            String intersectionId,
            int    timestamp,
            String greenArm,
            int    phaseDuration,
            int    actionId,
            double confidence,
            List<Double> allQValues,
            boolean fallbackUsed,
            String reasoning
    ) {}

    // ── Stats response record ─────────────────────────────────────────────────
    public record SignalDecisionStatsDTO(
            long   totalDecisions,
            long   fallbackCount,
            double modelUsageRate,
            String mostFrequentGreenArm,
            double avgPhaseDuration,
            double avgConfidence
    ) {}

    // ── Endpoints ─────────────────────────────────────────────────────────────

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public SignalDecision create(@RequestBody SignalDecisionRequest req) {
        SignalDecision doc = new SignalDecision();
        doc.setIntersectionId(req.intersectionId());
        doc.setTimestamp(req.timestamp());
        doc.setGreenArm(req.greenArm());
        doc.setPhaseDuration(req.phaseDuration());
        doc.setActionId(req.actionId());
        doc.setConfidence(req.confidence());
        doc.setAllQValues(req.allQValues());
        doc.setFallbackUsed(req.fallbackUsed());
        doc.setReasoning(req.reasoning());
        doc.setReceivedAt(LocalDateTime.now());
        return repo.save(doc);
    }

    @GetMapping("/latest")
    public List<SignalDecision> latest() {
        return repo.findTop50ByOrderByTimestampDesc();
    }

    @GetMapping("/stats")
    public SignalDecisionStatsDTO stats() {
        long total     = repo.count();
        long fallbacks = repo.countByFallbackUsedTrue();
        double usageRate = total == 0 ? 0.0 : ((double)(total - fallbacks) / total) * 100.0;

        List<SignalDecision> recent = repo.findTop50ByOrderByTimestampDesc();

        String mostFreqArm = recent.stream()
                .collect(Collectors.groupingBy(SignalDecision::getGreenArm, Collectors.counting()))
                .entrySet().stream()
                .max(Map.Entry.comparingByValue())
                .map(Map.Entry::getKey)
                .orElse("none");

        double avgDuration = recent.stream()
                .mapToInt(SignalDecision::getPhaseDuration)
                .average().orElse(0.0);

        double avgConf = recent.stream()
                .mapToDouble(SignalDecision::getConfidence)
                .average().orElse(0.0);

        return new SignalDecisionStatsDTO(total, fallbacks, usageRate,
                mostFreqArm, avgDuration, avgConf);
    }
}
