// backend-services/src/main/java/com/traffic/backend_services/domain/SimControlCommand.java
package com.traffic.backend_services.domain;

import lombok.Data;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.LocalDateTime;

/**
 * MongoDB document representing a dashboard-issued simulation command.
 * The SUMO simulation polls /api/sim/commands/latest to pick these up.
 */
@Data
@Document(collection = "sim_commands")
public class SimControlCommand {

    @Id
    private String id;

    /** Action type: SET_SPAWN_RATE | SPAWN_EMERGENCY | SPAWN_FLAGGED |
     *               RESET_SPAWN_RATE | SET_MODE */
    private String action;

    /** Numeric payload (spawn rate value). Nullable. */
    private Integer value;

    /** String payload (mode name: FIXED | ADAPTIVE | RL). Nullable. */
    private String stringValue;

    /** Always "dashboard" for UI-issued commands. */
    private String source = "dashboard";

    private LocalDateTime issuedAt = LocalDateTime.now();

    /** Set to true after the simulation has read and applied this command. */
    private boolean acknowledged = false;
}
