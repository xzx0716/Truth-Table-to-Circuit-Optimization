#!/usr/bin/env python3
"""Publish a tagged GitHub release without printing or persisting credentials.

Authentication is obtained from the configured Git credential helper. Existing
release assets are reused only after verifying their exact SHA-256; this tool
never overwrites an existing asset or moves a tag.
"""
import argparse
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ReleaseError(Exception):
    pass


class SafeRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlparse(newurl)
        if target.scheme != "https":
            raise ReleaseError("Refused a non-HTTPS redirect")
        result = super().redirect_request(req, fp, code, msg, headers, newurl)
        if result is not None and target.netloc != urlparse(req.full_url).netloc:
            result.remove_header("Authorization")
        return result


def credential():
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        process = subprocess.run(["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n", text=True,
            capture_output=True, env=env, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        raise ReleaseError("Could not obtain GitHub credentials from the Git credential helper") from None
    if process.returncode:
        # Credential-helper stderr can contain sensitive context. Never echo it.
        raise ReleaseError("Git credential helper did not provide GitHub credentials")
    fields = dict(line.split("=", 1) for line in process.stdout.splitlines() if "=" in line)
    token = fields.get("password")
    if not token:
        raise ReleaseError("Git credential helper returned no GitHub token/password")
    return token


class GitHub:
    def __init__(self, token):
        self.token = token
        self.opener = build_opener(SafeRedirects())

    def request(self, url, method="GET", body=None, content_type="application/json",
                accept="application/vnd.github+json", allow_missing=False, binary=False):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc not in ("api.github.com", "uploads.github.com"):
            raise ReleaseError("Refused to send credentials outside GitHub API hosts")
        headers = {"Authorization": "Bearer " + self.token,
                   "Accept": accept, "User-Agent": "Truth-Table-to-Circuit-Release",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if body is not None:
            headers["Content-Type"] = content_type
        req = Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=180) as response:
                payload = response.read()
                return payload if binary else json.loads(payload) if payload else None
        except HTTPError as exc:
            if allow_missing and exc.code == 404:
                return None
            # Do not print headers, complete requests, auth values or response bodies.
            try:
                message = json.loads(exc.read()).get("message", "request failed")
            except (ValueError, OSError):
                message = "request failed"
            message = str(message).replace(self.token, "[redacted]")[:240]
            raise ReleaseError(f"GitHub HTTP {exc.code}: {message}") from None
        except (URLError, TimeoutError, OSError):
            raise ReleaseError("GitHub network request failed; credentials and request headers omitted") from None


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def publish(args):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        raise ReleaseError("Repository must be OWNER/NAME")
    if not args.tag.strip() or any(c in args.tag for c in "\r\n"):
        raise ReleaseError("Invalid tag")
    notes = args.notes_file.read_text(encoding="utf-8-sig")
    assets = []
    seen = set()
    for path in args.asset:
        if not path.is_file():
            raise ReleaseError(f"Asset is not a file: {path.name}")
        if path.name in seen:
            raise ReleaseError(f"Duplicate asset name: {path.name}")
        seen.add(path.name)
        payload = path.read_bytes()
        assets.append((path, payload, sha256(payload)))
    if args.dry_run:
        return {"dry_run": True, "repo": args.repo, "tag": args.tag, "name": args.name,
                "notes_sha256": sha256(notes.encode()),
                "assets": [{"name": p.name, "size": len(data), "sha256": digest}
                           for p, data, digest in assets],
                "authentication_used": False}
    api = GitHub(credential())
    base = "https://api.github.com/repos/" + args.repo
    # Creating a release must not silently invent a tag or choose its commit.
    tag = api.request(base + "/git/ref/tags/" + quote(args.tag, safe=""), allow_missing=True)
    if tag is None:
        raise ReleaseError("Release tag does not exist remotely; push the intended immutable tag first")
    release = api.request(base + "/releases/tags/" + quote(args.tag, safe=""), allow_missing=True)
    if release is None:
        body = json.dumps({"tag_name": args.tag, "name": args.name, "body": notes,
                           "draft": False, "prerelease": False}).encode()
        release = api.request(base + "/releases", method="POST", body=body)
    elif release.get("name") != args.name or (release.get("body") or "") != notes:
        raise ReleaseError("Existing release title/notes differ; refusing to overwrite release metadata")
    existing = {}
    page = 1
    while True:
        batch = api.request(base + f"/releases/{release['id']}/assets?per_page=100&page={page}")
        for asset in batch:
            existing[asset["name"]] = asset
        if len(batch) < 100:
            break
        page += 1
    links = []
    upload_base = release["upload_url"].split("{", 1)[0]
    # Verify all existing assets before uploading any missing assets.
    for path, payload, digest in assets:
        old = existing.get(path.name)
        if old is not None:
            if old["size"] != len(payload):
                raise ReleaseError(f"Existing asset differs in size: {path.name}; refusing overwrite")
            expected = "sha256:" + digest
            recorded = old.get("digest")
            if recorded:
                if recorded != expected:
                    raise ReleaseError(f"Existing asset checksum differs: {path.name}; refusing overwrite")
            else:
                remote = api.request(base + f"/releases/assets/{old['id']}",
                                     accept="application/octet-stream", binary=True)
                if sha256(remote) != digest:
                    raise ReleaseError(f"Existing asset bytes differ: {path.name}; refusing overwrite")
    for path, payload, digest in assets:
        asset = existing.get(path.name)
        if asset is None:
            asset = api.request(upload_base + "?" + urlencode({"name": path.name}), method="POST",
                body=payload, content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            if asset.get("size") != len(payload):
                raise ReleaseError(f"Uploaded asset size verification failed: {path.name}")
            recorded = asset.get("digest")
            if recorded and recorded != "sha256:" + digest:
                raise ReleaseError(f"Uploaded asset checksum verification failed: {path.name}")
            if not recorded:
                remote = api.request(base + f"/releases/assets/{asset['id']}",
                                     accept="application/octet-stream", binary=True)
                if sha256(remote) != digest:
                    raise ReleaseError(f"Uploaded asset byte verification failed: {path.name}")
        links.append({"name": path.name, "url": asset["browser_download_url"]})
    return {"html_url": release["html_url"], "assets": links}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="xzx0716/Truth-Table-to-Circuit-Optimization")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--notes-file", type=Path, required=True)
    parser.add_argument("--asset", type=Path, action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = publish(args)
    except (ReleaseError, OSError, UnicodeError, ValueError) as exc:
        print(f"Release publication failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
