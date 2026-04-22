import importlib
import os
import unittest
from unittest import mock


def _reload():
    import briarwood.feature_flags as ff
    return importlib.reload(ff)


class FeatureFlagTests(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BRIARWOOD_CLAIMS_ENABLED", None)
            os.environ.pop("BRIARWOOD_CLAIMS_PROPERTY_IDS", None)
            ff = _reload()
            self.assertFalse(ff.CLAIMS_ENABLED)
            self.assertFalse(ff.claims_enabled_for("any-id"))
            self.assertFalse(ff.claims_enabled_for(None))

    def test_enabled_globally_when_allowlist_empty(self) -> None:
        with mock.patch.dict(os.environ, {"BRIARWOOD_CLAIMS_ENABLED": "true"}, clear=False):
            os.environ.pop("BRIARWOOD_CLAIMS_PROPERTY_IDS", None)
            ff = _reload()
            self.assertTrue(ff.CLAIMS_ENABLED)
            self.assertTrue(ff.claims_enabled_for("prop-1"))
            self.assertTrue(ff.claims_enabled_for(None))

    def test_allowlist_gates_properties(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "BRIARWOOD_CLAIMS_ENABLED": "1",
                "BRIARWOOD_CLAIMS_PROPERTY_IDS": "prop-1, prop-2",
            },
            clear=False,
        ):
            ff = _reload()
            self.assertEqual(ff.CLAIMS_PROPERTY_IDS, frozenset({"prop-1", "prop-2"}))
            self.assertTrue(ff.claims_enabled_for("prop-1"))
            self.assertTrue(ff.claims_enabled_for("prop-2"))
            self.assertFalse(ff.claims_enabled_for("prop-3"))
            self.assertFalse(ff.claims_enabled_for(None))

    def test_env_bool_accepts_common_truthy_values(self) -> None:
        from briarwood.feature_flags import _env_bool
        for val in ("1", "true", "TRUE", "yes", "on", " on "):
            with mock.patch.dict(os.environ, {"X": val}):
                self.assertTrue(_env_bool("X"), msg=val)
        for val in ("0", "false", "no", "off", ""):
            with mock.patch.dict(os.environ, {"X": val}):
                self.assertFalse(_env_bool("X"), msg=val)

    def test_env_bool_missing_uses_default(self) -> None:
        from briarwood.feature_flags import _env_bool
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("X", None)
            self.assertFalse(_env_bool("X"))
            self.assertTrue(_env_bool("X", default=True))

    def test_env_set_ignores_empty_and_whitespace(self) -> None:
        from briarwood.feature_flags import _env_set
        with mock.patch.dict(os.environ, {"X": " a ,, b,c "}):
            self.assertEqual(_env_set("X"), frozenset({"a", "b", "c"}))
        with mock.patch.dict(os.environ, {"X": ""}):
            self.assertEqual(_env_set("X"), frozenset())

    def tearDown(self) -> None:
        os.environ.pop("BRIARWOOD_CLAIMS_ENABLED", None)
        os.environ.pop("BRIARWOOD_CLAIMS_PROPERTY_IDS", None)
        _reload()


if __name__ == "__main__":
    unittest.main()
