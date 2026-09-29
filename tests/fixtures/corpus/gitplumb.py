"""Bare-repository writes through git plumbing, so the corpus depends on no library under test.

Every commit is deterministic: author, committer and dates come from the caller, never the clock.
"""

import os
import subprocess

DOMAIN = "users.noreply.syngraphe.local"
EPOCH = 1_800_000_000  # a fixed starting date, so the corpus is reproducible byte for byte


def author_env(user_id, seq):
    ident_name = str(user_id)
    ident_mail = f"{user_id}@{DOMAIN}"
    date = f"{EPOCH + seq * 3600} +0000"
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": ident_name,
            "GIT_AUTHOR_EMAIL": ident_mail,
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": ident_name,
            "GIT_COMMITTER_EMAIL": ident_mail,
            "GIT_COMMITTER_DATE": date,
        }
    )
    return env


def isolated_env():
    """The process environment without the developer's git configuration: no signing, no hooks."""
    env = dict(os.environ)
    env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
    return env


def git(repo, *args, inp=None, env=None):
    r = subprocess.run(
        ["git", "-C", repo, *args], input=inp, env=env or isolated_env(), capture_output=True
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.decode(errors='replace')}")
    return r.stdout


def init_bare(repo):
    if os.path.exists(repo):
        raise FileExistsError(f"{repo} exists; the corpus is generated into a new directory")
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", repo], check=True, env=isolated_env()
    )


def head(repo):
    try:
        return git(repo, "rev-parse", "--verify", "-q", "refs/heads/main").decode().strip() or None
    except RuntimeError:
        return None


def commit_document(repo, content, user_id, message, seq, path="document.md"):
    """Write one file as the whole tree and commit it on main. Returns the commit sha."""
    env = author_env(user_id, seq)
    blob = git(repo, "hash-object", "-w", "--stdin", inp=content.encode("utf-8")).decode().strip()
    tree = git(repo, "mktree", inp=f"100644 blob {blob}\t{path}\n".encode()).decode().strip()
    parent = head(repo)
    args = ["commit-tree", tree, "-m", message]
    if parent:
        args += ["-p", parent]
    sha = git(repo, *args, env=env).decode().strip()
    git(repo, "update-ref", "refs/heads/main", sha)
    return sha


def tag(repo, name, sha, user_id, seq, message):
    git(repo, "tag", "-a", name, sha, "-m", message, env=author_env(user_id, seq))


def read_at(repo, sha, path="document.md"):
    return git(repo, "show", f"{sha}:{path}").decode("utf-8")
