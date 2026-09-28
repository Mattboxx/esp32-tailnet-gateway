#!/usr/bin/env python3
"""Scan tracked content/artifacts and optionally reachable Git history.

Requires PyYAML. Reports rule/location only: never echo a matched secret.
History uses high-confidence credential rules, not topology/example heuristics.
This is pattern-based detection, not proof that a repository contains no secrets.
"""
from __future__ import annotations
import argparse
import base64
import fnmatch
import io
import pathlib
import re
import subprocess
import sys
import zipfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOKEN_RULES = {
    "Tailscale/Headscale auth key": rb"\b(?:tskey|hskey)-[A-Za-z0-9_-]{12,}",
    "GitHub token": rb"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,})\b",
    "Cloudflare token": rb"\bcfat_[A-Za-z0-9_-]{20,}\b",
    "AWS access key": rb"\bAKIA[0-9A-Z]{16}\b",
    "Google API key": rb"\bAIza[0-9A-Za-z_-]{30,}\b",
    "JWT": rb"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}",
}
ARTIFACT_RULES = {
    **TOKEN_RULES,
    "Credentials embedded in URL": rb"https?://[^\s/:@]+:[^\s/@]+@",
    "Developer home path": rb"(?i)(?:[A-Z]:\\Users\\|/Users/|/home/)[^\\/\x00\s]+",
}
PEM = re.compile(rb"-----BEGIN ((?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY)-----\s+"
                 rb"([A-Za-z0-9+/=\r\n]{40,})-----END \1-----")


def credential_findings(data: bytes, artifact: bool = False) -> set[str]:
    found = {name for name, pattern in (ARTIFACT_RULES if artifact else TOKEN_RULES).items()
             if re.search(pattern, data)}
    for match in PEM.finditer(data):
        try:
            decoded = base64.b64decode(re.sub(rb"\s+", b"", match[2]), validate=True)
        except ValueError:
            continue
        if len(decoded) > 16:
            found.add("Embedded private key")
    return found


def git(*args: str, repository: pathlib.Path = ROOT) -> bytes:
    return subprocess.check_output(["git", *args], cwd=repository)


def history_findings(repository: pathlib.Path = ROOT) -> tuple[list[tuple[str, str]], int]:
    objects = git("rev-list", "--objects", "--all", repository=repository).splitlines()
    findings = []
    count = 0
    # Stream objects: no temp dump of credentials and no unbounded history copy.
    with subprocess.Popen(["git", "cat-file", "--batch"], cwd=repository,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
        assert process.stdin is not None and process.stdout is not None
        for entry in objects:
            oid, _, path = entry.partition(b" ")
            process.stdin.write(oid + b"\n")
            process.stdin.flush()
            header = process.stdout.readline().split()
            if len(header) != 3:
                raise RuntimeError("Cannot read Git object")
            size = int(header[2])
            data = process.stdout.read(size)
            if len(data) != size or process.stdout.read(1) != b"\n":
                raise RuntimeError("Incomplete Git object")
            if header[1] != b"blob":
                continue
            count += 1
            location = f"{repository.name} history {oid.decode()[:12]} {path.decode(errors='replace')}"
            findings.extend((name, location) for name in credential_findings(data))
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Git history scan failed")
    return findings, count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--repository", type=pathlib.Path, default=ROOT,
                        help="Git worktree to scan (default: project root)")
    args = parser.parse_args()
    repository = args.repository.resolve()
    if not (repository / ".git").exists():
        parser.error(f"not a Git worktree: {repository}")
    config = yaml.safe_load((ROOT / ".github/sensitive-patterns.yml").read_text(encoding="utf-8"))
    files = [p.decode(errors="strict") for p in
             git("ls-files", "--cached", "--others", "--exclude-standard", "-z",
                 repository=repository).split(b"\0") if p]
    findings = []
    artifacts = 0
    for filename in files:
        for pattern in config.get("blocked_files", []):
            if fnmatch.fnmatchcase(filename, pattern):
                findings.append(("Blocked file", filename))
        path = repository / filename
        if not path.is_file():
            continue  # submodule or tracked deletion
        data = path.read_bytes()
        if path.suffix in (".bin", ".zip"):
            payloads = [(filename, data)]
            if path.suffix == ".zip":
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    payloads = [(filename + ":" + name, archive.read(name)) for name in archive.namelist()]
            for location, payload in payloads:
                artifacts += 1
                findings.extend((name, location) for name in credential_findings(payload, True))
        if b"\0" in data:
            continue
        lines = data.decode("utf-8", errors="replace").splitlines()
        for rule in config.get("blocked_content", []):
            if any(fnmatch.fnmatchcase(filename, p) for p in rule.get("exclude_files", [])):
                continue
            regex = re.compile(rule["pattern"])
            for line_no, line in enumerate(lines, 1):
                if any(m.group() not in rule.get("allow", []) for m in regex.finditer(line)):
                    findings.append((rule["name"], f"{filename}:{line_no}"))
    history_count = 0
    if args.history:
        older, history_count = history_findings(repository)
        findings.extend(older)
    for name, location in sorted(set(findings)):
        # Plain text avoids workflow-command injection through a filename.
        print(f"BLOCKED {name}: {location!r}")
    print(f"Scanned {len(files)} tracked paths, {artifacts} artifact payloads, "
          f"{history_count} historical blobs; {len(set(findings))} finding(s).")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
