import re
from typing import Optional

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
            r"\s+(?:" + "|".join(self.name_suffixes) + r")\.?$", 
            re.IGNORECASE
        )
        
        # Regex to remove safe suffixes from text
        self.text_suffix_pattern = re.compile(
            r"\b(?:" + "|".join(self.text_suffixes) + r")\b\.?", 
            re.IGNORECASE
        )

        # False Positives for Union/Labor context
        self.false_positives = [
            (re.compile(r"\bcredit\s+unions?\b", re.IGNORECASE), "bank"),
            (re.compile(r"\beuropean\s+union\b", re.IGNORECASE), "Europe"),
            (re.compile(r"\bstate\s+of\s+the\s+union\b", re.IGNORECASE), "speech"),
            (re.compile(r"\bstudent\s+unions?\b", re.IGNORECASE), "student body"),
        ]

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
        all_words.sort(key=len, reverse=True)
        word_pattern = "|".join(re.escape(w) for w in all_words)
        self.number_phrase_pattern = re.compile(
            rf"\b(?:{word_pattern})(?:[\s-]+(?:{word_pattern}))*\b",
            re.IGNORECASE
        )

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

    def clean(self, text: str, company_name: Optional[str] = None) -> str:
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

        # 5. Numbers
        text = self.number_phrase_pattern.sub(self._parse_number_phrase, text)
        text = self.comma_pattern.sub("", text)
        text = self.scale_pattern.sub(self._scale_replacer, text)
        
        # Final cleanup
        text = self.space_pattern.sub(" ", text).strip()
        
        return text

if __name__ == "__main__":
    cleaner = MinimalTextCleaner()
    
    # Sample Item 1 text (inspired by JNJ)
    sample_text = """
    Johnson & Johnson and its subsidiaries (the Company) have approximately 138,100 employees worldwide engaged 
    in the research and development, manufacture and sale of a broad range of products in the healthcare field. 
    Johnson & Johnson is a holding company, with operating companies conducting business in virtually all countries of the world.
    The Company’s primary focus is products related to human health and well-being. 
    Johnson & Johnson was incorporated in the State of New Jersey in 1887.
    We have 5 million dollars in assets and 2 thousand employees in the European Union.
    Approximately three fourths of our staff are unionized, and fifty five percent are full time.
    """
    
    company_name = "Johnson & Johnson Corporation"
    
    print("-" * 50)
    print(f"Original Text:\n{sample_text.strip()}")
    print("-" * 50)
    print(f"Company Name: {company_name}")
    print("-" * 50)
    
    cleaned_text = cleaner.clean(sample_text, company_name)
    
    print(f"Cleaned Text:\n{cleaned_text}")
    print("-" * 50)