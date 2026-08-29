"""
Tests for Domain Generator.
"""

import unittest
from domain_monitor.generator import DomainGenerator, normalize_text


class TestDomainGenerator(unittest.TestCase):

    def test_normalize_text(self):
        self.assertEqual(normalize_text("García"), "garcia")
        self.assertEqual(normalize_text("Díaz"), "diaz")
        self.assertEqual(normalize_text("Carlos-Alex"), "carlos-alex")

    def test_generate_slugs_default_filters(self):
        gen = DomainGenerator(
            "carlos",
            "diaz",
            "garcia",
            include_full_name=False,
            include_surname_only=True,
            include_initials=True,
            include_hyphenated=True,
        )
        slugs = gen.get_slug_combinations()

        self.assertIn("carlos", slugs["high"])
        self.assertIn("diaz", slugs["high"])
        self.assertIn("carlosdiaz", slugs["high"])
        self.assertNotIn("carlosdiazgarcia", slugs["high"])
        self.assertIn("carlos-diaz", slugs["medium"])
        self.assertIn("cdiaz", slugs["medium"])

    def test_generate_slugs_with_full_name(self):
        gen = DomainGenerator("carlos", "diaz", "garcia", include_full_name=True)
        slugs = gen.get_slug_combinations()
        self.assertIn("carlosdiazgarcia", slugs["high"])

    def test_generate_domains_with_tld_exclusions(self):
        gen = DomainGenerator(
            "carlos",
            "diaz",
            "garcia",
            include_surname_only=True,
            excluded_tlds=["cat", "org"],
            excluded_slugs=["carlosdiazgarcia"],
        )
        domains = gen.generate_domains(tlds=["es", "com", "cat", "org", "dev"])
        flat_list = [d[0] for d in domains]

        self.assertIn("carlos.es", flat_list)
        self.assertIn("carlos.com", flat_list)
        self.assertIn("carlos.dev", flat_list)
        self.assertIn("diaz.es", flat_list)
        self.assertIn("carlosdiaz.es", flat_list)
        # Excluded TLDs and slugs should not be present
        self.assertNotIn("carlos.cat", flat_list)
        self.assertNotIn("carlos.org", flat_list)
        self.assertNotIn("carlosdiazgarcia.com", flat_list)


if __name__ == "__main__":
    unittest.main()
