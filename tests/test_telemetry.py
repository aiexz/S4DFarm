#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
for mod in ['redis', 'redis.exceptions', 'psycopg2', 'psycopg2.pool', 'psycopg2.extras', 'prometheus_client', 'flask']:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# Add server and client to path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / 'server' / 'app'))
sys.path.insert(0, str(root_dir / 'client'))

from api import resolve_team_and_service, calc_percentiles
from start_sploit import ExecutionStorage, guess_service, get_sploit_hash


class TestTelemetry(unittest.TestCase):
    def test_calc_percentiles(self):
        self.assertEqual(calc_percentiles([]), (0.0, 0.0))
        self.assertEqual(calc_percentiles([1.5]), (1.5, 1.5))
        durations = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        p50, p95 = calc_percentiles(durations)
        self.assertEqual(p50, 6.0)
        self.assertEqual(p95, 10.0)

    def test_resolve_team_and_service(self):
        teams_config = {
            'Team #1': '10.60.1.3',
            'Team #2': '10.60.2.3:8080',
            'Team #3': '10.60.3.3',
        }

        # 1. Exact team name match
        team, service = resolve_team_and_service('Team #1', 'bank', 'exploit.py', teams_config)
        self.assertEqual(team, 'Team #1')
        self.assertEqual(service, 'bank')

        # 2. Reverse lookup by IP
        team, service = resolve_team_and_service('10.60.1.3', '', 'sploit_crypto.py', teams_config)
        self.assertEqual(team, 'Team #1')
        self.assertEqual(service, 'sploit_crypto')

        # 3. Reverse lookup by IP with port
        team, service = resolve_team_and_service('10.60.2.3:8080', '', 'run.py', teams_config)
        self.assertEqual(team, 'Team #2')
        self.assertEqual(service, 'port_8080')

        # 4. Unknown target IP fallback
        team, service = resolve_team_and_service('192.168.1.1:9999', '', '', teams_config)
        self.assertEqual(team, '192.168.1.1')
        self.assertEqual(service, 'port_9999')

    def test_execution_storage(self):
        storage = ExecutionStorage()
        self.assertEqual(storage.queue_size, 0)

        storage.add({'id': 1, 'team': 'Team #1'})
        storage.add({'id': 2, 'team': 'Team #2'})
        self.assertEqual(storage.queue_size, 2)

        picked = storage.pick_executions(1)
        self.assertEqual(len(picked), 1)
        self.assertEqual(picked[0]['id'], 1)

        storage.mark_as_sent(1)
        self.assertEqual(storage.queue_size, 1)

        picked2 = storage.pick_executions(10)
        self.assertEqual(len(picked2), 1)
        self.assertEqual(picked2[0]['id'], 2)
        storage.mark_as_sent(1)
        self.assertEqual(storage.queue_size, 0)

    def test_guess_service_and_hash(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("#!/usr/bin/env python3\nPORT = 31337\nprint('sploit')\n")
            sploit_path = f.name

        try:
            h = get_sploit_hash(sploit_path)
            self.assertEqual(len(h), 16)

            svc = guess_service(sploit_path, team_addr='10.0.0.1')
            self.assertEqual(svc, 'port_31337')

            # Override via args
            svc_custom = guess_service(sploit_path, args_service='custom_svc')
            self.assertEqual(svc_custom, 'custom_svc')

            # Target address port has precedence over content
            svc_addr_port = guess_service(sploit_path, team_addr='10.0.0.1:8000')
            self.assertEqual(svc_addr_port, 'port_8000')
        finally:
            os.remove(sploit_path)

    def test_run_sploit_telemetry(self):
        import re
        from argparse import Namespace
        from start_sploit import run_sploit, execution_storage

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("#!/usr/bin/env python3\nimport sys\nprint('FLAG{TEST_FLAG_123}')\nsys.exit(0)\n")
            sploit_path = f.name
        os.chmod(sploit_path, 0o755)

        try:
            args = Namespace(
                sploit=sploit_path,
                interpreter=sys.executable,
                endless=False,
                verbose_attacks=0,
                client_id='test-worker-1',
                service='test_service',
            )
            flag_format = re.compile(r'FLAG\{[A-Z0-9_]+\}')

            # Clear queue before test
            execution_storage.pick_executions(1000)
            execution_storage.mark_as_sent(1000)

            run_sploit(args, 'Team #1', '10.60.1.3', 1, 5.0, flag_format)

            self.assertEqual(execution_storage.queue_size, 1)
            exec_item = execution_storage.pick_executions(1)[0]

            self.assertEqual(exec_item['client_id'], 'test-worker-1')
            self.assertEqual(exec_item['team'], 'Team #1')
            self.assertEqual(exec_item['round'], 1)
            self.assertEqual(exec_item['exit_code'], 0)
            self.assertEqual(exec_item['timeout'], False)
            self.assertEqual(exec_item['flags_found'], 1)
            self.assertIn('FLAG{TEST_FLAG_123}', exec_item['output_preview'])
            self.assertGreaterEqual(exec_item['duration'], 0.0)
        finally:
            os.remove(sploit_path)

    def test_regression_detection(self):
        # Simulate executions over multiple rounds for a sploit
        # Round 1: 5 successes
        # Round 2: 5 successes
        # Round 3: 1 success, 4 failures (sudden drop from 100% to 20%)
        executions = []
        for r in [1, 2]:
            for i in range(5):
                executions.append({
                    'id': len(executions) + 1,
                    'sploit_id': 'vuln_sploit.py',
                    'sploit_hash': 'abcdef',
                    'client_id': 'worker-1',
                    'service': 'port_8080',
                    'team': f'Team #{i}',
                    'round': r,
                    'start_time': 1000 + r * 100 + i,
                    'end_time': 1001 + r * 100 + i,
                    'duration': 1.0,
                    'exit_code': 0,
                    'timeout': False,
                    'flags_found': 1,
                    'output_preview': 'flag',
                })
        for i in range(5):
            executions.append({
                'id': len(executions) + 1,
                'sploit_id': 'vuln_sploit.py',
                'sploit_hash': 'abcdef',
                'client_id': 'worker-1',
                'service': 'port_8080',
                'team': f'Team #{i}',
                'round': 3,
                'start_time': 1300 + i,
                'end_time': 1301 + i,
                'duration': 1.0,
                'exit_code': 0 if i == 0 else 1, # 1 success, 4 failures = 20%
                'timeout': False,
                'flags_found': 1 if i == 0 else 0,
                'output_preview': 'error' if i > 0 else 'flag',
            })

        from collections import defaultdict
        sploit_rounds = defaultdict(list)
        for e in executions:
            sploit_rounds[e['round']].append(e)

        sorted_rounds = sorted(sploit_rounds.keys())
        latest_round = sorted_rounds[-1]
        latest_runs = sploit_rounds[latest_round]
        latest_successes = sum(1 for e in latest_runs if e['exit_code'] == 0 and not e['timeout'])
        latest_rate = round(latest_successes / len(latest_runs) * 100, 1)

        prior_runs = [e for r in sorted_rounds[:-1] for e in sploit_rounds[r]]
        prior_successes = sum(1 for e in prior_runs if e['exit_code'] == 0 and not e['timeout'])
        prior_rate = round(prior_successes / len(prior_runs) * 100, 1)

        self.assertEqual(prior_rate, 100.0)
        self.assertEqual(latest_rate, 20.0)
        self.assertTrue(prior_rate >= 50.0 and latest_rate <= 20.0 and len(latest_runs) >= 3)


if __name__ == '__main__':
    unittest.main()
