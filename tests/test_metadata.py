"""Packaging and user-visible flow translation checks."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "digi_ro"


def test_release_manifest():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["version"] == "0.1.21"
    assert manifest["homeassistant"] == "2024.4.0"
    assert manifest["domain"] == "digi_ro" and manifest["config_flow"] is True
    assert json.loads((ROOT / "hacs.json").read_text())["content_in_root"] is False


def test_complete_en_ro_flow_translations():
    expected_steps = {
        "user",
        "reconfigure",
        "reauth_confirm",
        "login",
        "cookie",
        "2fa_method",
        "2fa_code",
        "address_select",
    }
    strings = json.loads((COMPONENT / "strings.json").read_text())["config"]
    for language in ("en", "ro"):
        translations = json.loads(
            (COMPONENT / "translations" / f"{language}.json").read_text()
        )["config"]
        assert set(translations["step"]) == expected_steps
        assert set(translations["error"]) == set(strings["error"])
        assert set(translations["abort"]) == set(strings["abort"])
        for step, contents in strings["step"].items():
            assert set(translations["step"][step]["data"]) == set(contents["data"])
