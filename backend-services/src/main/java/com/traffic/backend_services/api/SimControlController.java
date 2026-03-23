// backend-services/src/main/java/com/traffic/backend_services/api/SimControlController.java
package com.traffic.backend_services.api;

import com.traffic.backend_services.domain.SimControlCommand;
import com.traffic.backend_services.infrastructure.SimControlRepository;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.Set;

/**
 * REST endpoints for controlling the running SUMO simulation.
 * The simulation polls GET /api/sim/commands/latest every N steps.
 */
@RestController
@RequestMapping("/api/sim")
@CrossOrigin("*")
public class SimControlController {

    private static final Set<String> VALID_MODES = Set.of("FIXED", "ADAPTIVE", "RL");

    private final SimControlRepository repo;

    public SimControlController(SimControlRepository repo) {
        this.repo = repo;
    }

    // ── Request records ───────────────────────────────────────────────────────

    public record SpawnRateRequest(int rate) {}
    public record SetModeRequest(String mode) {}

    // ── Command helpers ───────────────────────────────────────────────────────

    private SimControlCommand save(String action, Integer value, String stringValue) {
        SimControlCommand cmd = new SimControlCommand();
        cmd.setAction(action);
        cmd.setValue(value);
        cmd.setStringValue(stringValue);
        cmd.setSource("dashboard");
        cmd.setIssuedAt(LocalDateTime.now());
        cmd.setAcknowledged(false);
        return repo.save(cmd);
    }

    // ── Endpoints ─────────────────────────────────────────────────────────────

    @PostMapping("/spawn-rate")
    public ResponseEntity<?> setSpawnRate(@RequestBody SpawnRateRequest req) {
        if (req.rate() < 5 || req.rate() > 60) {
            return ResponseEntity.badRequest()
                    .body("rate must be between 5 and 60, got: " + req.rate());
        }
        save("SET_SPAWN_RATE", req.rate(), null);
        return ResponseEntity.ok(new CommandResponse(true, req.rate(), null));
    }

    @PostMapping("/spawn-emergency")
    public ResponseEntity<CommandResponse> spawnEmergency() {
        save("SPAWN_EMERGENCY", null, null);
        return ResponseEntity.ok(new CommandResponse(true, null, null));
    }

    @PostMapping("/spawn-flagged")
    public ResponseEntity<CommandResponse> spawnFlagged() {
        save("SPAWN_FLAGGED", null, null);
        return ResponseEntity.ok(new CommandResponse(true, null, null));
    }

    @PostMapping("/reset")
    public ResponseEntity<CommandResponse> reset() {
        save("RESET_SPAWN_RATE", null, null);
        return ResponseEntity.ok(new CommandResponse(true, null, null));
    }

    @PostMapping("/set-mode")
    public ResponseEntity<?> setMode(@RequestBody SetModeRequest req) {
        if (req.mode() == null || !VALID_MODES.contains(req.mode().toUpperCase())) {
            return ResponseEntity.badRequest()
                    .body("mode must be one of: " + VALID_MODES);
        }
        save("SET_MODE", null, req.mode().toUpperCase());
        return ResponseEntity.ok(new CommandResponse(true, null, req.mode().toUpperCase()));
    }

    @GetMapping("/commands/latest")
    public ResponseEntity<SimControlCommand> latestCommand() {
        return repo.findTopByAcknowledgedFalseOrderByIssuedAtDesc()
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.noContent().build());
    }

    @DeleteMapping("/commands/latest")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void acknowledgeLatest() {
        repo.findTopByAcknowledgedFalseOrderByIssuedAtDesc()
                .ifPresent(cmd -> {
                    cmd.setAcknowledged(true);
                    repo.save(cmd);
                });
    }

    private record CommandResponse(boolean accepted, Integer rate, String mode) {}
}
