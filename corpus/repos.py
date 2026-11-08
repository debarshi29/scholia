"""Git checkouts of upstream repos (cached under ``data/repos/``) and licence lookup.

Repos are fetched shallowly and blob-less (``--depth 1 --filter=blob:none``), so only
the files actually read are downloaded. Nothing is checked out into a working tree.
"""

import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path

from git import GitCommandError, Repo

from corpus.filters import detect_licence_from_text

log = logging.getLogger(__name__)

_FULL_SHA = re.compile(r"[0-9a-f]{40}")

_LICENCE_FILES = ("LICENSE", "LICENSE.txt", "LICENSE.rst", "LICENSE.md", "COPYING", "LICENCE")


class CheckoutError(RuntimeError):
    pass


class RepoCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._fetched: set[tuple[str, str]] = set()

    def _repo(self, slug: str) -> Repo:
        path = self.root / slug.replace("/", "__")
        if (path / "HEAD").exists():
            return Repo(path)
        repo = Repo.init(path, bare=True)
        repo.create_remote("origin", f"https://github.com/{slug}.git")
        # Blob-less partial clone: lazily fetch only the blobs we `git show`.
        with repo.config_writer() as cfg:
            cfg.set_value('remote "origin"', "promisor", "true")
            cfg.set_value('remote "origin"', "partialclonefilter", "blob:none")
        return repo

    def resolve(self, slug: str, ref: str) -> str:
        """Full 40-char sha for ``ref``. Abbreviated shas (common in BugsInPy) cannot be
        fetched directly, so they are resolved in a separate treeless clone of the history
        (``--filter=tree:0``: commits only, no trees or blobs), kept apart from the shallow
        object store used for reading files.
        """
        if _FULL_SHA.fullmatch(ref):
            return ref
        path = self.root / (slug.replace("/", "__") + "__history")
        if (path / "HEAD").exists():
            repo = Repo(path)
        else:
            repo = Repo.init(path, bare=True)
            repo.create_remote("origin", f"https://github.com/{slug}.git")
        try:
            return str(repo.git.rev_parse("--verify", f"{ref}^{{commit}}"))
        except GitCommandError:
            pass
        log.info("fetching history to resolve short sha", extra={"repo": slug, "ref": ref})
        try:
            repo.git.fetch("--filter=tree:0", "origin", "+refs/heads/*:refs/heads/*")
            return str(repo.git.rev_parse("--verify", f"{ref}^{{commit}}"))
        except GitCommandError as exc:
            raise CheckoutError(f"cannot resolve {slug}@{ref}: {exc.stderr}") from exc

    def _ensure_commit(self, slug: str, commit: str) -> Repo:
        repo = self._repo(slug)
        if (slug, commit) in self._fetched:
            return repo
        try:
            repo.git.cat_file("-e", f"{commit}^{{commit}}")
        except GitCommandError:
            log.info("fetching commit", extra={"repo": slug, "commit": commit})
            try:
                repo.git.fetch("--depth", "1", "--filter=blob:none", "origin", commit)
            except GitCommandError as exc:
                raise CheckoutError(f"cannot fetch {slug}@{commit}: {exc.stderr}") from exc
        self._fetched.add((slug, commit))
        return repo

    def read(self, slug: str, commit: str, path: str) -> bytes:
        repo = self._ensure_commit(slug, commit)
        try:
            out = repo.git.execute(
                ["git", "show", f"{commit}:{path}"],
                stdout_as_string=False,
                strip_newline_in_stdout=False,
            )
        except GitCommandError as exc:
            raise CheckoutError(f"{slug}@{commit}:{path} not readable: {exc.stderr}") from exc
        assert isinstance(out, bytes)
        return out

    def read_text(self, slug: str, commit: str, path: str) -> str:
        try:
            return self.read(slug, commit, path).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CheckoutError(f"{path} is not UTF-8") from exc

    def licence_text(self, slug: str, commit: str) -> str | None:
        for name in _LICENCE_FILES:
            try:
                return self.read_text(slug, commit, name)
            except CheckoutError:
                continue
        return None


class LicenceResolver:
    """SPDX id for a repo: GitHub's detection first, then the LICENSE text at the commit.

    GitHub answers are cached in ``<cache_dir>/licences.json``.
    """

    def __init__(self, cache_dir: Path, repos: RepoCache) -> None:
        self.path = cache_dir / "licences.json"
        self.repos = repos
        self._cache: dict[str, str | None] = (
            json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        )

    def _github(self, slug: str) -> str | None:
        if slug not in self._cache:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{slug}/license",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "scholia-corpus"},
            )
            spdx: str | None
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    spdx = json.load(resp).get("license", {}).get("spdx_id")
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                spdx = None
            self._cache[slug] = spdx
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._cache, indent=2, sort_keys=True), "utf-8")
        return self._cache[slug]

    def resolve(self, slug: str, commit: str) -> str | None:
        spdx = self._github(slug)
        if spdx and spdx != "NOASSERTION":
            return spdx
        text = self.repos.licence_text(slug, commit)
        return detect_licence_from_text(text) if text else None
