from dataclasses import dataclass
import random
from typing import Tuple

from defs.common_data import months
from defs.function_definitions import _get_company_reference, _cleanup_sentence
from defs.instrument_definitions import BaseNarrativeEvidence, ContextEvidence
from defs.legal_data import states_and_counties

# ========== ABOUT {company} / BUSINESS DESCRIPTION ==========
company_description_templates = {
    "core_identity": [
        "{company}'s principal business activities are in {industry}",
        "{company} operates through these reportable segments: {industry}",
        "{company} is a leading provider of {industry} serving over {small_int} markets",
    ],
    "mission": [
        "{company}'s mission is to {offer_verb} {mission_statement}",
        "{company} is a {industry} company that {offer_verb} {mission_statement}",
    ]
}
offer_verbs = [
    "provides",
    "offers",
    "develops",
    "creates",
    "manufactures",
    "produces",
    "builds",
    "constructs",
]

industries = {
    "technology": {
        "industries": [
            "technology", "software", "semiconductor", "robotics", "artificial intelligence",
            "cybersecurity", "nanotechnology", "digital health", "telemedicine", "healthcare it",
            "hardware", "cloud services", "displays", "memory", "automation", "data analytics",
            "iot", "quantum computing", "nanomaterials", "advanced manufacturing", "information technology"
        ],
        "missions": [
            "technology solutions", "services to enterprise customers", "software applications",
            "semiconductor devices", "integrated circuits", "robotics", "automation technologies",
            "artificial intelligence solutions", "cybersecurity products", "services",
            "financial technology solutions", "platforms", "nanotechnology innovations"
        ]
    },
    "healthcare": {
        "industries": [
            "healthcare", "biotechnology", "pharmaceutical", "medical devices", "diagnostics",
            "contract research organization (cro)", "contract manufacturing organization (cmo)",
            "health insurance", "pharmacy benefits management (pbm)", "hospital management",
            "nursing home", "assisted living", "home healthcare", "medical tourism",
            "gene therapy", "personalized medicine"
        ],
        "missions": [
            "healthcare services", "medical devices", "research", "development of new pharmaceuticals",
            "biotechnology research", "development"
        ]
    },
    "consumer_goods": {
        "industries": [
            "consumer goods", "food and beverage", "fashion", "luxury goods", "personal care",
            "nutrition", "apparel", "footwear", "accessories", "luxury fashion", "jewelry",
            "watches", "home care", "food", "beverage"
        ],
        "missions": [
            "consumer products globally", "food", "beverage products", "fashion apparel",
            "accessories", "luxury goods", "experiences"
        ]
    },
    "energy": {
        "industries": [
            "energy", "utilities", "cleantech", "energy storage", "solar", "wind",
            "generation", "transmission", "distribution"
        ],
        "missions": [
            "energy resources", "clean energy technologies", "energy infrastructure", "utility services", "energy efficiency",
            "renewable energy", "sustainable energy", "clean energy solutions",
            
        ]
    },
    "media_entertainment": {
        "industries": [
            "media", "entertainment", "gaming", "publishing", "sports", "digital media",
            "console gaming", "pc gaming", "mobile gaming", "professional sports",
            "collegiate sports", "esports", "book publishing", "magazine publishing",
            "digital publishing"
        ],
        "missions": [
            "media content", "entertainment", "video games", "interactive entertainment",
            "books", "magazines", "digital content", "sports teams", "leagues", "events"
        ]
    },
    "financial_services": {
        "industries": [
            "financial services", "venture capital", "private equity", "investment banking",
            "asset management", "wealth management", "brokerage", "credit card services",
            "payment processing", "mortgage banking", "commercial banking", "investment management",
            "hedge fund", "mutual fund", "pension fund", "endowment fund", "sovereign wealth fund",
            "family office", "microfinance", "impact investing", "commercial", "consumer",
            "enterprise", "small business", "government", "consulting", "advisory",
            "corporate banking", "fintech", "blockchain", "digital payments", "growth equity",
            "private debt", "buyouts", "distressed investing", "infrastructure funds",
            "mergers & acquisitions", "debt capital markets", "equity capital markets",
            "life", "property & casualty", "reinsurance"
        ],
        "missions": [
            "financial advisory", "wealth management services", "insurance products",
            "risk management solutions", "investment banking", "corporate finance services"
        ]
    },
    "consulting": {
        "industries": [
            "consulting", "human resources", "market research", "outsourcing", "marketing",
            "advertising", "talent acquisition", "hr consulting", "payroll services",
            "consumer research", "b2b research", "corporate law", "intellectual property law",
            "litigation", "crisis communications", "public affairs", "media relations",
            "environmental consulting"
        ],
        "missions": [
            "management consulting", "advisory services", "human resources consulting",
            "talent management", "public relations", "communication strategies", "advertising",
            "marketing services", "market research", "consumer insights analysis",
            "environmental consulting", "remediation services", "legal services", "counsel"
        ]
    },
}


# ========== FORWARD-LOOKING STATEMENTS ==========
forward_looking_templates = [
    "This report contains forward-looking statements within the meaning of the Private Securities Litigation Reform Act of 1995",
    "Forward-looking statements include, but are not limited to, statements regarding {topics}",
    'Words such as "{words}" and similar expressions identify forward-looking statements',
    "These forward-looking statements are subject to risks and uncertainties that could cause actual results to differ materially from those projected",
    "{company} cautions that forward-looking statements are not guarantees of future performance and involve known and unknown risks",
    "{company} undertakes no obligation to update or revise forward-looking statements, whether as a result of new information, future events, or otherwise",
    "Forward-looking statements are based on management\'s current expectations and assumptions as of the date of this report",
    "Factors that could cause actual results to differ from forward-looking statements include {risk_factors}",
    "Investors should not place undue reliance on forward-looking statements, which speak only as of {month} {end_day}, {year}",
    "All forward-looking statements are qualified in their entirety by reference to the risk factors discussed in Item 1A of this report",
]

forward_looking_topics = {
    "financial": [
        "expected financial performance", "capital resources", "financing plans",
        "projected capital expenditures", "cost reduction initiatives", "dividend policy",
        "share repurchase programs", "tax rates", "financial ratios", "debt covenants",
        "credit ratings", "access to capital markets"
    ],
    "strategic": [
        "growth strategies", "market opportunities", "business development initiatives",
        "strategic alliances", "commercialization strategies", "merger and acquisition integration risks",
        "potential acquisitions", "divestitures"
    ],
    "regulatory": [
        "regulatory approvals", "regulatory developments", "compliance matters",
        "regulatory approval processes for new products", "environmental regulations",
        "healthcare reforms", "litigation and regulatory enforcement actions"
    ],
    "market": [
        "expected market conditions", "competitive dynamics", "customer demand",
        "competitive landscape", "market share shifts", "pricing strategies",
        "promotional activities", "seasonality", "cyclicality of business operations"
    ],
    "macroeconomic": [
        "macroeconomic conditions", "geopolitical events", "foreign currency exchange rates",
        "interest rate fluctuations", "public health crises", "pandemics"
    ],
    "operations": [
        "operational improvements", "manufacturing capacity", "production efficiency",
        "quality control", "assurance processes", "inventory management",
        "supply chain optimization", "logistics", "transportation networks"
    ],
    "technology": [
        "technological advancements", "industry trends", "information technology systems",
        "infrastructure", "data analytics", "business intelligence capabilities"
    ],
    "product": [
        "anticipated product launches", "product development lifecycle",
        "innovation pipeline", "product liability", "warranty claims",
        "patent protection", "intellectual property disputes"
    ],
    "research": [
        "research and development outcomes", "clinical trial outcomes",
        "ethical considerations in research and development"
    ],
    "human_capital": [
        "talent acquisition", "retention", "workforce management",
        "executive compensation", "incentive structures"
    ],
    "customer": [
        "customer relationships", "concentration risks", "customer service",
        "support operations", "changes in consumer preferences", "spending patterns"
    ],
    "brand": [
        "brand reputation", "public perception", "marketing", "advertising campaigns"
    ],
    "risk": [
        "cybersecurity risks", "data privacy concerns", "insurance coverage",
        "indemnification arrangements", "catastrophic events", "business continuity plans"
    ],
    "social": [
        "environmental, social, and governance (ESG) initiatives", "social impact",
        "community engagement", "corporate governance", "board oversight",
        "shareholder activism", "investor relations"
    ],
    "healthcare": [
        "reimbursement policies", "drug pricing pressures", "affordability concerns",
        "patient safety", "adverse event reporting"
    ]
}

forward_looking_words = {
    "expect": [
        "expects", "anticipates", "predict", "forecast", "projects", "prognosticate",
        "speculate", "surmise", "hypothesize", "presume", "envision", "foresee",
        "imagine", "contemplate", "extrapolate", "infer", "deduce", "conclude"
    ],
    "intent": [
        "intends", "plans", "propose", "design", "schedule", "endeavor", "strive",
        "aim", "aspire", "pursue", "commit", "dedicate", "pledge", "promise", "guarantee"
    ],
    "belief": [
        "believes", "believe", "trust", "confide", "rely", "depend"
    ],
    "uncertainty": [
        "may", "might", "can", "could", "possibly", "perhaps", "likely", "probable",
        "plausible", "credible", "conceivable", "potential", "prospective", "possible",
        "latent", "inherent"
    ],
    "goal": [
        "targets", "target", "goals", "goal", "objective", "aspiration", "mission", "vision"
    ],
    "plan": [
        "strategy", "tactic", "plan", "approach", "method"
    ],
    "explore": [
        "seek", "seeks", "search", "explore", "investigate", "discover"
    ],
    "evaluate": [
        "estimates", "estimate", "appraise", "assess", "evaluate", "judge"
    ],
    "time": [
        "future", "forthcoming", "upcoming", "impending", "imminent", "continue",
        "persist", "endure", "maintain", "sustain", "outlook", "prospect", "perspective",
        "view", "expectation"
    ],
    "position": [
        "positioned", "situated", "placed", "located", "arranged"
    ],
    "opportunity": [
        "opportunity", "chance", "possibility", "opening", "break", "momentum",
        "impetus", "drive", "thrust", "force", "trajectory", "path", "course", "route", "amount"
    ],
    "modal": [
        "will", "shall", "must", "ought", "should", "would"
    ],
    "guide": [
        "guidance"
    ]
}

risk_factors = {
    "economic": [
        "economic conditions", "interest rate fluctuations", "changes in interest rates",
        "impact of inflation or deflation", "changes in energy costs", "access to capital markets",
        "changes in credit ratings", "decline in market demand for products or services",
        "adverse changes in economic conditions"
    ],
    "regulatory": [
        "regulatory changes", "government regulations", "changes in tax laws",
        "changes in accounting standards", "regulatory compliance costs",
        "unfavorable legal or regulatory outcomes", "changes in government policies or regulations",
        "litigation and regulatory investigations", "environmental regulations"
    ],
    "market": [
        "market volatility", "pricing pressures", "competition from new market entrants",
        "increased competition", "seasonality of business operations", "concentration of customers or suppliers"
    ],
    "operational": [
        "operational challenges", "execution risks", "failure to meet performance expectations",
        "disruptions in supply chain", "disruptions in transportation and logistics",
        "difficulty in integrating acquired businesses", "integration risks associated with mergers and acquisitions"
    ],
    "technology": [
        "technological changes", "failure to adapt to technological advancements",
        "technological obsolescence", "disruptions to information technology systems"
    ],
    "cybersecurity": [
        "cybersecurity threats", "data breaches", "cybersecurity incidents"
    ],
    "legal": [
        "litigation uncertainties", "product liability claims", "warranty obligations",
        "loss of intellectual property protection", "failure to protect intellectual property rights"
    ],
    "personnel": [
        "reliance on key personnel", "inability to attract and retain qualified employees",
        "labor disputes", "workforce availability"
    ],
    "financial": [
        "financing availability", "inability to obtain adequate financing"
    ],
    "consumer": [
        "changes in consumer preferences", "changes in consumer spending patterns",
        "brand reputation", "damage to brand reputation", "adverse publicity or reputational damage",
        "marketing effectiveness"
    ],
    "geopolitical": [
        "geopolitical events", "political instability", "trade policies",
        "geopolitical conflicts", "trade wars", "risks associated with international operations"
    ],
    "environmental": [
        "natural disasters", "climate change", "extreme weather events",
        "public health crises", "pandemics", "other catastrophic events",
        "sustainability initiatives"
    ],
    "product": [
        "product development risks", "challenges in new product development and commercialization",
        "product recalls", "safety concerns", "dependence on key patents or licenses"
    ]
}


safe_harbor_templates = [
    "Statements in this report that are not historical facts constitute forward-looking statements subject to the safe harbor provisions of the Private Securities Litigation Reform Act",
    "{company} includes forward-looking statements to provide investors with its current expectations and projections, but cautions that such statements involve risks",
    "Safe harbor statement: Except for historical information, this report contains forward-looking statements that involve substantial risks and uncertainties",
    "This document contains forward-looking statements that are protected by the safe harbor provisions for such statements",
]

@dataclass
class CompanyDescriptionSentence:
    """Generates contextual sentences about the company's business."""

    company_name: str
    reporting_year: int

    def build(self) -> Tuple[str, ContextEvidence]:
        """Builds a multi-sentence paragraph about the company's business."""
        sentences = []

        # Pick a random industry category
        industry_category = random.choice(list(industries.keys()))
        industry_details = industries[industry_category]

        industry = random.sample(industry_details["industries"], k=random.randint(1, 4))
        mission = random.sample(industry_details["missions"], k=random.randint(1, 4))

        # Choose a template
        template_type = random.choice(list(company_description_templates.keys()))
        template = random.choice(company_description_templates[template_type])

        state_name, city_name = random.choice(states_and_counties)

        placeholders = {
            "company": _get_company_reference(self.company_name),
            "industry": industry[0] if len(industry) == 1 else ", ".join(industry[:len(industry) - 1]) + " and " + industry[-1],
            "mission_statement": mission[0] if len(mission) == 1 else ", ".join(mission[:len(mission) - 1]) + " and " + mission[-1],
            "small_int": random.randint(5, 50),
            "year": self.reporting_year - random.randint(10, 50),
            "city": city_name,
            "state": state_name,
            "integer": f"{random.randint(100, 50000):,}",
            "offer_verb": random.choice(offer_verbs)
        }

        sentence = template.format_map(placeholders)
        sentences.append(_cleanup_sentence(sentence))

        full_paragraph = ". ".join(sentences) + "."
        evidence = ContextEvidence(
            category="GEN", status="context_mention", details=full_paragraph
        )

        return full_paragraph, evidence


@dataclass
class ForwardLookingSentence:
    """Generates a paragraph containing forward-looking statements."""

    company_name: str
    reporting_year: int
    reporting_month: str
    reporting_day: int

    def build(self) -> Tuple[str, ContextEvidence]:
        """Builds a multi-sentence paragraph with forward-looking statements."""
        num_sentences = random.randint(1, 4)
        sentences: list[str] = []

        # Start with a safe harbor statement
        safe_harbor_template = random.choice(safe_harbor_templates)
        sentences.append(_cleanup_sentence(safe_harbor_template))

        # Add other forward-looking statements
        for _ in range(num_sentences):
            template = random.choice(forward_looking_templates)
            placeholders = self._get_placeholders()
            # Avoid repeating the same template structure
            if any(p in template for p in placeholders if p in sentences[-1]):
                template = random.choice(forward_looking_templates)
            
            formatted_sentence = template.format_map(placeholders)
            sentences.append(_cleanup_sentence(formatted_sentence))

        full_paragraph = ". ".join(sentences) + "."
        evidence = ContextEvidence(
            category="GEN", status="context_mention", details=full_paragraph
        )

        return full_paragraph, evidence

    def _get_placeholders(self) -> dict:
        """Helper to generate placeholders for the templates."""
        
        # Generate a list of topics
        num_topics = random.randint(1, 3)
        topics_list = []
        for _ in range(num_topics):
            topic_category = random.choice(list(forward_looking_topics.keys()))
            topics_list.append(random.choice(forward_looking_topics[topic_category]))
        topics_str = ", ".join(topics_list)

        # Generate a list of forward-looking words
        num_words = random.randint(2, 4)
        words_list = []
        for _ in range(num_words):
            word_category = random.choice(list(forward_looking_words.keys()))
            words_list.append(random.choice(forward_looking_words[word_category]))
        words_str = ", ".join(words_list)

        # Generate a list of risk factors
        num_risks = random.randint(2, 4)
        risks_list = []
        for _ in range(num_risks):
            risk_category = random.choice(list(risk_factors.keys()))
            risks_list.append(random.choice(risk_factors[risk_category]))
        risks_str = ", ".join(risks_list)

        return {
            "company": _get_company_reference(self.company_name),
            "year": self.reporting_year,
            "month": self.reporting_month,
            "end_day": self.reporting_day,
            "topics": topics_str,
            "words": words_str,
            "risk_factors": risks_str,
        }
