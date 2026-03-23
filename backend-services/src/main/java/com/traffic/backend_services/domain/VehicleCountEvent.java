// backend-services/src/main/java/com/traffic/backend_services/domain/VehicleCountEvent.java
package com.traffic.backend_services.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * MongoDB document that stores a single vehicle-count event forwarded
 * by ai-services from the SUMO simulation.
 */
@Document(collection = "vehicle_count_events")
public class VehicleCountEvent {

    @Id
    private String id;

    private String intersectionId;
    private int    timestamp;
    private Map<String, Integer> armCounts;
    private int    totalVehicles;
    private String mostCongestedArm;
    private String mode;
    private String source;
    private LocalDateTime createdAt = LocalDateTime.now();

    // ── No-arg constructor (required by Spring Data) ─────────────────────────
    public VehicleCountEvent() {}

    // ── Getters ──────────────────────────────────────────────────────────────
    public String getId()                        { return id; }
    public String getIntersectionId()            { return intersectionId; }
    public int    getTimestamp()                 { return timestamp; }
    public Map<String, Integer> getArmCounts()   { return armCounts; }
    public int    getTotalVehicles()             { return totalVehicles; }
    public String getMostCongestedArm()          { return mostCongestedArm; }
    public String getMode()                      { return mode; }
    public String getSource()                    { return source; }
    public LocalDateTime getCreatedAt()          { return createdAt; }

    // ── Setters ──────────────────────────────────────────────────────────────
    public void setId(String id)                                    { this.id = id; }
    public void setIntersectionId(String intersectionId)            { this.intersectionId = intersectionId; }
    public void setTimestamp(int timestamp)                         { this.timestamp = timestamp; }
    public void setArmCounts(Map<String, Integer> armCounts)        { this.armCounts = armCounts; }
    public void setTotalVehicles(int totalVehicles)                 { this.totalVehicles = totalVehicles; }
    public void setMostCongestedArm(String mostCongestedArm)        { this.mostCongestedArm = mostCongestedArm; }
    public void setMode(String mode)                                { this.mode = mode; }
    public void setSource(String source)                            { this.source = source; }
    public void setCreatedAt(LocalDateTime createdAt)               { this.createdAt = createdAt; }
}
