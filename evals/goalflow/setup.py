"""Create a fresh, isolated project using an explicit committed kit snapshot."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
from session import build_project, kit_checkout  # 키트 커밋 설치는 평가 실행기와 같은 절차를 쓴다


def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


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
    fixture = lambda project: shutil.copytree(HERE / "fixture", project, ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="goalflow-kit-") as directory:
        kit = Path(directory) / "kit"
        kit_checkout(selected, kit)
        build_project(target, kit, prepare=fixture, settings=settings,
                      author=("goalflow", "goalflow@invalid"), messages=("goalflow fixture", "pinned kit for goalflow"))
    print(json.dumps({"project": str(target), "kit": selected,
                      "base": run("git", "rev-parse", "HEAD", cwd=target),
                      "map": "work/enrollment/work.md"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
