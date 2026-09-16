#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

SPL_TEST_PATH = 'client/spl_test.py'
with open(SPL_TEST_PATH, 'w') as f:
    f.write('''#!/usr/bin/env python3
import sys
import random

if len(sys.argv) < 2:
    sys.exit(1)

target = sys.argv[1]
PORT = 8080
print(f"Attacking target {target} on port {PORT}")
flag = f"VolgaCTF{{team.service.{random.randint(10000, 99999)}}}"
print(f"Found flag: {flag}", flush=True)
sys.exit(0)
''')
os.chmod(SPL_TEST_PATH, 0o755)

print("Starting client/start_sploit.py against http://localhost:5137...")
cmd = [
    sys.executable,
    'client/start_sploit.py',
    SPL_TEST_PATH,
    '--server-url', 'http://localhost:5137',
    '--server-pass', '1234',
    '--client-id', 'e2e-tester',
    '--attack-period', '3',
    '--pool-size', '10',
    '-v', '1',
]

proc = subprocess.Popen(cmd)
try:
    # Let it run for 1 attack cycle + post loop (approx 7 seconds)
    print("Waiting 8 seconds for attack run and telemetry posting...")
    time.sleep(8)
finally:
    print("Sending SIGINT to start_sploit.py...")
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    if os.path.exists(SPL_TEST_PATH):
        os.remove(SPL_TEST_PATH)

print("Querying /api/telemetry from server...")
req = urllib.request.Request(
    'http://localhost:5137/api/telemetry',
    headers={'Authorization': '1234'}
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())

print("\n=== TELEMETRY SUMMARY ===")
print(f"Total sploits tracked: {len(data['sploits'])}")
for sp in data['sploits']:
    print(f"  Sploit: {sp['sploit_id']}, Service: {sp['service']}, Runs: {sp['total_runs']}, "
          f"Success: {sp['success_rate']}%, Flags: {sp['flags_found']}, "
          f"p50: {sp['p50_duration']}s, p95: {sp['p95_duration']}s")

print(f"\nTotal teams tracked: {len(data['teams'])}")
active_teams = [t for t in data['teams'] if t['total_runs'] > 0]
unhit_teams = data['unhit_teams']
print(f"  Active teams hit: {len(active_teams)}")
print(f"  Unhit teams: {len(unhit_teams)}")

print(f"\nRecent executions recorded: {len(data['recent_executions'])}")
if data['recent_executions']:
    first = data['recent_executions'][0]
    print(f"  Sample execution: sploit={first['sploit_id']}, team={first['team']}, "
          f"service={first['service']}, exit_code={first['exit_code']}, duration={first['duration']}s")
    print(f"  Output preview snippet: {repr(first['output_preview'][:80])}")

assert len(data['sploits']) > 0, "Expected at least one sploit tracked"
assert len(data['recent_executions']) > 0, "Expected recent executions recorded"
assert data['sploits'][0]['sploit_id'] == 'spl_test.py'
assert data['sploits'][0]['service'] == 'port_8080'
assert data['sploits'][0]['success_rate'] > 0

print("\n ALL E2E CHECKS PASSED SUCCESSFULLY!")
