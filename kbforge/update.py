"""Fast-forward the source checkout on explicit request."""

import os
from pathlib import Path
import subprocess

SOURCE_ROOT = Path(__file__).resolve().parent.parent


def git(root, *args):
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            env={
                **os.environ,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_SSH_COMMAND": "ssh -o BatchMode=yes",
            },
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=45,
        )
    except FileNotFoundError as error:
        raise ValueError("Install Git to update from the app.") from error
    except subprocess.TimeoutExpired as error:
        raise ValueError(
            "Git did not finish in time. Check the checkout before retrying."
        ) from error
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(
            f"Git could not {args[0]}: {detail}"
            if detail
            else f"Git could not {args[0]}."
        )
    return result.stdout.strip()


def update_checkout(root=SOURCE_ROOT):
    """Fetch the configured upstream and apply it only as a fast-forward."""
    if not (root / ".git").exists():
        raise ValueError(
            "This installation is not a Git checkout. Download a new copy to update."
        )
    if Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root.resolve():
        raise ValueError("Open KB Forge from the root of its own Git checkout.")
    branch = git(root, "branch", "--show-current")
    if not branch:
        raise ValueError("Switch to a local branch before updating.")
    try:
        upstream = git(root, "rev-parse", "--symbolic-full-name", "@{upstream}")
        remote = git(root, "config", "--get", f"branch.{branch}.remote")
    except ValueError as error:
        raise ValueError(
            "Configure an upstream remote branch before updating."
        ) from error
    if not upstream.startswith("refs/remotes/") or remote == ".":
        raise ValueError("Configure an upstream remote branch before updating.")
    if git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Save or commit checkout changes before updating.")
    before = git(root, "rev-parse", "HEAD")
    git(root, "fetch", "--", remote)
    target = git(root, "rev-parse", "--verify", upstream)
    if before == target:
        return None
    # Recheck after fetching in case an editor or another Git client changed the checkout.
    if (
        git(root, "rev-parse", "HEAD") != before
        or git(root, "branch", "--show-current") != branch
        or git(root, "status", "--porcelain", "--untracked-files=normal")
    ):
        raise ValueError(
            "The checkout changed while fetching. Review the changes and retry."
        )
    if git(root, "merge-base", before, target) != before:
        raise ValueError(
            "The local branch has commits outside its upstream. Reconcile them in Git before updating."
        )
    git(root, "merge", "--ff-only", "--no-overwrite-ignore", target)
    return before[:12], target[:12]
