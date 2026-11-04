import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "prepublish_audit.py"
SPEC = importlib.util.spec_from_file_location("prepublish_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_audit_blocks_secrets_and_private_data(tmp_path) -> None:
    fake_key = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    assignment = "API" + "_KEY" + " = " + repr(fake_key)
    (tmp_path / "app.py").write_text(assignment, encoding="utf-8")
    (tmp_path / "users.parquet").write_bytes(b"private")
    findings = MODULE.audit(tmp_path)
    codes = {finding.code for finding in findings}
    assert "openai_like_key" in codes
    assert "private_data_file" in codes


def test_audit_allows_small_clean_source(tmp_path) -> None:
    (tmp_path / "app.py").write_text("print('safe')", encoding="utf-8")
    import json
    digest = "a" * 20 + "138" + "12345678" + "b" * 33
    (tmp_path / "PACKAGE_MANIFEST.json").write_text(json.dumps([{"sha256": digest}], indent=2), encoding="utf-8")
    assert MODULE.audit(tmp_path) == []
    (tmp_path / "notes.txt").write_text("contact: " + "138" + "12345678", encoding="utf-8")
    assert "cn_mobile" in {x.code for x in MODULE.audit(tmp_path)}


def test_public_data_exception_is_path_and_content_specific(tmp_path):
    from causalops.sample_data import wine_example
    raw,_=wine_example()
    target=tmp_path/'src/causalops/sample_data/winequality-red.csv'
    target.parent.mkdir(parents=True)
    target.write_bytes(raw)
    assert MODULE.audit(tmp_path)==[]
    target.write_bytes(raw+b'\n')
    assert 'private_data_file' in {x.code for x in MODULE.audit(tmp_path)}
    target.write_bytes(raw)
    (tmp_path/'users.csv').write_bytes(raw)
    assert 'private_data_file' in {x.code for x in MODULE.audit(tmp_path)}


def test_credentials_still_block_outside_transport_fixture(tmp_path):
    # Generate an inert provider-shaped value only inside the temporary audit tree.
    from secrets import token_hex

    target = tmp_path / "config.py"
    target.write_text("{} = {!r}".format("secret", "sk-" + token_hex(16)), encoding="utf-8")
    hits = {(f.code, f.severity, f.path) for f in MODULE.audit(tmp_path)}
    assert ("assigned_secret", "blocker", target.name) in hits
    assert ("openai_like_key", "blocker", target.name) in hits
