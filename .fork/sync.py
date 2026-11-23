import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def git(*args, data=None, env=None):
    return subprocess.run(
        ["git", *args], input=data, stdout=subprocess.PIPE, env=env, check=True
    ).stdout


def filtered_readme(source):
    lines = source.splitlines(keepends=True)
    headings = [line.strip() for line in lines]
    start = b"## Node Eligibility Requirements"
    toc = b"- [Node Eligibility Requirements](#node-eligibility-requirements)"
    if headings.count(start) != 1 or headings.count(toc) != 1:
        sys.exit("README eligibility heading or contents link changed; please review upstream.")
    first = headings.index(start)
    following = next((i for i in range(first + 1, len(lines)) if headings[i].startswith(b"## ")), None)
    if following is None or headings[following] not in (b"## How you are paid", b"## Capacity Testing"):
        sys.exit("Unexpected end of the README eligibility section; please review upstream.")
    result = b"".join(line for line in lines[:first] + lines[following:] if line.strip() != toc)
    if re.search(rb"node-eligibility-requirements|^\s*\|\s*U\d+\s*\||^### (?:Universal|Archive node|Full node|Per-chain) requirements", result, re.I | re.M):
        sys.exit("Eligibility material found outside the expected section; please review upstream.")
    return result


def sync():
    git("fetch", "--no-tags", "origin", "refs/heads/main")
    current = git("rev-parse", "FETCH_HEAD").decode().strip()
    git("fetch", "--no-tags", "https://github.com/taostat/blockmachine-miner.git", "refs/heads/main")
    source = git("rev-parse", "FETCH_HEAD").decode().strip()
    managed = (".fork",)
    if git("ls-tree", source, "--", *managed):
        sys.exit("Upstream uses a fork-owned path; please review before syncing.")
    if git("ls-tree", source, "--", "README.md").split()[:2] != [b"100644", b"blob"]:
        sys.exit("Upstream README.md must be a regular file.")
    readme = filtered_readme(git("show", source + ":README.md"))
    with tempfile.TemporaryDirectory() as tmp:
        index = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
        git("read-tree", source, env=index)
        git("restore", "--staged", "--source=" + current, "--", *managed, env=index)
        blob = git("hash-object", "-w", "--stdin", data=readme).decode().strip()
        git("update-index", "--add", "--cacheinfo", "100644", blob, "README.md", env=index)
        tree = git("write-tree", env=index).decode().strip()
    if tree == git("rev-parse", current + "^{tree}").decode().strip():
        print("Fork contents are current at upstream " + source)
        return
    parents = ["-p", current]
    if source != current and subprocess.run(["git", "merge-base", "--is-ancestor", source, current]).returncode == 1:
        parents += ["-p", source]
    commit = git("commit-tree", tree, *parents, "-m", "Sync miner from upstream " + source).decode().strip()
    git("push", "origin", commit + ":refs/heads/main")
    print("Published " + commit + " from upstream " + source)


if __name__ == "__main__":
    sync()
