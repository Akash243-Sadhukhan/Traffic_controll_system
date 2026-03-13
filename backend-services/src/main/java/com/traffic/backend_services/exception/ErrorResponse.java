package com.traffic.backend_services.exception;

import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * Standard JSON error envelope returned by {@link GlobalExceptionHandler}.
 */
@Data
@Builder
public class ErrorResponse {

    private int status;
    private String error;
    private String message;

    @Builder.Default
    private LocalDateTime timestamp = LocalDateTime.now();
}
