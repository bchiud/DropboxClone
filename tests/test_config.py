"""Unit tests for app/config.py — Settings loading and validation."""
import pytest
from pydantic import ValidationError

from app.config import Settings

# A complete set of the required fields, with dummy values.
REQUIRED = dict(
    mongodb_uri="mongodb+srv://user:pass@host/",
    s3_endpoint_url="https://s3.example.com",
    s3_access_key_id="access-key",
    s3_secret_access_key="secret-key",
    s3_region="us-west-004",
    jwt_secret="a-secret",
)


def test_loads_required_fields():
    s = Settings(_env_file=None, **REQUIRED)
    assert s.mongodb_uri == REQUIRED["mongodb_uri"]
    assert s.s3_access_key_id == "access-key"
    assert s.jwt_secret == "a-secret"


def test_defaults_applied():
    s = Settings(_env_file=None, **REQUIRED)
    assert s.mongodb_db == "dropbox_clone"
    assert s.s3_bucket == "dropbox-clone"
    assert s.block_size == 4 * 1024 * 1024


@pytest.mark.parametrize("missing", sorted(REQUIRED))
def test_missing_any_required_field_raises(missing):
    partial = {k: v for k, v in REQUIRED.items() if k != missing}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **partial)


def test_jwt_secret_has_no_default():
    # Regression: jwt_secret must be required, never fall back to a shipped default.
    partial = {k: v for k, v in REQUIRED.items() if k != "jwt_secret"}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **partial)


def test_block_size_coerced_to_int():
    s = Settings(_env_file=None, **{**REQUIRED, "block_size": "1024"})
    assert s.block_size == 1024
    assert isinstance(s.block_size, int)


def test_extra_env_vars_ignored():
    s = Settings(_env_file=None, **{**REQUIRED, "unrelated_var": "x"})
    assert not hasattr(s, "unrelated_var")
