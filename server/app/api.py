import importlib
import time
from collections import defaultdict
from datetime import datetime

import redis.exceptions
from flask import request, jsonify, Blueprint
from prometheus_client import Counter, Gauge

import auth
import reloader
from database import db_cursor
from models import FlagStatus

api = Blueprint('api', __name__, url_prefix='/api')

FLAGS_RECEIVED = Counter(
    'flags_received',
    'Number of flags received',
    ['sploit', 'team'],
)

EXECUTIONS_RECEIVED = Counter(
    'executions_received',
    'Number of executions received',
    ['sploit', 'team'],
)

TOTAL_TEAMS = Gauge('total_teams', 'Number of teams')
TOTAL_TEAMS.set_function(lambda: len(reloader.get_config()['TEAMS']))


@api.route('/get_config')
@auth.auth_required
def get_config():
    config = reloader.get_config()
    return jsonify({
        key: value
        for key, value in config.items()
        if 'PASSWORD' not in key and 'TOKEN' not in key
    })


@api.route('/post_flags', methods=['POST'])
@auth.auth_required
def post_flags():
    flags = request.json
    cur_time = round(time.time())
    config = reloader.get_config()

    if config.get('SYSTEM_VALIDATOR'):
        validator_module = importlib.import_module('validators.' + config['SYSTEM_VALIDATOR'])
        flags = validator_module.validate_flags(flags, config)

    rows = [
        {
            'flag': flag['flag'],
            'sploit': flag['sploit'],
            'team': flag['team'],
            'time': cur_time,
            'status': FlagStatus.QUEUED.name,
        }
        for flag in flags
    ]

    with db_cursor() as (conn, curs):
        curs.executemany(
            """
            INSERT INTO flags (flag, sploit, team, time, status)
            VALUES (%(flag)s, %(sploit)s, %(team)s, %(time)s, %(status)s)
            ON CONFLICT DO NOTHING
            """,
            rows,
        )
        conn.commit()

    for flag in flags:
        FLAGS_RECEIVED.labels(sploit=flag['sploit'], team=flag['team']).inc()

    return ''

def resolve_team_and_service(team, service, sploit_id, teams_config):
    if team in teams_config:
        resolved_team = team
    else:
        addr_to_name = {}
        for t_name, t_addr in teams_config.items():
            addr_to_name[t_addr] = t_name
            if ':' in t_addr:
                addr_to_name[t_addr.split(':')[0]] = t_name
        raw_team = team.split(':')[0] if team else ''
        resolved_team = addr_to_name.get(team) or addr_to_name.get(raw_team) or raw_team or 'unknown'

    resolved_service = service
    if not resolved_service or resolved_service == 'unknown':
        if ':' in (team or ''):
            resolved_service = f"port_{team.split(':')[1]}"
        elif sploit_id:
            resolved_service = sploit_id.rsplit('.', 1)[0]
        else:
            resolved_service = 'default'

    return resolved_team, resolved_service


def calc_percentiles(durations):
    if not durations:
        return 0.0, 0.0
    sorted_d = sorted(durations)
    n = len(sorted_d)
    p50 = sorted_d[int(n * 0.50)]
    p95 = sorted_d[min(int(n * 0.95), n - 1)]
    return round(float(p50), 3), round(float(p95), 3)


@api.route('/post_executions', methods=['POST'])
@auth.auth_required
def post_executions():
    data = request.json
    if not data:
        return jsonify({'status': 'ok', 'count': 0})
    if not isinstance(data, list):
        data = [data]

    config = reloader.get_config()
    teams_config = config.get('TEAMS', {})

    rows = []
    for item in data:
        sploit_id = str(item.get('sploit_id', ''))
        team_raw = str(item.get('team', ''))
        service_raw = str(item.get('service', ''))
        resolved_team, resolved_service = resolve_team_and_service(
            team_raw, service_raw, sploit_id, teams_config
        )

        start_time = float(item.get('start_time', time.time()))
        end_time = float(item.get('end_time', start_time))
        duration = float(item.get('duration', round(end_time - start_time, 3)))

        rows.append({
            'client_id': str(item.get('client_id', 'unknown')),
            'sploit_id': sploit_id,
            'sploit_hash': str(item.get('sploit_hash', '')),
            'service': resolved_service,
            'team': resolved_team,
            'round': int(item.get('round', 1)),
            'start_time': start_time,
            'end_time': end_time,
            'duration': duration,
            'exit_code': int(item.get('exit_code', 0)),
            'timeout': bool(item.get('timeout', False)),
            'flags_found': int(item.get('flags_found', 0)),
            'output_preview': str(item.get('output_preview', ''))[:2000],
        })

    if rows:
        with db_cursor() as (conn, curs):
            curs.executemany(
                """
                INSERT INTO executions (
                    client_id, sploit_id, sploit_hash, service, team, round,
                    start_time, end_time, duration, exit_code, timeout,
                    flags_found, output_preview
                )
                VALUES (
                    %(client_id)s, %(sploit_id)s, %(sploit_hash)s, %(service)s, %(team)s, %(round)s,
                    %(start_time)s, %(end_time)s, %(duration)s, %(exit_code)s, %(timeout)s,
                    %(flags_found)s, %(output_preview)s
                )
                """,
                rows,
            )
            conn.commit()

        for row in rows:
            EXECUTIONS_RECEIVED.labels(sploit=row['sploit_id'], team=row['team']).inc()

    return jsonify({'status': 'ok', 'count': len(rows)})


@api.route('/telemetry', methods=['GET'])
@auth.auth_required
def get_telemetry():
    args = request.args
    filter_sploit = args.get('sploit')
    filter_team = args.get('team')
    filter_round = args.get('round')
    filter_service = args.get('service')

    conditions = []
    params = []
    if filter_sploit:
        conditions.append('sploit_id = %s')
        params.append(filter_sploit)
    if filter_team:
        conditions.append('team = %s')
        params.append(filter_team)
    if filter_round:
        conditions.append('round = %s')
        params.append(int(filter_round))
    if filter_service:
        conditions.append('service = %s')
        params.append(filter_service)

    where_clause = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    with db_cursor(True) as (_, curs):
        curs.execute(f"SELECT * FROM executions {where_clause} ORDER BY start_time DESC LIMIT 5000", params)
        executions = curs.fetchall()

    teams_config = reloader.get_config().get('TEAMS', {})

    team_map = defaultdict(list)
    sploit_map = defaultdict(list)
    round_map = defaultdict(list)

    for ex in executions:
        team_map[ex['team']].append(ex)
        sploit_map[ex['sploit_id']].append(ex)
        round_map[ex['round']].append(ex)

    teams_result = []
    all_teams = list(teams_config.keys())
    for extra_team in team_map.keys():
        if extra_team not in all_teams:
            all_teams.append(extra_team)

    unhit_teams = []
    for team_name in all_teams:
        execs = team_map.get(team_name, [])
        addr = teams_config.get(team_name, '')
        if not execs:
            unhit_teams.append(team_name)
            teams_result.append({
                'team': team_name,
                'address': addr,
                'total_runs': 0,
                'success_runs': 0,
                'success_rate': 0.0,
                'timeout_runs': 0,
                'timeout_rate': 0.0,
                'flags_found': 0,
                'flags_per_run': 0.0,
                'p50_duration': 0.0,
                'p95_duration': 0.0,
                'last_run': None,
                'last_success': None,
                'status': 'unhit',
            })
            continue

        total = len(execs)
        successes = [e for e in execs if e['exit_code'] == 0 and not e['timeout']]
        timeouts = [e for e in execs if e['timeout']]
        flags = sum(e['flags_found'] for e in execs)
        durations = [e['duration'] for e in execs if e['duration'] is not None]
        p50, p95 = calc_percentiles(durations)

        last_run = max(e['start_time'] for e in execs)
        last_success = max((e['start_time'] for e in successes), default=None)

        success_rate = round(len(successes) / total * 100, 1)
        timeout_rate = round(len(timeouts) / total * 100, 1)
        status = 'ok' if (success_rate >= 50 and execs[0]['exit_code'] == 0) else 'failing'

        teams_result.append({
            'team': team_name,
            'address': addr,
            'total_runs': total,
            'success_runs': len(successes),
            'success_rate': success_rate,
            'timeout_runs': len(timeouts),
            'timeout_rate': timeout_rate,
            'flags_found': flags,
            'flags_per_run': round(flags / total, 2),
            'p50_duration': p50,
            'p95_duration': p95,
            'last_run': last_run,
            'last_success': last_success,
            'status': status,
        })

    sploits_result = []
    regression_warnings = []
    for sploit_id, execs in sploit_map.items():
        total = len(execs)
        successes = [e for e in execs if e['exit_code'] == 0 and not e['timeout']]
        timeouts = [e for e in execs if e['timeout']]
        flags = sum(e['flags_found'] for e in execs)
        durations = [e['duration'] for e in execs if e['duration'] is not None]
        p50, p95 = calc_percentiles(durations)

        success_rate = round(len(successes) / total * 100, 1)
        timeout_rate = round(len(timeouts) / total * 100, 1)
        last_run = max(e['start_time'] for e in execs)
        last_success = max((e['start_time'] for e in successes), default=None)

        service = execs[0]['service'] if execs else 'default'
        sploit_hash = execs[0]['sploit_hash'] if execs else ''
        client_id = execs[0]['client_id'] if execs else ''

        sploit_rounds = defaultdict(list)
        for e in execs:
            sploit_rounds[e['round']].append(e)

        sorted_rounds = sorted(sploit_rounds.keys())
        regression_detected = False
        regression_reason = None
        if len(sorted_rounds) >= 2:
            latest_round = sorted_rounds[-1]
            latest_runs = sploit_rounds[latest_round]
            latest_successes = sum(1 for e in latest_runs if e['exit_code'] == 0 and not e['timeout'])
            latest_rate = round(latest_successes / len(latest_runs) * 100, 1) if latest_runs else 0.0

            prior_runs = [e for r in sorted_rounds[:-1] for e in sploit_rounds[r]]
            prior_successes = sum(1 for e in prior_runs if e['exit_code'] == 0 and not e['timeout'])
            prior_rate = round(prior_successes / len(prior_runs) * 100, 1) if prior_runs else 0.0

            if prior_rate >= 50.0 and latest_rate <= 20.0 and len(latest_runs) >= 3:
                regression_detected = True
                regression_reason = f"Success rate dropped from {prior_rate}% to {latest_rate}% in round {latest_round}"
                regression_warnings.append({
                    'sploit_id': sploit_id,
                    'round': latest_round,
                    'reason': regression_reason,
                    'prior_rate': prior_rate,
                    'latest_rate': latest_rate,
                })

        sploits_result.append({
            'sploit_id': sploit_id,
            'service': service,
            'sploit_hash': sploit_hash,
            'client_id': client_id,
            'total_runs': total,
            'success_runs': len(successes),
            'success_rate': success_rate,
            'timeout_runs': len(timeouts),
            'timeout_rate': timeout_rate,
            'flags_found': flags,
            'flags_per_run': round(flags / total, 2),
            'p50_duration': p50,
            'p95_duration': p95,
            'last_run': last_run,
            'last_success': last_success,
            'regression': regression_detected,
            'regression_reason': regression_reason,
        })

    rounds_result = []
    for r in sorted(round_map.keys(), reverse=True):
        r_execs = round_map[r]
        r_total = len(r_execs)
        r_success = sum(1 for e in r_execs if e['exit_code'] == 0 and not e['timeout'])
        r_flags = sum(e['flags_found'] for e in r_execs)
        r_durations = [e['duration'] for e in r_execs if e['duration'] is not None]
        avg_dur = round(sum(r_durations) / len(r_durations), 3) if r_durations else 0.0
        rounds_result.append({
            'round': r,
            'total_runs': r_total,
            'success_rate': round(r_success / r_total * 100, 1) if r_total else 0.0,
            'flags_found': r_flags,
            'avg_duration': avg_dur,
        })

    recent = [
        {
            'id': e['id'],
            'client_id': e['client_id'],
            'sploit_id': e['sploit_id'],
            'sploit_hash': e['sploit_hash'],
            'service': e['service'],
            'team': e['team'],
            'round': e['round'],
            'start_time': e['start_time'],
            'end_time': e['end_time'],
            'duration': e['duration'],
            'exit_code': e['exit_code'],
            'timeout': e['timeout'],
            'flags_found': e['flags_found'],
            'output_preview': e['output_preview'],
        }
        for e in executions[:100]
    ]

    return jsonify({
        'teams': teams_result,
        'sploits': sploits_result,
        'unhit_teams': unhit_teams,
        'regressions': regression_warnings,
        'rounds': rounds_result,
        'recent_executions': recent,
    })


@api.route('/filter_flags', methods=['GET'])
@auth.auth_required
def get_filtered_flags():
    filters = request.args

    conditions = []
    for column in ['sploit', 'status', 'team']:
        value = filters.get(column)
        if value:
            conditions.append((f'{column} = %s', value))

    for column in ['flag', 'checksystem_response']:
        value = filters.get(column)
        if value:
            conditions.append((f'POSITION(%s in LOWER({column})) > 0', value.lower()))

    for column in ['since', 'until']:
        value = filters.get(column, '').strip()
        if value:
            timestamp = round(datetime.strptime(value, '%Y-%m-%d %H:%M').timestamp())
            sign = '>=' if column == 'since' else '<='
            conditions.append((f'time {sign} %s', timestamp))

    page = int(filters.get('page', 1))
    if page < 1:
        raise ValueError('Invalid page')

    page_size = int(filters.get('page_size', 30))
    if page_size < 1 or page_size > 100:
        raise ValueError('Invalid page size')

    if conditions:
        chunks, values = list(zip(*conditions))
        conditions_sql = 'WHERE ' + ' AND '.join(chunks)
        conditions_args = list(values)
    else:
        conditions_sql = ''
        conditions_args = []

    sql = 'SELECT * FROM flags ' + conditions_sql + ' ORDER BY time DESC LIMIT %s OFFSET %s'
    args = conditions_args + [page_size, page_size * (page - 1)]

    count_sql = 'SELECT COUNT(*) as cnt FROM flags ' + conditions_sql
    count_args = conditions_args

    with db_cursor(True) as (_, curs):
        curs.execute(sql, args)
        flags = curs.fetchall()
        curs.execute(count_sql, count_args)
        total_count = curs.fetchone()['cnt']

    response = {
        'flags': list(map(dict, flags)),
        'page_size': page_size,
        'page': page,
        'total': total_count,
    }

    return jsonify(response)


@api.route('/filter_config', methods=['GET'])
@auth.auth_required
def get_filter_config():
    distinct_values = {}
    with db_cursor(True) as (_, curs):
        for column in ['sploit', 'status', 'team']:
            curs.execute(f'SELECT DISTINCT {column} FROM flags ORDER BY {column}')
            rows = curs.fetchall()
            distinct_values[column] = [item[column] for item in rows]

    config = reloader.get_config()

    server_tz_name = time.strftime('%Z')
    if server_tz_name.startswith('+'):
        server_tz_name = 'UTC' + server_tz_name

    response = {
        'filters': distinct_values,
        'flag_format': config['FLAG_FORMAT'],
        'server_tz': server_tz_name
    }

    return jsonify(response)

@api.route('/summary', methods=['GET'])
@auth.auth_required
def summary():
    filters = request.args

    conditions = []
    for column in ['sploit', 'status', 'team']:
        value = filters.get(column)
        if value:
            conditions.append((f'{column} = %s', value))

    for column in ['flag', 'checksystem_response']:
        value = filters.get(column)
        if value:
            conditions.append((f'POSITION(%s in LOWER({column})) > 0', value.lower()))

    for column in ['since', 'until']:
        value = filters.get(column, '').strip()
        if value:
            timestamp = round(datetime.strptime(value, '%Y-%m-%d %H:%M').timestamp())
            sign = '>=' if column == 'since' else '<='
            conditions.append((f'time {sign} %s', timestamp))

    # result for last x seconds
    for column in ['last']:
        value = filters.get(column, '').strip()
        if value:
            timestamp = round(datetime.strptime(datetime.timestamp()-value, '%Y-%m-%d %H:%M').timestamp())
            sign = '>='
            conditions.append((f'time {sign} %s', timestamp))

    if conditions:
        chunks, values = list(zip(*conditions))
        conditions_sql = 'WHERE ' + ' AND '.join(chunks)
        conditions_args = list(values)
    else:
        conditions_sql = ''
        conditions_args = []

    sql = 'SELECT * FROM flags ' + conditions_sql
    args = conditions_args

    with db_cursor(True) as (_, curs):
        curs.execute(sql, args)
        flags = curs.fetchall()

    result = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    response = filters.get('response','')
    for item in flags:
        key = item['checksystem_response'][:64] if response else item['status']
        result[item['sploit']][item['team']][key] += 1

    teams = reloader.get_config()['TEAMS']
    sploits=[]
    for sploit in result:
        tmp={}
        tmp['sploit_name'] = sploit
        tmp['teams']=[]
        for team in teams:
            if team not in result[sploit]:
                tmp['teams'].append({
                    'team': team,
                    'team_status': 'not status'
                })
        for team in result[sploit]:
            output = ''
            for key, value in result[sploit][team].items():
                output += f'{key}: {value}\n'
            tmp['teams'].append({
                'team': team,
                'team_status': output
            })
        sploits.append(tmp)

    return jsonify(sploits)

@api.route('/teams', methods=['GET'])
@auth.auth_required
def get_teams():
    teams = reloader.get_config()['TEAMS']
    response = list(map(
        lambda x: {'name': x[0], 'address': x[1]},
        teams.items(),
    ))
    return jsonify(response)
