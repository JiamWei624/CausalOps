"""Publication checks do not execute held-out Agent tasks."""
import importlib.util,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
def scanner():
 spec=importlib.util.spec_from_file_location('beta_release_scan',ROOT/'scripts/prepublish_audit.py')
 m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def test_synthetic_allowlist_is_exact_path_and_bytes(tmp_path):
 m=scanner()
 for name in m.PUBLIC_SYNTHETIC_SHA256:
  p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);raw=(ROOT/name).read_bytes();p.write_bytes(raw)
  assert not any(x.severity=='blocker' for x in m.audit(tmp_path))
  p.write_bytes(raw+b'\n');assert any(x.code=='private_data_file' for x in m.audit(tmp_path));p.write_bytes(raw)
 (tmp_path/'customer.csv').write_bytes(raw)
 assert any(x.path=='customer.csv' and x.code=='private_data_file' for x in m.audit(tmp_path))

def test_secret_still_blocks_inside_allowlisted_location(tmp_path):
 m=scanner();p=tmp_path/next(iter(m.PUBLIC_SYNTHETIC_SHA256));p.parent.mkdir(parents=True)
 p.write_text('value\n'+'sk-'+('a'*32),encoding='utf8')
 codes={x.code for x in m.audit(tmp_path)}
 assert {'private_data_file','openai_like_key'}<=codes

def test_beta_metadata_consistent():
 import tomllib
 from causalops import __version__
 assert __version__==tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf8'))['project']['version']
 assert '0.17.0b1' in (ROOT/'README.md').read_text(encoding='utf8')
