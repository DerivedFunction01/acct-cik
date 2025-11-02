import random


def _get_company_reference(company_name: str, chance: float = 0.25) -> str:
    """Randomly returns either the full company name or a generic placeholder."""
    return company_name if random.random() < chance else "The Company"