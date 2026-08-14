from pathlib import Path

from lib.memory.volatile import find_markers, check_marker, CHECKERS


def test_find_markers_extracts_kind_and_line():
    text = (
        "# Page\n\n"
        "RenOS is currently at 0.7.2. <!-- ren-volatile: framework-version -->\n"
        "27 tagged releases so far. <!-- ren-volatile: release-count -->\n"
        "No marker here.\n"
    )
    markers = find_markers(text)
    assert [m.kind for m in markers] == ["framework-version", "release-count"]
    assert markers[0].line_no == 3
    assert "0.7.2" in markers[0].line_text


def test_unknown_kind_is_inventoried_not_checked():
    text = "The frontier model is X. <!-- ren-volatile: current-frontier -->\n"
    (marker,) = find_markers(text)
    status, truth = check_marker(marker)
    assert status == "unverifiable" and truth is None


def test_release_count_checker_against_fixture_repo(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for cmd in (["git", "-C", str(tmp_path), "commit", "--allow-empty", "-q",
                 "-m", "x"],
                ["git", "-C", str(tmp_path), "tag", "v0.1.0"],
                ["git", "-C", str(tmp_path), "tag", "v0.2.0"]):
        subprocess.run(cmd, check=True,
                       env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                            "PATH": __import__("os").environ["PATH"]})
    (marker,) = find_markers("2 releases <!-- ren-volatile: release-count -->\n")
    status, truth = check_marker(marker, repo_root=tmp_path)
    assert status == "ok" and truth == "2"

    (stale,) = find_markers("99 releases <!-- ren-volatile: release-count -->\n")
    status, truth = check_marker(stale, repo_root=tmp_path)
    assert status == "stale" and truth == "2"


def test_missing_ground_truth_is_unverifiable(tmp_path):
    # tmp_path is not a git repo → release-count checker can't run
    (marker,) = find_markers("2 releases <!-- ren-volatile: release-count -->\n")
    status, truth = check_marker(marker, repo_root=tmp_path)
    assert status == "unverifiable"
