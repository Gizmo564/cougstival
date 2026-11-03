"""publish() against a throwaway local repo: author, message, no trailers, and recovery when the remote moved on."""
import os, subprocess, tempfile
from datetime import datetime
import run

def sh(*a, cwd=None):
    return subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

with tempfile.TemporaryDirectory() as tmp:
    remote, a, b = (os.path.join(tmp, n) for n in ("remote.git", "a", "b"))
    sh("git", "init", "--bare", "-b", "main", remote)
    sh("git", "clone", remote, a); sh("git", "clone", remote, b)
    for repo in (a, b):  # identity for the test's own setup commits only
        sh("git", "config", "user.name", "Someone Else", cwd=repo); sh("git", "config", "user.email", "x@example.com", cwd=repo)
    os.makedirs(os.path.join(a, "docs")); open(os.path.join(a, "docs", "data.json"), "w").write("1")
    open(os.path.join(a, "README"), "w").write("hi")
    sh("git", "add", ".", cwd=a); sh("git", "commit", "-m", "init", cwd=a); sh("git", "push", "-u", "origin", "main", cwd=a)
    run.HERE = a
    os.environ["GIT_EMAIL"] = "me@example.com"
    now = datetime(2026, 11, 9, 17, 0)

    open(os.path.join(a, "docs", "data.json"), "w").write("2")
    run.publish(now)
    log = sh("git", "log", "-1", "--format=%an|%ae|%cn|%ce|%B", cwd=remote)
    assert log.startswith("Team Rocket|me@example.com|Team Rocket|me@example.com|Update leaderboard Mon 17:00"), log
    assert "Co-Authored-By" not in log and "Claude" not in log

    run.publish(now)  # nothing changed: no new commit, no error
    assert sh("git", "rev-list", "--count", "main", cwd=remote) == "2"

    # Someone pushes other work to the repo; the next publish still goes through.
    sh("git", "pull", "origin", "main", cwd=b)  # b was cloned while the remote was empty
    open(os.path.join(b, "README"), "w").write("new"); sh("git", "commit", "-am", "code change", cwd=b); sh("git", "push", cwd=b)
    open(os.path.join(a, "docs", "data.json"), "w").write("3")
    run.publish(now)
    assert sh("git", "rev-list", "--count", "main", cwd=remote) == "4"
    assert sh("git", "show", "main:docs/data.json", cwd=remote) == "3"
print("publish test passed")
