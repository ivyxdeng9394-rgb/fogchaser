import json
import os
import pytest


def test_manifest_structure():
    """The manifest is the contract between pipeline and frontend.
    If keys change, the frontend breaks silently."""
    manifest_path = "app/data/manifest.json"
    if not os.path.exists(manifest_path):
        pytest.skip("No manifest.json yet — run the pipeline first")

    with open(manifest_path) as f:
        m = json.load(f)

    assert "run_utc" in m, "manifest missing 'run_utc'"
    assert "generated_utc" in m, "manifest missing 'generated_utc'"
    assert "hours" in m, "manifest missing 'hours'"
    assert len(m["hours"]) > 0, "manifest has empty 'hours'"
    for h in m["hours"]:
        assert "fxx" in h and isinstance(h["fxx"], int)
        assert "valid_utc" in h and isinstance(h["valid_utc"], str)
        assert "url" in h  # url may be None for failed hours — that's OK
        assert "approx_asos" in h
