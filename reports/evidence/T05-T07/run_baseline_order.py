import pathlib,json,subprocess,os,time,sys
root=pathlib.Path.cwd();out=root/'reports/evidence/T05-T07';base=root/'.task-tools/base'
nodes=['tests/unit/test_runaway_hardening.py::TestGesturePassiveTriggerGuardWiring::test_repeated_triple_clap_triggers_are_bounded']
env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',JARVIS_HEADLESS='1',JARVIS_MOCK_AUDIO='1',JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK='1',GOOGLE_API_KEY='test_dummy_ci_key',JARVIS_RUN_LIVE_NETWORK_TESTS='0',JARVIS_RUN_LIVE_INFRA_TESTS='0',JARVIS_RUN_LIVE_IMAP_TESTS='0',JARVIS_RUN_BROWSER_E2E='1',PLAYWRIGHT_BROWSERS_PATH=r'C:/Users/MSI/.codex/worktrees/ci-baseline-9d3c591/JARVIS/.baseline-tools/browsers',PYTEST_DEBUG_TEMPROOT=str(root/'.task-tools/basetemp'))
pathlib.Path(env['PYTEST_DEBUG_TEMPROOT']).mkdir(exist_ok=True)
cmd=[r'C:/Users/MSI/.codex/worktrees/ci-baseline-9d3c591/runtime/venv/Scripts/python.exe','-m','pytest',*nodes,'-o','addopts=','-q','--tb=short','--timeout=120','--junit-xml='+str(out/'baseline-order-rerun.xml')]
t=time.time()
with (out/'baseline-order-rerun.txt').open('w',encoding='utf-8') as f:r=subprocess.run(cmd,cwd=base,env=env,stdout=f,stderr=subprocess.STDOUT)
record={'command':cmd,'cwd':str(base),'revision':'9d3c5916ee715eff291ed2364beab9b1e9a815b6','started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(t)),'wall_seconds':time.time()-t,'exit_code':r.returncode}
(out/'baseline-order-rerun.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record));print((out/'baseline-order-rerun.txt').read_text(encoding='utf-8')[-1500:]);sys.exit(r.returncode)
