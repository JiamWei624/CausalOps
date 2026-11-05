from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", ".venv", "artifacts", "htmlcov"}
PUBLIC_SAMPLE_SHA256 = '4a402cf041b025d4566d954c3b9ba8635a3a8a01e039005d97d6a710278cf05e'

PUBLIC_SYNTHETIC_SHA256 = {'docs/evaluation/v23/data/donor.csv': 'eb78ce39706c7f561bf80755928d5b44c363661c6c97b5f37427a9b3a6a92bfd', 'docs/evaluation/v23/data/lab.csv': 'cf18c6ecdf1324603750aa26d051b38923ee066fa7bb6fb08cd5ad6cf0280e67', 'docs/evaluation/v23/data/line.csv': '9968701d94df042321ac703698a99a35f91cdeae1b381ff13f14de698d40a5fe', 'docs/evaluation/v23/data/port.csv': 'a1d89add002ab83172a4f988977ce535fbd81932aceadac171c952c8c5b4034e', 'docs/evaluation/v23/data/school.csv': '5bc7b37324ba8c831b3997115dd1c13f7220d3259dd7f86750bc3e1b06782060', 'docs/evaluation/v23/data/service.csv': '6fc6d28ab189ec60ebfc264feb69c9a081958b3da0e7f97c56d6821bc2c7e5d7'}

PRIVATE_SUFFIXES = {".csv", ".parquet", ".pq", ".duckdb", ".sqlite", ".db", ".pkl", ".pickle"}
TEXT_SUFFIXES = {".csv", ".py", ".toml", ".md", ".json", ".yaml", ".yml", ".txt", ".sql", ".ps1"}
MAX_PUBLIC_FILE_BYTES = 5 * 1024 * 1024

SECRET_PATTERNS = {
    "openai_like_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "assigned_secret": re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|password|secret)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]"
    ),
}
PERSONAL_PATTERNS = {
    "windows_user_path": re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.I),
    "email_address": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "cn_mobile": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
}


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    line: int | None
    message: str


def iter_candidates(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def audit(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_candidates(root):
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        if size > MAX_PUBLIC_FILE_BYTES:
            findings.append(Finding("blocker", "large_file", relative, None, f"File is {size} bytes (>5 MiB)."))
        if path.suffix.lower() in PRIVATE_SUFFIXES and not ((relative == 'src/causalops/sample_data/winequality-red.csv' and hashlib.sha256(path.read_bytes()).hexdigest() == PUBLIC_SAMPLE_SHA256) or PUBLIC_SYNTHETIC_SHA256.get(relative) == hashlib.sha256(path.read_bytes()).hexdigest()):
            findings.append(Finding("blocker", "private_data_file", relative, None, "Data/binary artifact must not enter the public repository."))
        if path.suffix.lower() not in TEXT_SUFFIXES or size > MAX_PUBLIC_FILE_BYTES:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            findings.append(Finding("review", "non_utf8_text", relative, None, "Text candidate is not valid UTF-8."))
            continue
        for number, line in enumerate(lines, start=1):
            for code, pattern in SECRET_PATTERNS.items():
                if pattern.search(line):
                    findings.append(Finding("blocker", code, relative, number, "Potential credential material detected."))
            # A generated manifest digest can contain a phone-shaped decimal substring.
            # Exempt only the complete, typed SHA-256 value, never filenames or free text.
            personal_line = line
            if path.name == "PACKAGE_MANIFEST.json" and re.fullmatch(r'\s*"sha256"\s*:\s*"[0-9a-f]{64}"\s*,?\s*', line):
                personal_line = ""
            for code, pattern in PERSONAL_PATTERNS.items():
                if pattern.search(personal_line):
                    findings.append(Finding("review", code, relative, number, "Potential personal identifier or machine-specific path requires review."))
    return findings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    findings = audit(root)
    payload = {
        "root": str(root),
        "status": "blocked" if any(item.severity == "blocker" for item in findings) else "review",
        "blockers": sum(item.severity == "blocker" for item in findings),
        "review_items": sum(item.severity == "review" for item in findings),
        "findings": [asdict(item) for item in findings],
        "limitations": [
            "Pattern scanning cannot prove that a repository contains no secrets.",
            "A human must inspect git diff and the final staged file list before publishing.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(1 if payload["blockers"] else 0)


if __name__ == "__main__":
    main()
