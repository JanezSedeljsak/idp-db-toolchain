import pytest

from scripts import seed as seed_data


def test_integration_profile_is_deterministic() -> None:
    assert seed_data.INTEGRATION_COUNTS["users"] == 5
    assert seed_data.INTEGRATION_RNG_SEED == 42
