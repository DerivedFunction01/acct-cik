import re
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass
from enum import Enum
from defs.regex_lib import build_alternation, YEAR_REGEX

COMPANY_TOKEN = "the Company"

class MinimalTextCleaner:
    def __init__(self):
        # Suffixes to strip from the passed company name
        self.name_suffixes = [
            r"inc\.?", r"corp\.?", r"corporation", r"l\.?l\.?c\.?", 
            r"co\.?", r"company", r"ltd\.?", r"limited", r"p\.?l\.?c\.?", 
            r"s\.?a\.?", r"group", r"holdings?", r"trust", r"assoc\.?", r"association"
        ]
        
        # Suffixes to remove from the text generally (safer subset)
        self.text_suffixes = [
            r"inc\.?", r"corp\.?", r"corporation", r"l\.?l\.?c\.?", 
            r"ltd\.?", r"limited", r"p\.?l\.?c\.?", r"s\.?a\.?"
        ]

        # Regex to strip suffixes from the end of the company name
        self.name_suffix_pattern = re.compile(
            r"\s+" + build_alternation(self.name_suffixes) + r"\.?$", 
            re.IGNORECASE
        )
        
        # Regex to remove safe suffixes from text
        self.text_suffix_pattern = re.compile(
            r"\b" + build_alternation(self.text_suffixes) + r"\b\.?", 
            re.IGNORECASE
        )

        # False Positives for Union/Labor context
        self.false_positives = [
            (re.compile(r"\bcredit\s+unions?\b", re.IGNORECASE), "bank"),
            (re.compile(r"\beuropean\s+union\b", re.IGNORECASE), "Europe"),
            (re.compile(r"\bstate\s+of\s+the\s+union\b", re.IGNORECASE), "speech"),
            (re.compile(r"\bstudent\s+unions?\b", re.IGNORECASE), "student body"),
        ]

        # Date and Year Patterns
        months = [
            "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December",
            "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Sept", "Oct", "Nov", "Dec"
        ]
        self.months_pattern_str = build_alternation(months) + r"[a-z]*\.?"
        
        self.date_md_pattern = re.compile(
            rf"\b(?:{self.months_pattern_str})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,)?(?!\d)", 
            re.IGNORECASE
        )
        
        self.date_dm_pattern = re.compile(
            rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{self.months_pattern_str})\b", 
            re.IGNORECASE
        )
        
        self.month_only_pattern = re.compile(
            rf"\b(?:{self.months_pattern_str})\b", 
            re.IGNORECASE
        )

        self.year_pattern = YEAR_REGEX

        # Word to number mappings
        self.num_words = {
            'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
            'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14,
            'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18,
            'nineteen': 19, 'twenty': 20, 'thirty': 30, 'forty': 40,
            'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80,
            'ninety': 90
        }
        self.multipliers = {
            'hundred': 100,
            'thousand': 1_000,
            'million': 1_000_000,
            'billion': 1_000_000_000,
            'trillion': 1_000_000_000_000
        }
        self.fractions = {
            'half': 0.5, 'halves': 0.5,
            'quarter': 0.25, 'quarters': 0.25,
            'third': 1/3, 'thirds': 1/3,
            'fourth': 0.25, 'fourths': 0.25,
            'fifth': 0.2, 'fifths': 0.2,
            'sixth': 1/6, 'sixths': 1/6,
            'seventh': 1/7, 'sevenths': 1/7,
            'eighth': 1/8, 'eighths': 1/8,
            'ninth': 1/9, 'ninths': 1/9,
            'tenth': 0.1, 'tenths': 0.1
        }
        
        # Build regex for number phrases
        all_words = list(self.num_words.keys()) + list(self.multipliers.keys()) + list(self.fractions.keys())
        word_pattern = build_alternation([re.escape(w) for w in all_words])
        self.number_phrase_pattern = re.compile(
            rf"\b{word_pattern}(?:[\s-]+{word_pattern})*\b",
            re.IGNORECASE
        )

        # Handle "a hundred", "a thousand" etc.
        self.a_multiplier_pattern = re.compile(
            r"\ba\s+(?=(?:hundred|thousand|million|billion|trillion))",
            re.IGNORECASE
        )
        self.percent_pattern = re.compile(r"\bper\s?cent\b", re.IGNORECASE)
        self.percent_space_pattern = re.compile(r"(\d)\s+%", re.IGNORECASE)

        # Numbers
        self.comma_pattern = re.compile(r"(?<=\d),(?=\d{3})")
        self.scale_map = {
            "thousand": 1_000,
            "million": 1_000_000,
            "billion": 1_000_000_000,
            "trillion": 1_000_000_000_000
        }
        self.scale_pattern = re.compile(
            r"\b(\d+(?:\.\d+)?)\s+(thousand|million|billion|trillion)\b", 
            re.IGNORECASE
        )

        self.space_pattern = re.compile(r"\s+")

    def normalize_company_name(self, name: str) -> str:
        if not name:
            return ""
        name = name.strip()
        prev_name = None
        while name != prev_name:
            prev_name = name
            name = self.name_suffix_pattern.sub("", name)
        return name

    def _scale_replacer(self, match):
        try:
            number = float(match.group(1))
            multiplier = self.scale_map.get(match.group(2).lower(), 1)
            value = number * multiplier
            if value.is_integer():
                return f"{int(value)}"
            return f"{value}"
        except ValueError:
            return match.group(0)

    def _parse_number_phrase(self, match):
        text = match.group(0)
        clean_text = text.lower().replace('-', ' ')
        words = clean_text.split()
        
        # If phrase is only multipliers (e.g. "million"), leave it for scale_pattern
        if all(w in self.multipliers for w in words):
            return text
            
        total_value = 0
        current_chunk = 0
        is_fraction = False
        fraction_value = 0.0
        
        for word in words:
            if word in self.num_words:
                current_chunk += self.num_words[word]
            elif word in self.multipliers:
                mult = self.multipliers[word]
                if mult == 100:
                    current_chunk = (current_chunk if current_chunk else 1) * mult
                else:
                    total_value += (current_chunk if current_chunk else 1) * mult
                    current_chunk = 0
            elif word in self.fractions:
                if current_chunk > 0:
                    fraction_value += current_chunk * self.fractions[word]
                    current_chunk = 0
                    is_fraction = True
                elif word in ['half', 'halves']:
                    fraction_value += 0.5
                    is_fraction = True
        
        if is_fraction:
            final_val = total_value + fraction_value
            if final_val == 0: return text
            return f"{final_val * 100:g}%"
            
        total_value += current_chunk
        if total_value == 0 and "zero" not in clean_text:
            return text
        return str(total_value)

    def clean(self, text: str, company_name: Optional[str] = None, reporting_year: Optional[int] = None) -> str:
        if not text:
            return ""
        
        # 1. Whitespace
        text = self.space_pattern.sub(" ", text).strip()

        # 2. False Positives
        for pat, repl in self.false_positives:
            text = pat.sub(repl, text)

        # 3. Company Name
        if company_name:
            core_name = self.normalize_company_name(company_name)
            if len(core_name) > 2:
                escaped_name = re.escape(core_name)
                suffix_regex = r"(?:\s+(?:" + "|".join(self.name_suffixes) + r")\.?)*"
                company_regex = re.compile(rf"\b{escaped_name}{suffix_regex}\b", re.IGNORECASE)
                text = company_regex.sub(COMPANY_TOKEN, text)

        # 4. General Suffix Removal
        text = self.text_suffix_pattern.sub("", text)

        # 4b. Date and Year Removal
        text = self.date_md_pattern.sub(" ", text)
        text = self.date_dm_pattern.sub(" ", text)
        text = self.month_only_pattern.sub(" ", text)
        text = self.year_pattern.sub(r" <\1> ", text)

        # 5. Numbers
        text = self.a_multiplier_pattern.sub("one ", text)
        text = self.number_phrase_pattern.sub(self._parse_number_phrase, text)
        text = self.comma_pattern.sub("", text)
        text = self.scale_pattern.sub(self._scale_replacer, text)
        
        # Percent normalization
        text = self.percent_pattern.sub("%", text)
        text = self.percent_space_pattern.sub(r"\1%", text)
        
        # Final cleanup
        text = self.space_pattern.sub(" ", text).strip()
        
        return text


# ============================================================================
# AUTOMATED TEST FRAMEWORK
# ============================================================================

class TestType(Enum):
    """Types of validation tests."""
    CONTAINS = "contains"              # Result must contain string
    NOT_CONTAINS = "not_contains"      # Result must not contain string
    EXACT = "exact"                    # Result must be exact match
    REGEX = "regex"                    # Result must match regex
    LENGTH_LESS = "length_less"        # Result length < expected
    LENGTH_GREATER = "length_greater"  # Result length > expected
    COUNT = "count"                    # Count of pattern occurrences
    PROPERTY = "property"              # Custom property validation


@dataclass
class TestCase:
    """Represents a single test case."""
    name: str
    input_text: str
    company_name: Optional[str] = None
    reporting_year: Optional[int] = None
    validations: Optional[List[Tuple[TestType, str, any]]] = None # type: ignore
    
    def __post_init__(self):
        if self.validations is None:
            self.validations = []


class TestValidator:
    """Validates cleaned text against expected transformations."""
    
    def __init__(self):
        self.cleaner = MinimalTextCleaner()
        self.results = []
        self.passed = 0
        self.failed = 0
    
    def add_validation(self, test_case: TestCase, test_type: TestType, 
                      pattern: str, expected_value: Optional[any] = None) -> TestCase: # type: ignore
        """Fluent API to add validation to a test case."""
        if test_case.validations is None:
            test_case.validations = []
        test_case.validations.append((test_type, pattern, expected_value))
        return test_case
    
    def run_test(self, test_case: TestCase) -> Dict:
        """Run a single test case and return results."""
        result = {
            "name": test_case.name,
            "input": test_case.input_text,
            "company_name": test_case.company_name,
            "output": None,
            "passed": True,
            "validations": []
        }
        
        # Clean the text
        output = self.cleaner.clean(
            test_case.input_text,
            test_case.company_name,
            test_case.reporting_year
        )
        result["output"] = output
        
        assert test_case.validations is not None
        # Run all validations
        for test_type, pattern, expected_value in test_case.validations:
            validation_result = self._validate(output, test_type, pattern, expected_value)
            result["validations"].append(validation_result)
            
            if not validation_result["passed"]:
                result["passed"] = False
        
        return result
    
    def _validate(self, text: str, test_type: TestType, pattern: str, 
                  expected_value: any) -> Dict: # type: ignore
        """Execute a single validation."""
        validation = {
            "type": test_type.value,
            "pattern": pattern,
            "passed": False,
            "message": ""
        }
        
        try:
            if test_type == TestType.CONTAINS:
                passed = pattern in text
                validation["passed"] = passed
                validation["message"] = f"{'✓' if passed else '✗'} Contains '{pattern}'"
            
            elif test_type == TestType.NOT_CONTAINS:
                passed = pattern not in text
                validation["passed"] = passed
                validation["message"] = f"{'✓' if passed else '✗'} Does not contain '{pattern}'"
            
            elif test_type == TestType.EXACT:
                passed = text == pattern
                validation["passed"] = passed
                validation["message"] = f"{'✓' if passed else '✗'} Exact match"
                if not passed:
                    validation["message"] += f"\nExpected: {pattern}\nGot: {text}"
            
            elif test_type == TestType.REGEX:
                passed = bool(re.search(pattern, text))
                validation["passed"] = passed
                validation["message"] = f"{'✓' if passed else '✗'} Matches regex '{pattern}'"
            
            elif test_type == TestType.LENGTH_LESS:
                passed = len(text) < expected_value
                validation["passed"] = passed
                validation["message"] = f"{'✓' if passed else '✗'} Length {len(text)} < {expected_value}"
            
            elif test_type == TestType.LENGTH_GREATER:
                passed = len(text) > expected_value
                validation["passed"] = passed
                validation["message"] = f"{'✓' if passed else '✗'} Length {len(text)} > {expected_value}"
            
            elif test_type == TestType.COUNT:
                count = len(re.findall(pattern, text, re.IGNORECASE))
                passed = count == expected_value
                validation["passed"] = passed
                validation["message"] = f"{'✓' if passed else '✗'} Pattern count: {count} (expected {expected_value})"
            
        except Exception as e:
            validation["passed"] = False
            validation["message"] = f"✗ Error: {str(e)}"
        
        return validation
    
    def run_all_tests(self, test_cases: List[TestCase]) -> bool:
        """Run all test cases and print results."""
        self.results = []
        self.passed = 0
        self.failed = 0
        
        print("\n" + "="*80)
        print("AUTOMATED TEXT CLEANER TEST SUITE")
        print("="*80 + "\n")
        
        for test_case in test_cases:
            result = self.run_test(test_case)
            self.results.append(result)
            
            # Count pass/fail
            if result["passed"]:
                self.passed += 1
                status = "✓ PASSED"
            else:
                self.failed += 1
                status = "✗ FAILED"
            
            # Print test header
            print(f"{status} | {result['name']}")
            print("-" * 80)
            
            # Print input/output
            print(f"Input: {result['input'][:100]}..." if len(result['input']) > 100 else f"Input: {result['input']}")
            print(f"Output: {result['output'][:100]}..." if len(result['output']) > 100 else f"Output: {result['output']}")
            
            # Print validation details
            if result['validations']:
                print("\nValidations:")
                for v in result['validations']:
                    print(f"  {v['message']}")
            
            print()
        
        # Summary
        print("="*80)
        print(f"SUMMARY: {self.passed} passed, {self.failed} failed out of {len(test_cases)} tests")
        print("="*80 + "\n")
        
        return self.failed == 0


# ============================================================================
# TEST CASES
# ============================================================================

def create_test_cases() -> List[TestCase]:
    """Create comprehensive test cases."""
    return [
        # Test 1: Company Name Replacement
        TestCase(
            name="Company Name Replacement",
            input_text="Johnson & Johnson Corporation is a leading company. Johnson & Johnson was founded long ago.",
            company_name="Johnson & Johnson Corporation",
            validations=[
                (TestType.CONTAINS, "the Company", None),
                (TestType.COUNT, r"the Company", 2),
                (TestType.NOT_CONTAINS, "Johnson & Johnson Corporation", None),
            ]
        ),
        
        # Test 2: Date Removal (Month Day format)
        TestCase(
            name="Date Removal - Month Day Format",
            input_text="As of December 31, 2023, we had significant growth.",
            validations=[
                (TestType.NOT_CONTAINS, "December 31", None),
                (TestType.CONTAINS, "we had significant growth", None),
            ]
        ),
        
        # Test 3: Date Removal (Day Month format)
        TestCase(
            name="Date Removal - Day Month Format",
            input_text="On the 15th of July, we announced new products.",
            validations=[
                (TestType.NOT_CONTAINS, "15th of July", None),
                (TestType.CONTAINS, "we announced new products", None),
            ]
        ),
        
        # Test 4: Year Wrapping
        TestCase(
            name="Year Wrapping",
            input_text="In 2023 and 1999, we made significant investments.",
            validations=[
                (TestType.CONTAINS, "<2023>", None),
                (TestType.CONTAINS, "<1999>", None),
            ]
        ),
        
        # Test 5: Word Numbers to Digits
        TestCase(
            name="Word Numbers to Digits",
            input_text="We have five million dollars and two thousand employees.",
            validations=[
                (TestType.CONTAINS, "5000000", None),
                (TestType.CONTAINS, "2000", None),
                (TestType.NOT_CONTAINS, "five million", None),
                (TestType.NOT_CONTAINS, "two thousand", None),
            ]
        ),
        
        # Test 6: Fraction to Percentage
        TestCase(
            name="Fraction to Percentage",
            input_text="Approximately three-fourths of our staff are satisfied.",
            validations=[
                (TestType.CONTAINS, "75%", None),
                (TestType.NOT_CONTAINS, "three-fourths", None),
            ]
        ),
        
        # Test 7: Scale Numbers (numbers with scale words)
        TestCase(
            name="Scale Numbers",
            input_text="We invested 2 million dollars and earned 500 thousand dollars.",
            validations=[
                (TestType.CONTAINS, "2000000", None),
                (TestType.CONTAINS, "500000", None),
            ]
        ),
        
        # Test 8: Comma Removal in Numbers
        TestCase(
            name="Comma Removal",
            input_text="The company has 138,100 employees worldwide.",
            validations=[
                (TestType.CONTAINS, "138100", None),
                (TestType.NOT_CONTAINS, "138,100", None),
            ]
        ),
        
        # Test 9: Suffix Removal
        TestCase(
            name="Suffix Removal",
            input_text="Our subsidiaries include ABC Inc., XYZ Corp., and 123 Ltd.",
            validations=[
                (TestType.NOT_CONTAINS, "Inc.", None),
                (TestType.NOT_CONTAINS, "Corp.", None),
                (TestType.NOT_CONTAINS, "Ltd.", None),
            ]
        ),
        
        # Test 10: False Positive Prevention (Credit Union)
        TestCase(
            name="False Positive - Credit Union",
            input_text="We have partnerships with credit unions and banks.",
            validations=[
                (TestType.CONTAINS, "bank", None),
                (TestType.NOT_CONTAINS, "union", None),
            ]
        ),
        
        # Test 11: False Positive Prevention (European Union)
        TestCase(
            name="False Positive - European Union",
            input_text="The European Union has strict regulations.",
            validations=[
                (TestType.CONTAINS, "Europe", None),
                (TestType.NOT_CONTAINS, "European Union", None),
            ]
        ),
        
        # Test 12: Percent Normalization
        TestCase(
            name="Percent Normalization",
            input_text="Sales increased by 25 % and costs rose 10 per cent.",
            validations=[
                (TestType.NOT_CONTAINS, "25 %", None),
                (TestType.CONTAINS, "25%", None),
                (TestType.NOT_CONTAINS, "per cent", None),
                (TestType.CONTAINS, "10%", None),
            ]
        ),
        
        # Test 13: Whitespace Normalization
        TestCase(
            name="Whitespace Normalization",
            input_text="The   company   has   multiple    spaces   between    words.",
            validations=[
                (TestType.NOT_CONTAINS, "   ", None),
                (TestType.CONTAINS, "The company has multiple spaces between words", None),
            ]
        ),
        
        # Test 14: Month-only Removal
        TestCase(
            name="Month Only Removal",
            input_text="In January we launched products, and in February we expanded.",
            validations=[
                (TestType.NOT_CONTAINS, "January", None),
                (TestType.NOT_CONTAINS, "February", None),
                (TestType.CONTAINS, "we launched products", None),
            ]
        ),
        
        # Test 15: Complex Text (Integration)
        TestCase(
            name="Complex Integration Test",
            input_text="Apple Inc. reported 138,100 employees on December 31, 2023. Approximately one half of staff work in the European Union earning five million dollars per year at 25 percent bonus.",
            company_name="Apple Inc.",
            validations=[
                (TestType.CONTAINS, "the Company", None),
                (TestType.CONTAINS, "138100", None),
                (TestType.CONTAINS, "<2023>", None),
                (TestType.NOT_CONTAINS, "December 31", None),
                (TestType.CONTAINS, "50%", None),
                (TestType.CONTAINS, "Europe", None),
                (TestType.CONTAINS, "5000000", None),
                (TestType.CONTAINS, "25%", None),
            ]
        ),
        
        # Test 16: Edge case - Empty string
        TestCase(
            name="Edge Case - Empty String",
            input_text="",
            validations=[
                (TestType.EXACT, "", None),
            ]
        ),
        
        # Test 17: Edge case - No changes needed
        TestCase(
            name="Edge Case - No Changes",
            input_text="The business operates in multiple countries.",
            validations=[
                (TestType.CONTAINS, "The business operates", None),
            ]
        ),
    ]


def run_tests():
    """Run the test suite."""
    test_cases = create_test_cases()
    validator = TestValidator()
    all_passed = validator.run_all_tests(test_cases)
    
    return 0 if all_passed else 1
