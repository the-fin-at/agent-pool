#!/usr/bin/env python3
"""Audit every distributable path, text file and declared binary asset.

This checks the current source tree, not Git history or a user's installed pool.
Run from any directory: python3 scripts/check_portability.py --report test-results/portability.json
"""
import argparse
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
POLICY = Path(__file__).with_name("portability-policy.json")
ASSETS = Path(__file__).with_name("portability-assets.json")


def source_files(root):
    """Include tracked and new source files, including hidden configuration."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
        capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError("Run this check in a Git source checkout")
    return sorted({p for p in result.stdout.decode().split("\0")
                   if p and ((root / p).is_file() or (root / p).is_symlink())})


def text_findings(text, policy):
    blocked = set(policy["blocked_identifier_sha256"])
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        tokens = re.findall(r"[a-z0-9]+", line.lower())
        if any(hashlib.sha256(token.encode()).hexdigest() in blocked for token in tokens):
            found.append((number, "machine-or-owner-identifier"))
        users = re.findall(r"(?i)/(?:Users|home)/([^/\s'\"`<>\\]+)", line)
        users += re.findall(r"(?i)[A-Z]:\\+Users\\+([^\\\s'\"`<>]+)", line)
        if any(user.lower() not in policy["generic_usernames"] for user in users):
            found.append((number, "personal-absolute-path"))
        for match in re.finditer(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})", line):
            # Login URL security fixtures use generic userinfo on official domains.
            if line[max(0, match.start() - 3):match.start()] == "://" and match[1] in {"user", "attacker"}:
                continue
            domain = match[2].lower()
            if not (domain in {"example.com", "example.org", "example.net"}
                    or domain.endswith((".invalid", ".test", ".example"))):
                found.append((number, "non-example-email"))
        for value in re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", line):
            try:
                address = ipaddress.IPv4Address(value)
            except ipaddress.AddressValueError:
                continue
            documentation = any(address in ipaddress.ip_network(net) for net in (
                "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"))
            if not (address.is_loopback or address.is_unspecified or documentation):
                found.append((number, "non-example-ipv4"))
    return sorted(set(found))


class HtmlLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for name in ("href", "src"):
            if name in attrs:
                self.links.append(attrs[name])


def missing_links(root, path, text):
    if path.suffix == ".md":
        links = re.findall(r"!?\[[^\]\n]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", text)
    elif path.suffix == ".html":
        parser = HtmlLinks()
        parser.feed(text)
        links = parser.links
    else:
        return []
    failures = []
    for value in links:
        url = urlsplit(value.strip("<>"))
        if url.scheme or url.netloc or not url.path:
            continue
        relative = unquote(url.path)
        if relative.startswith("/agent-pool/"):
            target = root / "site" / relative[len("/agent-pool/"):]
        elif relative.startswith("/"):
            if path.parent == root / "desktop":
                target = root / "desktop" / relative.lstrip("/")
                if not target.exists():
                    target = root / "desktop/public" / relative.lstrip("/")
            else:
                target = root / relative.lstrip("/")
        else:
            target = path.parent / relative
        if not target.exists():
            failures.append(value)
    return failures


def audit(root, policy, assets, files=None):
    records = []
    findings = []
    directories = set()
    for name in source_files(root) if files is None else sorted(files):
        path = root / name
        for parent in Path(name).parents:
            if str(parent) != ".":
                directories.add(parent.as_posix())
        if path.is_symlink():
            target = os.readlink(path)
            data = target.encode()
            try:
                safe = not Path(target).is_absolute() and path.resolve().is_relative_to(root.resolve()) and path.exists()
            except (OSError, RuntimeError):
                safe = False
            if not safe:
                findings.append({"path": name, "line": 0, "rule": "external-or-dangling-symlink"})
        else:
            data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if (name.startswith("test-results/") or path.name in {".env", "auth.json", "credentials.json"}
                or path.suffix in {".log", ".sqlite", ".sqlite3", ".db"}):
            findings.append({"path": name, "line": 0, "rule": "runtime-state-in-source"})
        for line, rule in text_findings(name, policy):
            findings.append({"path": name, "line": 0, "rule": "path-" + rule})
        try:
            text = data.decode("utf-8")
            if "\0" in text:
                raise UnicodeDecodeError("utf-8", data, 0, 1, "binary NUL")
        except UnicodeDecodeError:
            asset = assets.get(name, {})
            if asset.get("sha256") != digest or not asset.get("purpose"):
                findings.append({"path": name, "line": 0, "rule": "unreviewed-binary"})
            kind = "binary"
        else:
            kind = "symlink" if path.is_symlink() else "text"
            # Upstream license notices must retain their original attribution.
            license_notice = bool(re.search(r"(?:^|/)(?:OFL|LICENSE|NOTICE|COPYING)[^/]*$", name, re.I))
            for line, rule in text_findings(text, policy):
                if rule == "non-example-email" and license_notice:
                    continue
                findings.append({"path": name, "line": line, "rule": rule})
            for target in missing_links(root, path, text):
                findings.append({"path": name, "line": 0, "rule": "missing-local-link", "target": target})
        records.append({"path": name, "kind": kind, "bytes": len(data), "sha256": digest})
    active = {record["path"] for record in records}
    for name in assets.keys() - active:
        findings.append({"path": name, "line": 0, "rule": "stale-binary-declaration"})
    return {"schema_version": 1, "scope": "current distributable source tree",
            "passed": not findings, "file_count": len(records), "directory_count": len(directories),
            "directories": sorted(directories), "files": records, "findings": findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Write the complete per-file inventory as JSON")
    args = parser.parse_args()
    result = audit(ROOT, json.loads(POLICY.read_text()), json.loads(ASSETS.read_text()))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n")
    counts = {kind: sum(record["kind"] == kind for record in result["files"])
              for kind in ("text", "binary", "symlink")}
    print(f"Checked {result['file_count']} files ({counts['text']} text, {counts['binary']} binary) "
          f"and {result['directory_count']} folders: {len(result['findings'])} findings")
    for finding in result["findings"]:
        print(f"{finding['path']}:{finding['line']}: {finding['rule']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
