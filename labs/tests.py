from django.test import SimpleTestCase

from .middleware import lab_slug_from_host

SUFFIXES = [".lab.compile.cl", ".localhost"]


class LabSlugFromHostTests(SimpleTestCase):
    def test_subdomain(self):
        self.assertEqual(lab_slug_from_host("biodata.lab.compile.cl", SUFFIXES), "biodata")

    def test_localhost_subdomain_with_port(self):
        self.assertEqual(lab_slug_from_host("biodata.localhost:8000", SUFFIXES), "biodata")

    def test_bare_host(self):
        self.assertIsNone(lab_slug_from_host("lab.compile.cl", SUFFIXES))
        self.assertIsNone(lab_slug_from_host("localhost:8000", SUFFIXES))
