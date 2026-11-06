"""Create a fresh, isolated project using an explicit committed kit snapshot."""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[1]


def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def commit(project, message):
    run("git", "add", "-A", cwd=project)
    run("git", "-c", "user.name=goalflow", "-c", "user.email=goalflow@invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", message, cwd=project)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--kit-ref", required=True)
    parser.add_argument("--settings", type=Path)
    args = parser.parse_args()
    if args.target.exists() or args.target.is_symlink():
        parser.error("기존 경로는 사용하지 않는다. 새 시험 프로젝트 경로를 지정한다")
    selected = run("git", "rev-parse", "--verify", args.kit_ref + "^{commit}", cwd=KIT)
    settings = json.loads(args.settings.read_text()) if args.settings else None
    target = args.target.resolve()
    shutil.copytree(HERE / "fixture", target, ignore=shutil.ignore_patterns("__pycache__"))
    run("git", "init", "-q", cwd=target)
    commit(target, "goalflow fixture")
    with tempfile.TemporaryDirectory(prefix="goalflow-kit-") as directory:
        kit = Path(directory) / "kit"
        run("git", "clone", "-q", "--no-hardlinks", str(KIT), str(kit))
        run("git", "checkout", "-q", "--detach", selected, cwd=kit)
        run("bash", str(kit / "install.sh"), str(target))
    if settings is not None:
        path = target / ".claude/settings.json"
        current = json.loads(path.read_text())
        plugins = {**current.get("enabledPlugins", {}), **settings.get("enabledPlugins", {})}
        current.update(settings)
        current["enabledPlugins"] = plugins
        path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n")
    commit(target, "pinned kit for goalflow")
    print(json.dumps({"project": str(target), "kit": selected,
                      "base": run("git", "rev-parse", "HEAD", cwd=target),
                      "map": "work/enrollment/work.md"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
