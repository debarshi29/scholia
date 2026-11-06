import pytest

from corpus.patch import PatchError, cluster, parse_patch

SOURCE = "".join(f"line{i}\n" for i in range(1, 41))

REPLACE = """\
diff --git a/pkg/mod.py b/pkg/mod.py
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -9,5 +9,5 @@ def f():
 line9
 line10
-line11
+LINE11
 line12
 line13
"""


def test_replacement_maps_to_removed_line() -> None:
    [fp] = parse_patch(REPLACE)
    assert fp.path == "pkg/mod.py"
    assert not fp.is_new
    assert fp.locate(SOURCE) == [11]
    assert fp.changed_regions(SOURCE) == [(11, 11)]
    assert fp.diff.startswith("diff --git a/pkg/mod.py")


def test_header_offset_is_corrected_by_content() -> None:
    """Real SWE-bench patches can state the wrong start line (seen in sympy-11870)."""
    shifted = REPLACE.replace("@@ -9,5 +9,5 @@", "@@ -4,5 +4,5 @@")
    [fp] = parse_patch(shifted)
    assert fp.locate(SOURCE) == [11]


def test_pure_insertion_anchors_to_previous_line() -> None:
    patch = """\
diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -20,2 +20,4 @@
 line20
+new_a
+new_b
 line21
"""
    [fp] = parse_patch(patch)
    assert fp.locate(SOURCE) == [20]


def test_insertion_at_top_of_file() -> None:
    patch = """\
diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -0,0 +1,1 @@
+import os
"""
    [fp] = parse_patch(patch)
    assert fp.locate(SOURCE) == [1]


def test_replacement_block_is_not_also_an_insertion() -> None:
    patch = """\
diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -30,3 +30,4 @@
 line30
-line31
+x
+y
 line32
"""
    [fp] = parse_patch(patch)
    assert fp.locate(SOURCE) == [31]


def test_multiple_files_and_hunks() -> None:
    patch = (
        REPLACE
        + """\
diff --git a/other.py b/other.py
--- a/other.py
+++ b/other.py
@@ -2,2 +2,2 @@
-line2
+LINE2
 line3
@@ -35,2 +35,2 @@
 line35
-line36
+LINE36
"""
    )
    a, b = parse_patch(patch)
    assert (a.path, b.path) == ("pkg/mod.py", "other.py")
    assert b.locate(SOURCE) == [2, 36]
    assert b.changed_regions(SOURCE) == [(2, 2), (36, 36)]


def test_new_file_is_flagged() -> None:
    patch = """\
diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,1 @@
+x = 1
"""
    [fp] = parse_patch(patch)
    assert fp.is_new


def test_rename_rejected() -> None:
    with pytest.raises(PatchError, match="rename"):
        parse_patch("diff --git a/a.py b/b.py\n--- a/a.py\n+++ b/b.py\n@@ -1 +1 @@\n-a\n+b\n")


def test_content_mismatch_raises() -> None:
    [fp] = parse_patch(REPLACE.replace("-line11", "-nothing_like_this"))
    with pytest.raises(PatchError, match="does not match"):
        fp.locate(SOURCE)


def test_truncated_hunk_raises() -> None:
    with pytest.raises(PatchError, match="truncated"):
        parse_patch(REPLACE.rsplit(" line13", 1)[0])


def test_garbage_raises() -> None:
    with pytest.raises(PatchError):
        parse_patch("not a patch")


@pytest.mark.parametrize(
    ("points", "regions"),
    [
        ([], []),
        ([5], [(5, 5)]),
        ([5, 6, 15], [(5, 15)]),
        ([5, 6, 17], [(5, 6), (17, 17)]),
    ],
)
def test_cluster(points: list[int], regions: list[tuple[int, int]]) -> None:
    assert cluster(points, gap=10) == regions
