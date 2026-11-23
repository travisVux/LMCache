@echo off
rem Daily Trace Agent run (registered in Windows Task Scheduler as "CacheAgent\TraceAgentDaily").
rem Proposes fixes for failed release gates >= v0.5.7 via knowledge\prompts\PR_FAILURE_TRACE_AGENT_PROMPT.md,
rem then rebuilds + verifies 06_PR_TO_CI_VISUAL.html locally. It never pushes to gh-pages.
cd /d "%~dp0..\..\..\.."
if not exist "LM-762-ci-resource\plan-2026-11\outputs\trace_agent" mkdir "LM-762-ci-resource\plan-2026-11\outputs\trace_agent"
python -I -X utf8 LM-762-ci-resource\plan-2026-11\outputs\cpu_tests\trace_agent_daily.py %* >> "LM-762-ci-resource\plan-2026-11\outputs\trace_agent\scheduler.log" 2>&1
rem 3 extra trace directions (#obs/flaky, #obs/gpuload, #obs/bug): agent runs only when due (weekly / data changed); bug is skipped while the number does not exist
python -I -X utf8 LM-762-ci-resource\plan-2026-11\outputs\cpu_tests\trace_agent_dirs.py >> "LM-762-ci-resource\plan-2026-11\outputs\trace_agent\scheduler.log" 2>&1
