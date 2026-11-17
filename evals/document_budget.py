"""설치 문서의 기존 크기 한도. 행동 평가 전 확인과 전체 자체 검사가 공유한다."""
import importlib.util
from pathlib import Path
import sys


def check(kit):
    kit = Path(kit)
    problems = []
    agents = (kit / 'AGENTS.md').read_text(encoding='utf-8')
    region = agents[agents.index('<!-- agent-workflow-kit:begin -->'):
                    agents.index('<!-- agent-workflow-kit:end -->')].encode()
    if len(region) > 6000:
        problems.append(f'AGENTS.md 키트 영역 {len(region)}B > 6000B')
    for file in sorted((kit / '.agents/skills').glob('*/SKILL.md')):
        size = len(file.read_bytes())
        if size > 4500:
            problems.append(f'{file.relative_to(kit)} {size}B > 4500B')
    documents = [file for file in (kit / '.agents/skills').rglob('*')
                 if file.is_file() and file.suffix in ('.md', '.txt')]
    spec = importlib.util.spec_from_file_location('awk_budget_verify', kit / '.agents/skills/wf-verify/verify.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    prompt_size = len(verifier.VERIFIER_PROMPT.encode())
    total = len(region) + sum(len(file.read_bytes()) for file in documents) + prompt_size
    if total > 32000:
        problems.append(f'설치 문서 전체 {total}B > 32000B')
    return problems, f'키트 영역 {len(region)}B, 검토자 지시문 {prompt_size}B, 설치 문서 전체 {total}B'


def main():
    try:
        problems, measured = check(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1])
    except (OSError, ValueError, AttributeError, ImportError) as error:
        print('문서 예산을 확인하지 못했다: ' + str(error))
        return 1
    print('\n'.join(problems) or measured)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
