#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XXAI 广场测试用例集 - 统一运行入口

Usage:
    python run_all.py                          # 跑全部套件
    python run_all.py --suite s99_smoke        # 跑单个套件
    python run_all.py --suite s01_eleven_issues s03_ux_quality   # 跑多个
    python run_all.py --env dev                # 指定环境 (默认 dev)
    python run_all.py --list                   # 列出所有套件
"""
import argparse
import importlib
import io
import json
import os
import sys
import time

# 让脚本支持双向 import (无论从根还是从 testcases/ 跑)
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(HERE, '.env'))
except ImportError:
    # fallback: 手动解析 .env, 不强依赖 python-dotenv
    env_file = os.path.join(HERE, '.env')
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8-sig') as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith('#') or '=' not in _line:
                    continue
                _k, _v = _line.split('=', 1)
                _k = _k.strip(); _v = _v.strip().strip('"').strip("'")
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

from lib import HTTPClient, Reporter


ALL_SUITES = {
    's01_eleven_issues':   'suites.s01_eleven_issues',
    's02_full_regression': 'suites.s02_full_regression',
    's03_ux_quality':      'suites.s03_ux_quality',
    's04_interactions':    'suites.s04_interactions',
    's05_stress_abuse':    'suites.s05_stress_abuse',
    's06_video_hotlink':   'suites.s06_video_hotlink',
    's07_publish_depth':   'suites.s07_publish_depth',
    's99_smoke':           'suites.s99_smoke',
}


def load_env(env_name: str) -> dict:
    path = os.path.join(HERE, 'config', f'env_{env_name}.json')
    if not os.path.exists(path):
        raise FileNotFoundError(f'环境配置不存在: {path}')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def run_one(suite_key: str, client, ts: str, env_name: str) -> dict:
    print(f'\n{"="*70}\n>>> 运行套件: {suite_key}\n{"="*70}')
    mod = importlib.import_module(ALL_SUITES[suite_key])
    outdir = os.path.join(HERE, 'reports', ts)
    reporter = Reporter(suite=suite_key, outdir=outdir,
                        meta={'env': env_name,
                              'token_user': os.environ.get('TOKEN_USER', 'chenzhuo (user_id=21)')})
    try:
        mod.run(client, reporter)
    except Exception as e:
        import traceback
        traceback.print_exc()
        reporter.add_finding('high', 'runner', f'套件 {suite_key} 异常', str(e))
    json_path, md_path = reporter.dump()
    s = reporter.stats()
    print(f'    用例: {s["total_cases"]}  通过: {s["passed"]}  失败: {s["failed"]}  '
          f'通过率: {s["pass_rate"]}%')
    print(f'    发现 高/中/低: {s["findings_high"]} / {s["findings_medium"]} / {s["findings_low"]}')
    print(f'    报告: {md_path}')
    return {'suite': suite_key, 'stats': s, 'json': json_path, 'md': md_path}


def write_summary(results, outdir):
    md = ['# 全量回归汇总\n', f'**生成时间**: {time.strftime("%Y-%m-%d %H:%M:%S")}\n',
          '\n## 套件结果\n',
          '| 套件 | 用例 | 通过 | 失败 | 通过率 | 高 | 中 | 低 |',
          '|---|---|---|---|---|---|---|---|']
    for r in results:
        s = r['stats']
        md.append(f'| {r["suite"]} | {s["total_cases"]} | {s["passed"]} | {s["failed"]} | '
                  f'{s["pass_rate"]}% | {s["findings_high"]} | {s["findings_medium"]} | {s["findings_low"]} |')
    md.append('\n## 详细报告链接\n')
    for r in results:
        md.append(f'- [{r["suite"]}]({os.path.basename(r["md"])})  '
                  f'JSON: `{os.path.basename(r["json"])}`')
    out_md = os.path.join(outdir, 'summary.md')
    with open(out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    return out_md


def main():
    p = argparse.ArgumentParser(description='XXAI 广场测试用例集运行入口')
    p.add_argument('--suite', nargs='+', help='指定套件 (可多个)', default=None)
    p.add_argument('--env',   default=os.environ.get('ENV', 'dev'), help='环境名 (默认 dev)')
    p.add_argument('--list',  action='store_true', help='列出所有套件')
    args = p.parse_args()

    if args.list:
        print('可用套件:')
        for k in ALL_SUITES: print(f'  - {k}')
        return

    # token
    token = os.environ.get('ADMIN_TOKEN')
    if not token:
        print('!! 缺少 ADMIN_TOKEN 环境变量, 请复制 .env.example 为 .env 并填值')
        sys.exit(2)

    env = load_env(args.env)
    print(f'>>> 环境: {env["name"]}  域名: {env["admin_api"]}')

    client = HTTPClient(env, admin_token=token)
    if not client.alive():
        print('!! 后台不可达或 token 失效'); sys.exit(3)
    print('>>> 探活: OK')

    ts = time.strftime('%Y%m%d_%H%M%S')
    outdir = os.path.join(HERE, 'reports', ts)
    os.makedirs(outdir, exist_ok=True)

    suites = args.suite or list(ALL_SUITES.keys())
    invalid = [s for s in suites if s not in ALL_SUITES]
    if invalid:
        print(f'!! 未知套件: {invalid}, 可用: {list(ALL_SUITES.keys())}'); sys.exit(2)

    results = []
    for s in suites:
        results.append(run_one(s, client, ts, env['name']))

    summary = write_summary(results, outdir)
    print(f'\n>>> 汇总报告: {summary}')


if __name__ == '__main__':
    main()
