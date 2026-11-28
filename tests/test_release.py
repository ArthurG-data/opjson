import re
import subprocess
from pathlib import Path

from test_build import outputs, stamped

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def repo_with_tags(tmp_path, *tags):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                    "--allow-empty", "-m", "x"], check=True)
    for t in tags:
        subprocess.run(["git", "-C", str(tmp_path), "tag", t], check=True)
    return tmp_path


def test_next_version_sorts_by_version(tmp_path):
    repo = repo_with_tags(tmp_path, "v0.9.3", "v0.10.1", "v0.4.0")
    out = subprocess.run([TOOLS / "next_version.sh"], cwd=repo, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "v0.10.2"


def test_next_version_without_a_tag_fails(tmp_path):
    repo = repo_with_tags(tmp_path)
    out = subprocess.run([TOOLS / "next_version.sh"], cwd=repo, capture_output=True, text=True)
    assert out.returncode == 1 and "no release tag to follow" in out.stderr


def test_release_attaches_every_file_build_writes():
    names = re.search(r"for name in ([^;]+);", (TOOLS / "release.sh").read_text()).group(1).split()
    assert sorted(f"{n}.json" for n in names) == sorted(outputs(*stamped()))
