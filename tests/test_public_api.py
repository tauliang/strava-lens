import unittest

class PublicAPITests(unittest.TestCase):
    def test_standalone_exports(self):
        from strava_lens_parser import inspect_export, iter_export, __version__
        self.assertTrue(callable(inspect_export))
        self.assertTrue(callable(iter_export))
        self.assertEqual(__version__, '0.1.0')
