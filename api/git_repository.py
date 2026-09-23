import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "sample_repository"
PRS = Path(__file__).resolve().parents[1] / ".runtime_prs.json"


def _git_executable():

    executable = shutil.which("git")
    if executable:
        return executable

    if Path.home().drive:
        candidates = (
            Path("C:/Program Files/Git/cmd/git.exe"),
            Path("C:/Program Files (x86)/Git/cmd/git.exe"),
            Path.home() / "AppData/Local/Programs/Git/cmd/git.exe",
        )
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

    raise RuntimeError(
        "Git is required for the local repository integration. "
        "Install Git and ensure it is available on PATH."
    )


def git(*args, check=True):

    process = subprocess.run(
        [_git_executable(), "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore"
    )

    if check and process.returncode != 0:
        raise RuntimeError(
            f"""
Git command failed

Command:
git {' '.join(args)}

STDOUT:
{process.stdout}

STDERR:
{process.stderr}
"""
        )

    return process.stdout.strip()


def configure_git_user():

    user_name = git("config", "user.name", check=False)
    user_email = git("config", "user.email", check=False)

    if not user_name:
        git("config", "user.name", "Use Case 5 Demo")

    if not user_email:
        git(
            "config",
            "user.email",
            "usecase5-demo@example.com"
        )


def ensure_repo():

    if not (ROOT / ".git").exists():
        git("init", "-b", "main")

    configure_git_user()


def safe(path):

    p = (ROOT / path).resolve()

    if ROOT.resolve() not in p.parents and p != ROOT.resolve():
        raise ValueError("Invalid path")

    return p


def files():

    return [
        str(f.relative_to(ROOT)).replace("\\", "/")
        for f in ROOT.rglob("*")
        if f.is_file() and ".git" not in f.parts
    ]


def read(path):
    return safe(path).read_text(encoding="utf-8")


def branches():

    output = git(
        "branch",
        "--format=%(refname:short)",
        check=False
    )

    if not output:
        return []

    return output.splitlines()


def create_branch(name):

    configure_git_user()

    git("switch", "-C", name)

    return name


def write(path, content):

    p = safe(path)

    p.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    p.write_text(content, encoding="utf-8")

    return path


def commit(message):

    configure_git_user()

    git("add", ".")

    status = git(
        "status",
        "--porcelain",
        check=False
    )

    if not status:
        raise RuntimeError(
            "No file changes detected. Modify a file before creating a PR."
        )

    git("commit", "-m", message)

    return git("rev-parse", "HEAD")


def load_prs():

    if not PRS.exists():
        return []

    return json.loads(
        PRS.read_text(encoding="utf-8")
    )


def save_prs(data):

    PRS.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )


def create_pr(
    title,
    description,
    source_branch,
    target_branch="main"
):

    prs = load_prs()

    pr_number = (
        max(
            [p["number"] for p in prs],
            default=400
        ) + 1
    )

    merge_base = git(
        "merge-base",
        target_branch,
        source_branch
    )

    files_changed = git(
        "diff",
        "--name-only",
        merge_base,
        source_branch
    ).splitlines()

    changes = []

    for path in files_changed:

        patch = git(
            "diff",
            merge_base,
            source_branch,
            "--",
            path
        )

        change = {
            "path": path,
            "patch": patch,
            "breaking": False
        }

        if path.startswith("order-api"):
            change["service"] = "order-api"
            change["symbol"] = "GET /api/orders"
            change["breaking"] = True

        elif path.startswith("customer-api"):
            change["service"] = "customer-api"

        if path.endswith("customer_contract.sql"):
            change["schema"] = "customer_contract"
            change["breaking"] = True

        changes.append(change)

    pr = {
        "number": pr_number,
        "title": title,
        "description": description,
        "source_branch": source_branch,
        "target_branch": target_branch,
        "commit_sha": git(
            "rev-parse",
            source_branch
        ),
        "status": "open",
        "changed_files": changes
    }

    prs.append(pr)

    save_prs(prs)

    return pr


def get_pr(number):

    prs = load_prs()

    for pr in prs:
        if pr["number"] == number:
            return pr

    raise RuntimeError(
        f"PR {number} not found"
    )


def merge_pr(number):

    prs = load_prs()

    selected = None

    for pr in prs:
        if pr["number"] == number:
            selected = pr
            break

    if selected is None:
        raise RuntimeError(
            f"PR {number} not found"
        )

    git("switch", selected["target_branch"])

    git(
        "merge",
        "--no-ff",
        selected["source_branch"],
        "-m",
        f"Merge PR #{number}: {selected['title']}"
    )

    selected["status"] = "merged"

    save_prs(prs)

    return {
        "merged": True,
        "commit_sha": git(
            "rev-parse",
            "HEAD"
        )
    }
