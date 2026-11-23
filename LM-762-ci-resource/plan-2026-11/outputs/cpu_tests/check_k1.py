import re
import subprocess

with open("LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/report_model.py", encoding="utf-8") as f:
    text = f.read()

# find all tests in SPECS
all_tests = re.findall(r'tests=\[(.*?)\]', text, re.S)
test_list = []
for block in all_tests:
    for t in re.findall(r'"(tests/[^"]+)"', block):
        test_list.append(t)

unique_tests = sorted(set(test_list))
print(f"Total test paths referenced: {len(test_list)}, Unique: {len(unique_tests)}")

missing = []
for t in unique_tests:
    cmd = ["git", "-C", "third_party/LMCache", "cat-file", "-e", f"origin/dev:{t}"]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        missing.append(t)

print(f"Missing test paths in origin/dev ({len(missing)}):")
for m in missing:
    print(f"  - {m}")

