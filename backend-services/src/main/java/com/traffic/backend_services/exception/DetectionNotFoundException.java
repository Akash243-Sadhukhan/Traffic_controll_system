package com.traffic.backend_services.exception;

/**
 * Thrown when a {@link com.traffic.backend_services.domain.Detection} cannot
 * be found by the requested identifier.
 */
public class DetectionNotFoundException extends RuntimeException {

    public DetectionNotFoundException(String id) {
        super("Detection not found with id: " + id);
    }
}
