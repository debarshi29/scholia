"""What each upstream project is about, so the corpus can be limited to chosen topics.

The owner wants problems from AI/ML and numerical code, not web frameworks or developer
tooling (14 Nov 2026). ``LIBRARY_TOPICS`` in config holds the topics to keep; it filters
both what the build publishes and what the Library shows. Published problems of other
topics stay on disk (problems are immutable) and are simply not listed.
"""

from enum import StrEnum


class Topic(StrEnum):
    ML = "ml"
    """Machine learning and NLP libraries."""
    SCIENTIFIC = "scientific"
    """Numerical and array code built on numpy."""
    MATH = "math"
    """Symbolic maths and algorithms."""
    WEB = "web"
    TOOLING = "tooling"
    OTHER = "other"


REPO_TOPICS: dict[str, Topic] = {
    # SWE-bench Lite
    "scikit-learn/scikit-learn": Topic.ML,
    "sympy/sympy": Topic.MATH,
    "astropy/astropy": Topic.SCIENTIFIC,
    "pydata/xarray": Topic.SCIENTIFIC,
    "matplotlib/matplotlib": Topic.SCIENTIFIC,
    "mwaskom/seaborn": Topic.SCIENTIFIC,
    "django/django": Topic.WEB,
    "pallets/flask": Topic.WEB,
    "psf/requests": Topic.WEB,
    "pytest-dev/pytest": Topic.TOOLING,
    "sphinx-doc/sphinx": Topic.TOOLING,
    "pylint-dev/pylint": Topic.TOOLING,
    # BugsInPy
    "keras-team/keras": Topic.ML,
    "explosion/spacy": Topic.ML,
    "pandas-dev/pandas": Topic.SCIENTIFIC,
    "tiangolo/fastapi": Topic.WEB,
    "jakubroztocil/httpie": Topic.WEB,
    "huge-success/sanic": Topic.WEB,
    "scrapy/scrapy": Topic.WEB,
    "tornadoweb/tornado": Topic.WEB,
    "ytdl-org/youtube-dl": Topic.WEB,
    "ansible/ansible": Topic.TOOLING,
    "psf/black": Topic.TOOLING,
    "cookiecutter/cookiecutter": Topic.TOOLING,
    "spotify/luigi": Topic.TOOLING,
    "nvbn/thefuck": Topic.TOOLING,
    "tqdm/tqdm": Topic.TOOLING,
    "cool-rr/pysnooper": Topic.TOOLING,
}


def topic_of(repo: str) -> Topic:
    """Topic of a GitHub ``owner/name``. Unknown projects are ``other``."""
    return REPO_TOPICS.get(repo.strip().strip("/").lower(), Topic.OTHER)


def parse_topics(raw: str) -> frozenset[Topic]:
    """Parse a comma-separated list such as ``ml,scientific,math``. Empty means every topic."""
    names = [part.strip().lower() for part in raw.split(",") if part.strip()]
    return frozenset(Topic(name) for name in names)


def allowed(repo: str, topics: frozenset[Topic]) -> bool:
    return not topics or topic_of(repo) in topics
