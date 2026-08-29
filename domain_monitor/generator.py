"""
Domain Name Generator.
Generates smart candidate domain combinations and variations based on user names,
surnames, keywords, and categorized TLDs with configurable inclusion/exclusion rules.
"""

import unicodedata
from typing import Dict, List, Optional, Set, Tuple


def normalize_text(text: str) -> str:
    """Normalize text: lowercase, remove accents and special characters."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ASCII", "ignore").decode("utf-8")
    cleaned = "".join(c for c in ascii_text.lower() if c.isalnum() or c == "-")
    return cleaned.strip("-")


class DomainGenerator:
    """
    Generates tailored domain suggestions based on names, surnames, and configurable filters.
    """

    DEFAULT_TLD_CATEGORIES = {
        "personal": ["es", "com", "net", "me", "eu", "co"],
        "developer": ["dev", "io", "app", "tech", "ai", "cloud", "digital", "page", "sh"],
        "modern": ["xyz", "link", "online", "site"],
    }

    def __init__(
        self,
        first_name: str = "carlos",
        last_name1: str = "diaz",
        last_name2: str = "garcia",
        additional_keywords: Optional[List[str]] = None,
        custom_tlds: Optional[List[str]] = None,
        excluded_tlds: Optional[List[str]] = None,
        excluded_slugs: Optional[List[str]] = None,
        excluded_domains: Optional[List[str]] = None,
        include_full_name: bool = False,
        include_single_names: bool = True,
        include_first_name_only: bool = True,
        include_surname_only: bool = False,
        include_first_and_last: bool = True,
        include_second_surname: bool = False,
        include_hyphenated: bool = True,
        include_initials: bool = False,
    ):
        self.first_name = normalize_text(first_name)
        self.last_name1 = normalize_text(last_name1)
        self.last_name2 = normalize_text(last_name2)
        self.additional_keywords = [
            normalize_text(k) for k in (additional_keywords or []) if k
        ]
        self.custom_tlds = [
            t.lstrip(".").lower() for t in (custom_tlds or []) if t
        ]
        self.excluded_tlds = set(
            t.lstrip(".").lower() for t in (excluded_tlds or []) if t
        )
        self.excluded_slugs = set(
            normalize_text(s) for s in (excluded_slugs or []) if s
        )
        self.excluded_domains = set(
            d.strip().lower() for d in (excluded_domains or []) if d
        )
        self.include_full_name = include_full_name
        self.include_single_names = include_single_names
        self.include_first_name_only = include_first_name_only
        self.include_surname_only = include_surname_only
        self.include_first_and_last = include_first_and_last
        self.include_second_surname = include_second_surname
        self.include_hyphenated = include_hyphenated
        self.include_initials = include_initials

    def get_slug_combinations(self) -> Dict[str, List[str]]:
        """Builds grouped slug combinations according to configuration toggles."""
        fn = self.first_name
        ln1 = self.last_name1
        ln2 = self.last_name2

        high_slugs: List[str] = []
        medium_slugs: List[str] = []
        low_slugs: List[str] = []

        # 1. Single core name/surname slugs (Highest value)
        if self.include_single_names:
            if fn and self.include_first_name_only:
                high_slugs.append(fn)  # carlos
            if ln1 and self.include_surname_only:
                high_slugs.append(ln1)  # diaz

        # 2. First name + First surname
        if self.include_first_and_last and fn and ln1:
            high_slugs.append(f"{fn}{ln1}")  # carlosdiaz
            if self.include_hyphenated:
                medium_slugs.append(f"{fn}-{ln1}")  # carlos-diaz
            if self.include_initials:
                medium_slugs.append(f"{fn[0]}{ln1}")  # cdiaz

        # 3. Full name: First + LN1 + LN2 (Only if enabled)
        if self.include_full_name and fn and ln1 and ln2:
            high_slugs.append(f"{fn}{ln1}{ln2}")  # carlosdiazgarcia
            if self.include_hyphenated:
                medium_slugs.append(f"{fn}-{ln1}-{ln2}")  # carlos-diaz-garcia
            if self.include_initials:
                medium_slugs.append(f"{fn[0]}{ln1}{ln2}")  # cdiazgarcia
                medium_slugs.append(f"{fn[0]}{ln1[0]}{ln2}")  # cdgarcia

        # 4. First name + Second surname (optional)
        if self.include_second_surname and fn and ln2 and not self.include_full_name:
            if self.include_first_and_last:
                medium_slugs.append(f"{fn}{ln2}")  # carlosgarcia
                if self.include_hyphenated:
                    medium_slugs.append(f"{fn}-{ln2}")  # carlos-garcia

        # 5. Keywords + Name combinations (e.g. carlosdev, carlostech, etc.)
        for kw in self.additional_keywords:
            if fn:
                low_slugs.append(f"{fn}{kw}")
                if self.include_hyphenated:
                    low_slugs.append(f"{fn}-{kw}")
            if ln1:
                low_slugs.append(f"{ln1}{kw}")

        # Filter out excluded slugs
        def filter_slugs(slug_list: List[str]) -> List[str]:
            res = []
            for s in slug_list:
                if s not in self.excluded_slugs:
                    # check if any excluded slug substring matches exactly
                    if not any(exc == s for exc in self.excluded_slugs):
                        res.append(s)
            return list(dict.fromkeys(res))

        return {
            "high": filter_slugs(high_slugs),
            "medium": filter_slugs(medium_slugs),
            "low": filter_slugs(low_slugs),
        }

    def generate_domains(
        self,
        tlds: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        include_priorities: Tuple[str, ...] = ("high", "medium"),
    ) -> List[Tuple[str, str]]:
        """
        Generate a list of (domain, priority) tuples applying TLD filtering and exclusions.
        """
        active_tlds: Set[str] = set()

        if tlds:
            for t in tlds:
                clean_t = t.lstrip(".").lower()
                if clean_t not in self.excluded_tlds:
                    active_tlds.add(clean_t)

        if categories:
            for cat in categories:
                if cat in self.DEFAULT_TLD_CATEGORIES:
                    for t in self.DEFAULT_TLD_CATEGORIES[cat]:
                        if t not in self.excluded_tlds:
                            active_tlds.add(t)

        if not active_tlds:
            # Use custom TLDs or personal category
            if self.custom_tlds:
                for t in self.custom_tlds:
                    if t not in self.excluded_tlds:
                        active_tlds.add(t)
            else:
                for t in self.DEFAULT_TLD_CATEGORIES["personal"]:
                    if t not in self.excluded_tlds:
                        active_tlds.add(t)

        slug_groups = self.get_slug_combinations()
        domains_with_priority: List[Tuple[str, str]] = []
        seen: Set[str] = set()

        prime_tlds = {"es", "com", "dev", "me", "io", "ai", "app"}

        for priority in include_priorities:
            slugs = slug_groups.get(priority, [])
            for slug in slugs:
                for tld in active_tlds:
                    domain = f"{slug}.{tld}"
                    if domain not in seen and tld not in self.excluded_tlds and domain not in self.excluded_domains:
                        seen.add(domain)
                        item_priority = priority
                        if priority == "high" and tld in prime_tlds:
                            item_priority = "high"
                        elif priority == "high" and tld not in prime_tlds:
                            item_priority = "medium"
                        domains_with_priority.append((domain, item_priority))

        return domains_with_priority

    def generate_flat_list(
        self,
        tlds: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        include_priorities: Tuple[str, ...] = ("high", "medium"),
    ) -> List[str]:
        """Returns just the list of domain strings."""
        return [d[0] for d in self.generate_domains(tlds, categories, include_priorities)]
