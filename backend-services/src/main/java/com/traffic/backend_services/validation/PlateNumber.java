package com.traffic.backend_services.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Custom validation annotation to check if a string conforms to a valid
 * Indian license plate format (standard or BH-series).
 */
@Constraint(validatedBy = PlateNumberValidator.class)
@Target({ ElementType.METHOD, ElementType.FIELD, ElementType.PARAMETER })
@Retention(RetentionPolicy.RUNTIME)
public @interface PlateNumber {
    String message() default "Invalid license plate format";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
