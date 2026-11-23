import json

with open("LM-762-ci-resource/plan-2026-11/outputs/trace_agent/proposals.json", encoding="utf-8") as f:
    props = json.load(f)

print(f"proposals.json keys: {list(props.keys())}")
for tag, data in props.items():
    print(f"\n=== Tag: {tag} ===")
    if isinstance(data, dict):
        print(f"  suspect_pr: {data.get('suspect_pr')}")
        print(f"  root_cause: {str(data.get('root_cause'))[:200]}")
        print(f"  failing_tests: {data.get('failing_tests')}")
        print(f"  fix_proposal: {str(data.get('fix_proposal'))[:200]}")
    else:
        print(f"  type: {type(data)}")

