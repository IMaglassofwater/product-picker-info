"""Scan project source files for likely committed secrets without printing values."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCAN_SUFFIXES = {".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".example"}
SKIP_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "data", "reports"}


@dataclass(frozen=True)
class SecretFinding:
    path: Path
    line: int
    kind: str


PATTERNS = {
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "database_password": re.compile(r"postgres(?:ql)?://[^\s:/]+:[^\s@]+@", re.I),
    "authorization_value": re.compile(r"Authorization\s*[:=]\s*['\"]?(?:Bearer\s+)?[A-Za-z0-9._-]{24,}", re.I),
}


def scan_project(root: Path = PROJECT_ROOT) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.name == ".env" or path.name == "check_secrets.py":
            continue
        if path.suffix.casefold() not in SCAN_SUFFIXES and path.name not in {".gitignore"}:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        for number, line in enumerate(lines, 1):
            for kind, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(SecretFinding(path.relative_to(root), number, kind))
    return findings


def main() -> int:
    findings = scan_project()
    print(f"Potential Secrets Found: {len(findings)}")
    for finding in findings:
        print(f"{finding.path}:{finding.line} [{finding.kind}]")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
