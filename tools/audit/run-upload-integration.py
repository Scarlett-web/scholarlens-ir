"""Own a fresh loopback ES and run real upload/ownership acceptance; no external target URL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files_identity(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in root.rglob('*') if p.is_file()}


def get_json(url):
    # A loopback-only opener must not inherit a proxy from the user's shell.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=2) as response:
        return json.load(response)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def listening(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.5)
        return connection.connect_ex(('127.0.0.1', port)) == 0


def java_command(home, config):
    system = platform.system()
    if system == 'Windows':
        java, distribution = home / 'jdk/bin/java.exe', 'zip'
    elif system == 'Darwin':
        candidates = [home / 'jdk.app/Contents/Home/bin/java', home / 'jdk/Contents/Home/bin/java']
        java, distribution = next((p for p in candidates if p.is_file()), candidates[0]), 'tar'
    elif system == 'Linux':
        java, distribution = home / 'jdk/bin/java', 'tar'
    else:
        raise RuntimeError('Unsupported platform for native Elasticsearch acceptance')
    if not java.is_file():
        raise RuntimeError('Bundled Java is missing for this platform; select a matching --es-home')
    classpath = os.pathsep.join(str(home / p) for p in ('lib/*', 'lib/cli-launcher/*'))
    return [str(java), '-Xms4m', '-Xmx64m', '-XX:+UseSerialGC', '-Dcli.name=server',
            '-Djava.io.tmpdir=' + str(config.parent / 'tmp'),
            '-XX:ErrorFile=' + str(config.parent / 'logs/launcher-hs_err_pid%p.log'),
            '-Dcli.libs=lib/tools/server-cli', '-Des.path.home=' + str(home),
            '-Des.path.conf=' + str(config), '-Des.distribution.type=' + distribution,
            '-Des.java.type=bundled', '-cp', classpath, 'org.elasticsearch.launcher.CliToolLauncher']


def isolated_environment(output, config, home, model, http_port, transport_port, nonce):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith((
        'ELASTICSEARCH_', 'SCHOLARLENS_', 'ES_', 'AI_', 'SMTP_', 'GROBID_', 'JAVA_',
        '_JAVA_', 'JDK_JAVA_', 'OTEL_', 'APM_')) and k.upper() not in (
        'VECTOR_INDEX', 'UPLOADS_INDEX', 'UPLOAD_VECTOR_INDEX', 'EMBEDDING_MODEL_DIR',
        'FRONTEND_DIST', 'CORS_ORIGINS', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'KEYSTORE_PASSWORD')}
    env.update({
        'ES_PATH_CONF': str(config), 'ES_JAVA_HOME': str(Path(java_command(home, config)[0]).parent.parent),
        'ES_TMPDIR': str(output / 'tmp'),
        'ES_JAVA_OPTS': '-Xms512m -Xmx512m -XX:MaxDirectMemorySize=256m -XX:ActiveProcessorCount=2',
        'ELASTICSEARCH_URL': f'http://127.0.0.1:{http_port}',
        'ELASTICSEARCH_INDEX': f'scholarlens-papers-acceptance-{nonce}-real',
        'VECTOR_INDEX': f'scholarlens-vectors-acceptance-{nonce}',
        'UPLOADS_INDEX': f'scholarlens-uploads-acceptance-{nonce}-real',
        'UPLOAD_VECTOR_INDEX': f'scholarlens-vectors-uploads-acceptance-{nonce}',
        'SCHOLARLENS_RUNTIME_DIR': str(output / 'bootstrap-runtime'),
        'EMBEDDING_MODEL_DIR': str(model), 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
        'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1',
        'TMPDIR': str(output / 'tmp'), 'TEMP': str(output / 'tmp'), 'TMP': str(output / 'tmp'),
        'SCHOLARLENS_ISOLATED_UPLOAD_CONFIG': str(output / 'isolation.json'),
    })
    return env


def kill_owned_tree(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        result = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode and process.poll() is None:
            raise RuntimeError('Failed to stop this run\'s owned process tree')
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=15)


def run_tests(command, env, log, timeout=300):
    process = subprocess.Popen(command, cwd=REPO, env=env, stdin=subprocess.DEVNULL,
        stdout=log, stderr=subprocess.STDOUT,
        **({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
           if os.name == 'nt' else {'start_new_session': True}))
    try:
        return process.wait(timeout=timeout)
    except BaseException:
        kill_owned_tree(process)
        raise


def stop_owned(process, http_port, transport_port):
    # Closing this launcher's stdin asks its server child to shut down normally.
    if process.stdin:
        process.stdin.close()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        kill_owned_tree(process)
    # Do not infer that a launcher exiting means its child has exited.
    deadline = time.monotonic() + 10
    while (listening(http_port) or listening(transport_port)) and time.monotonic() < deadline:
        time.sleep(0.25)
    if listening(http_port) or listening(transport_port):
        raise RuntimeError('Owned ES listener remains after launcher shutdown; inspect this run, do not restart')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--es-home', type=Path, default=REPO / 'infra/.runtime/elasticsearch-8.19.23')
    parser.add_argument('--model-dir', type=Path, default=REPO / 'backend/.runtime/minilm')
    arguments = parser.parse_args()
    home = arguments.es_home.resolve(strict=True)
    model = arguments.model_dir.resolve(strict=True)
    # Verify platform/tool discovery before creating files or starting any process.
    java_command(home, home / 'config')
    native_before = files_identity(home / 'config')
    model_before = files_identity(model)
    nonce = uuid.uuid4().hex[:12]
    assert (REPO / 'tools/audit/reports').resolve(strict=True).is_relative_to(REPO.resolve(strict=True))
    output = REPO / 'tools/audit/reports' / ('upload-integration-' + time.strftime('%Y%m%d-%H%M%S') + '-' + nonce)
    output.mkdir(parents=True, exist_ok=False)
    output = output.resolve(strict=True)
    for name in ('config', 'data', 'logs', 'tmp'):
        (output / name).mkdir()
    config = output / 'config'
    for name in ('jvm.options', 'log4j2.properties'):
        shutil.copy2(home / 'config' / name, config / name)
    options = (config / 'jvm.options').read_text(encoding='utf-8')
    options = options.replace('-XX:ErrorFile=hs_err_pid%p.log', '-XX:ErrorFile=' + str(output / 'logs/hs_err_pid%p.log'))
    options = options.replace('-Xlog:gc*,gc+age=trace,safepoint:file=gc.log:utctime,level,pid,tags:filecount=32,filesize=64m', '-Xlog:gc=warning:stderr')
    options += '\n-XX:HeapDumpPath=' + str(output / 'logs') + '\n'
    (config / 'jvm.options').write_text(options, encoding='utf-8')
    http_port, transport_port = free_port(), free_port()
    while transport_port == http_port:
        transport_port = free_port()
    cluster = 'scholarlens-acceptance-' + nonce
    settings = {'cluster.name': cluster, 'node.name': cluster,
                'path.data': str(output / 'data'), 'path.logs': str(output / 'logs'),
                'network.host': '127.0.0.1', 'http.port': http_port, 'transport.port': transport_port,
                'discovery.type': 'single-node', 'xpack.security.enabled': False,
                'xpack.security.autoconfiguration.enabled': False, 'xpack.ml.enabled': False,
                'ingest.geoip.downloader.enabled': False}
    (config / 'elasticsearch.yml').write_text(''.join(k + ': ' + json.dumps(v) + '\n' for k, v in settings.items()), encoding='utf-8')
    env = isolated_environment(output, config, home, model, http_port, transport_port, nonce)
    identity = {'cluster': cluster, 'nonce': nonce, 'output': str(output),
                'url': env['ELASTICSEARCH_URL'], 'synthetic_data': True,
                'base_alias': env['ELASTICSEARCH_INDEX'], 'vector_alias': env['VECTOR_INDEX']}
    report = {'passed': False, 'platform': platform.system(), 'architecture': platform.machine(), 'synthetic_data': True,
              'scope': 'fresh native ES/SQLite, actual MiniLM CPU inference and production app routes',
              'output': str(output), 'cluster': cluster, 'http_port': http_port, 'transport_port': transport_port}
    process = None
    try:
        with (output / 'elasticsearch-console.log').open('w', encoding='utf-8') as log:
            # The vendor launcher resolves its bundled modules relative to ES home.
            # All writable paths (including JVM temp/error/GC output) are overridden above.
            process = subprocess.Popen(java_command(home, config), cwd=home, env=env,
                stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                **({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
                   if os.name == 'nt' else {'start_new_session': True}))
            report['launcher_pid'] = process.pid
            print(json.dumps({'event': 'starting', 'output': str(output), 'pid': process.pid}), flush=True)
            deadline = time.monotonic() + 120
            next_update = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    raise RuntimeError('ES launcher exited before readiness; inspect this run console log')
                try:
                    info = get_json(identity['url'])
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    info = None
                if info:
                    if info['cluster_name'] != cluster or info['name'] != cluster:
                        raise RuntimeError('Unexpected ES instance on selected port; refusing all writes')
                    assert info['version']['number'] == '8.19.23'
                    assert info['cluster_uuid'] not in ('', '_na_')
                    identity['cluster_uuid'] = info['cluster_uuid']
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError('Owned ES did not become ready; no second instance will be started')
                if time.monotonic() >= next_update:
                    print(json.dumps({'event': 'waiting_for_owned_es', 'pid': process.pid}), flush=True)
                    next_update = time.monotonic() + 15
                time.sleep(0.5)
            assert get_json(identity['url'] + '/_cat/indices?format=json') == []
            nodes = get_json(identity['url'] + '/_nodes/_local/settings,process?flat_settings=true')['nodes']
            assert len(nodes) == 1
            node = next(iter(nodes.values()))
            data_path = node['settings']['path.data']
            assert Path(data_path[0] if isinstance(data_path, list) else data_path).resolve() == output / 'data'
            assert node['settings']['network.host'] == '127.0.0.1'
            report['server_pid'] = node['process']['id']
            (output / 'isolation.json').write_text(json.dumps(identity, indent=2), encoding='utf-8')
            report['cluster_uuid'] = identity['cluster_uuid']
            print(json.dumps({'event': 'running_real_integration', 'cluster': cluster}), flush=True)
            with (output / 'pytest-console.txt').open('w', encoding='utf-8') as test_log:
                test_exit_code = run_tests([sys.executable, '-m', 'pytest',
                    'backend/tests/test_upload_integration_isolated.py', '-q', '--tb=short',
                    '-o', 'cache_dir=' + str(output / 'pytest-cache'),
                    '--basetemp=' + str(output / 'pytest-runtime'), '--junitxml=' + str(output / 'junit.xml')], env, test_log)
            report['pytest_exit_code'] = test_exit_code
            report['passed'] = test_exit_code == 0
            if report['passed']:
                suite = ET.parse(output / 'junit.xml').getroot()
                cases = suite.findall('.//testcase')
                assert len(cases) == 5 and not suite.findall('.//skipped')
                checks = json.loads((output / 'checks.json').read_text(encoding='utf-8'))
                assert len(checks['chains']) == 2 and all(c['passed'] for c in checks['chains'])
                assert all(c['expected'] == c['actual'] for c in checks['matrix'])
                report['test_groups'] = len(cases)
                report['route_assertions'] = len(checks['matrix'])
    except Exception as error:
        report['passed'] = False
        report['error'] = str(error)
    finally:
        if process is not None:
            try:
                stop_owned(process, http_port, transport_port)
                report['owned_es_stopped'] = True
            except Exception as error:
                report['owned_es_stopped'] = False
                report['cleanup_error'] = str(error)
                report['passed'] = False
        report['installation_config_unchanged'] = native_before == files_identity(home / 'config')
        report['model_files_unchanged'] = model_before == files_identity(model)
        report['ports_closed'] = not listening(http_port) and not listening(transport_port)
        if not all(report[k] for k in ('installation_config_unchanged', 'model_files_unchanged', 'ports_closed')):
            report['passed'] = False
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
