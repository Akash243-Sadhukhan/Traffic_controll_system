package com.traffic.backend_services.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import java.util.regex.Pattern;

/**
 * Validates a string against common Indian license plate formats:
 * 1. Standard: 2 letters, 2 digits, 2 letters, 4 digits (e.g., MH12AB1234)
 * 2. BH Series: 2 digits, BH, 4 digits, 2 letters (e.g., 22BH1234AA)
 */
public class PlateNumberValidator implements ConstraintValidator<PlateNumber, String> {

    private static final String STANDARD_PATTERN = "^[A-Z]{2}\\d{2}[A-Z]{2}\\d{4}$";
    private static final String BH_PATTERN = "^\\d{2}BH\\d{4}[A-Z]{2}$";
    private static final Pattern COMPILED_PATTERN = Pattern.compile(STANDARD_PATTERN + "|" + BH_PATTERN);

    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        if (value == null || value.trim().isEmpty()) {
            return true; // Use @NotBlank for empty checks
        }
        return COMPILED_PATTERN.matcher(value).matches();
    }
}
