
import re
from enum import Enum
from typing import NamedTuple, Set

class PlateType(Enum):
    """Enum for classifying Indian license plate types."""
    STANDARD = "Standard"
    BH_SERIES = "Bharat (BH) Series"
    INVALID = "Invalid"

class ValidationResult(NamedTuple):
    """
    A structured result for a plate validation operation.

    Attributes:
        is_valid (bool): True if the plate is a valid format, False otherwise.
        cleaned_plate (str): The corrected and formatted plate string.
        confidence (float): A score from 0.0 to 1.0 indicating the confidence
                            in the validation, where 1.0 is a perfect match.
        plate_type (PlateType): The detected type of the license plate.
    """
    is_valid: bool
    cleaned_plate: str
    confidence: float
    plate_type: PlateType

# Comprehensive set of RTO state/UT codes in India
STATE_CODES: Set[str] = {
    "AN", "AP", "AR", "AS", "BR", "CH", "CG", "DD", "DL", "GA", "GJ", "HR",
    "HP", "JK", "JH", "KA", "KL", "LA", "LD", "MP", "MH", "MN", "ML", "MZ",
    "NL", "OD", "PY", "PB", "RJ", "SK", "TN", "TS", "TR", "UP", "UK", "WB"
}

class PlateValidator:
    """
    Validates and cleans Indian vehicle number plates, supporting standard,
    BH-series, and common OCR error corrections.
    """
    def __init__(self):
        self.char_to_digit = {"O": "0", "I": "1", "Z": "2", "S": "5", "B": "8", "G": "6"}
        self.digit_to_char = {v: k for k, v in self.char_to_digit.items()}

        # Regex for standard plate: LL DD LL DDDD
        self.standard_pattern = re.compile(r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$")
        # Regex for BH-series plate: DD BH DDDD LL
        self.bh_pattern = re.compile(r"^\d{2}BH\d{4}[A-Z]{2}$")

    def _clean_input(self, plate: str) -> str:
        """Strips whitespace and converts to uppercase."""
        return "".join(filter(str.isalnum, plate)).upper()

    def _correct_char(self, char: str, expected_type: str) -> tuple[str, bool]:
        """
        Corrects a single character based on expected type (alpha/numeric)
        and returns the corrected character and whether a correction was made.
        """
        corrected = False
        if expected_type == 'alpha' and char.isdigit():
            if char in self.digit_to_char:
                return self.digit_to_char[char], True
        elif expected_type == 'numeric' and char.isalpha():
            if char in self.char_to_digit:
                return self.char_to_digit[char], True
        return char, corrected

    def validate(self, plate: str) -> ValidationResult:
        """
        Validates a raw license plate string.

        Args:
            plate (str): The raw OCR output of the license plate.

        Returns:
            ValidationResult: A named tuple containing the validation outcome.
        """
        cleaned_plate = self._clean_input(plate)
        if len(cleaned_plate) != 10:
            return ValidationResult(False, cleaned_plate, 0.0, PlateType.INVALID)

        # --- Try BH Series Validation ---
        # Structure: 22 BH 1234 AA
        is_potential_bh = cleaned_plate[2:4] == "BH" and \
                          cleaned_plate[:2].isdigit() and \
                          cleaned_plate[4:8].isdigit()

        if is_potential_bh:
            corrected_list = list(cleaned_plate)
            corrections = 0
            # Year (Digits)
            for i in range(2):
                corrected_char, corrected = self._correct_char(corrected_list[i], 'numeric')
                if corrected: corrections += 1
                corrected_list[i] = corrected_char
            # Serial Number (Digits)
            for i in range(4, 8):
                corrected_char, corrected = self._correct_char(corrected_list[i], 'numeric')
                if corrected: corrections += 1
                corrected_list[i] = corrected_char
            # Suffix (Letters)
            for i in range(8, 10):
                corrected_char, corrected = self._correct_char(corrected_list[i], 'alpha')
                if corrected: corrections += 1
                corrected_list[i] = corrected_char

            final_plate = "".join(corrected_list)
            if self.bh_pattern.match(final_plate):
                confidence = max(0, 1.0 - (corrections * 0.1))
                return ValidationResult(True, final_plate, confidence, PlateType.BH_SERIES)

        # --- Try Standard Plate Validation ---
        # Structure: MH 12 AB 1234
        corrected_list = list(cleaned_plate)
        corrections = 0
        # State Code (Letters)
        for i in range(2):
            corrected_char, corrected = self._correct_char(corrected_list[i], 'alpha')
            if corrected: corrections += 1
            corrected_list[i] = corrected_char
        # District Code (Digits)
        for i in range(2, 4):
            corrected_char, corrected = self._correct_char(corrected_list[i], 'numeric')
            if corrected: corrections += 1
            corrected_list[i] = corrected_char
        # Series (Letters)
        for i in range(4, 6):
            corrected_char, corrected = self._correct_char(corrected_list[i], 'alpha')
            if corrected: corrections += 1
            corrected_list[i] = corrected_char
        # Serial Number (Digits)
        for i in range(6, 10):
            corrected_char, corrected = self._correct_char(corrected_list[i], 'numeric')
            if corrected: corrections += 1
            corrected_list[i] = corrected_char

        final_plate = "".join(corrected_list)
        
        # Final check on state code and overall pattern
        if final_plate[:2] in STATE_CODES and self.standard_pattern.match(final_plate):
            confidence = max(0, 1.0 - (corrections * 0.1))
            return ValidationResult(True, final_plate, confidence, PlateType.STANDARD)

        # If all validations fail
        return ValidationResult(False, cleaned_plate, 0.0, PlateType.INVALID)

# --- Unit Tests ---
import unittest

class TestPlateValidator(unittest.TestCase):
    def setUp(self):
        self.validator = PlateValidator()

    def test_valid_standard_plate(self):
        res = self.validator.validate("MH12AB1234")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.cleaned_plate, "MH12AB1234")
        self.assertEqual(res.confidence, 1.0)
        self.assertEqual(res.plate_type, PlateType.STANDARD)

    def test_valid_bh_series_plate(self):
        res = self.validator.validate("22BH1234AA")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.cleaned_plate, "22BH1234AA")
        self.assertEqual(res.confidence, 1.0)
        self.assertEqual(res.plate_type, PlateType.BH_SERIES)

    def test_standard_plate_with_ocr_errors(self):
        res = self.validator.validate("MH12A8I234") # B->8, 1->I
        self.assertTrue(res.is_valid)
        self.assertEqual(res.cleaned_plate, "MH12AB1234")
        self.assertAlmostEqual(res.confidence, 0.8)
        self.assertEqual(res.plate_type, PlateType.STANDARD)

    def test_bh_series_with_ocr_errors(self):
        res = self.validator.validate("22BHO234A1") # 0->O, I->1
        self.assertTrue(res.is_valid)
        self.assertEqual(res.cleaned_plate, "22BH0234AI")
        self.assertAlmostEqual(res.confidence, 0.8)
        self.assertEqual(res.plate_type, PlateType.BH_SERIES)

    def test_plate_with_spaces_and_lowercase(self):
        res = self.validator.validate("  wb 06 cd 5678  ")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.cleaned_plate, "WB06CD5678")
        self.assertEqual(res.confidence, 1.0)

    def test_invalid_state_code(self):
        res = self.validator.validate("XX12AB1234")
        self.assertFalse(res.is_valid)
        self.assertEqual(res.plate_type, PlateType.INVALID)

    def test_invalid_format_too_short(self):
        res = self.validator.validate("MH12AB123")
        self.assertFalse(res.is_valid)
        self.assertEqual(res.cleaned_plate, "MH12AB123")

    def test_invalid_format_mixed_up(self):
        res = self.validator.validate("1234MH12AB")
        self.assertFalse(res.is_valid)

    def test_ev_plate_suffix_handling(self):
        # Assuming EV markings are non-alphanumeric or handled before this stage
        res = self.validator.validate("DL3CAW5678-EV")
        self.assertTrue(res.is_valid)
        self.assertEqual(res.cleaned_plate, "DL3CAW5678")

    def test_correction_logic_alpha_to_numeric(self):
        res = self.validator.validate("MHIZABIZOS") # I,Z,O,S should become 1,2,0,5
        self.assertTrue(res.is_valid)
        self.assertEqual(res.cleaned_plate, "MH12AB1205")
        self.assertAlmostEqual(res.confidence, 0.6)

    def test_correction_logic_numeric_to_alpha(self):
        res = self.validator.validate("M812A81234") # 8 should become B, 1 should become I
        self.assertTrue(res.is_valid)
        self.assertEqual(res.cleaned_plate, "MB12AB1234")
        self.assertAlmostEqual(res.confidence, 0.8)

if __name__ == '__main__':
    unittest.main()
