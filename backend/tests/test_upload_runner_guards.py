"""Acceptance runner guards: inherited configuration and actual Windows process-tree timeout."""
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import pytest


def runner_module():
    path = Path(__file__).resolve().parents[2] / 'tools/audit/run-upload-integration.py'
    spec = importlib.util.spec_from_file_location('upload_acceptance_runner', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inherited_service_settings_do_not_reach_isolated_run(monkeypatch, tmp_path):
    runner = runner_module()
    home = tmp_path / 'native tool with spaces'
    java = home / ('jdk/bin/java.exe' if os.name == 'nt' else
                   'jdk.app/Contents/Home/bin/java' if platform.system() == 'Darwin' else 'jdk/bin/java')
    java.parent.mkdir(parents=True)
    java.write_text('Discovery fixture only; never executed.', encoding='utf-8')
    for key in ('AI_API_KEY', 'SMTP_HOST', 'ELASTICSEARCH_API_KEY', 'ELASTICSEARCH_CA_CERTS',
                'GROBID_URL', 'FRONTEND_DIST', 'KEYSTORE_PASSWORD', 'JAVA_TOOL_OPTIONS'):
        monkeypatch.setenv(key, 'isolated-guard-placeholder')
    monkeypatch.setenv('ELASTICSEARCH_URL', 'https://unrelated.invalid')
    env = runner.isolated_environment(tmp_path, tmp_path / 'config', home, tmp_path / 'model', 19243, 19343, 'fixture')
    assert env['ELASTICSEARCH_URL'] == 'http://127.0.0.1:19243'
    assert env['SCHOLARLENS_RUNTIME_DIR'] == str(tmp_path / 'bootstrap-runtime')
    assert env['ES_JAVA_HOME'] == str(java.parent.parent)
    assert env['TMP'] == env['TEMP'] == str(tmp_path / 'tmp')
    for key in ('AI_API_KEY', 'SMTP_HOST', 'ELASTICSEARCH_API_KEY', 'ELASTICSEARCH_CA_CERTS',
                'GROBID_URL', 'FRONTEND_DIST', 'KEYSTORE_PASSWORD', 'JAVA_TOOL_OPTIONS'):
        assert key not in env


@pytest.mark.skipif(os.name != 'nt', reason='Windows native process lifetime acceptance; POSIX runtime remains unverified')
def test_timeout_stops_owned_child_and_grandchild_with_unicode_space_paths(tmp_path):
    import ctypes
    from ctypes import wintypes

    runner = runner_module()
    script = tmp_path / '隔离 runner 进程.py'
    identity = tmp_path / 'owned-processes.json'
    script.write_text('''import json,os,subprocess,sys,time
from pathlib import Path
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
Path(sys.argv[1]).write_text(json.dumps([os.getpid(),child.pid]),encoding='utf-8')
time.sleep(60)
''', encoding='utf-8')
    with (tmp_path / 'owned-process.log').open('w', encoding='utf-8') as log:
        with pytest.raises(subprocess.TimeoutExpired):
            runner.run_tests([sys.executable, str(script), str(identity)], os.environ.copy(), log, timeout=3)
    pids = json.loads(identity.read_text(encoding='utf-8'))
    assert len(set(pids)) == 2
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    for pid in pids:
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if handle:
            try:
                assert kernel.WaitForSingleObject(handle, 0) == 0, 'Owned process still running after timeout'
            finally:
                kernel.CloseHandle(handle)
