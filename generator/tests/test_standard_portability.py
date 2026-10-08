"""Diagnostics for platform-dependent standard metadata, without relaxing proof checks."""
import math
import unittest

from generator.production.verification import _first_metadata_difference


class StandardMetadataDiagnosticsTests(unittest.TestCase):
    def test_exact_float_difference_identifies_the_leaf(self):
        saved = 9.507467369019215
        fresh = math.nextafter(saved, -math.inf)
        difference = _first_metadata_difference({'rating': saved}, {'rating': fresh})
        self.assertEqual(difference, f'$.rating: saved {saved!r}; fresh {fresh!r}')

    def test_proof_differences_are_diagnostic_and_type_sensitive(self):
        self.assertEqual(_first_metadata_difference({'proof': [True]}, {'proof': [1]}),
                         '$.proof[0]: saved True; fresh 1')
        self.assertEqual(_first_metadata_difference({'proof': [1]}, {'proof': [1, 2]}),
                         '$.proof: saved length 1; fresh length 2')
        self.assertIsNone(_first_metadata_difference({'a': 1}, {'a': 1}))


if __name__ == '__main__':
    unittest.main()
