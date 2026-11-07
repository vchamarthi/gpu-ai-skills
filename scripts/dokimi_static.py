#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Key-free Dokimi diagnostics using this pack's published README examples."""

import argparse
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def readme_queries(path, names):
    queries, active = {}, False
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.startswith('|') or not line.endswith('|'):
            active = False
            continue
        cells = [cell.strip().replace(r'\|', '|') for cell in re.split(r'(?<!\\)\|', line)[1:-1]]
        if [cell.lower() for cell in cells] == ['skill', 'useful for', 'example prompt']:
            active = True
            continue
        if not active or all(re.fullmatch(r'[-: ]*', cell) for cell in cells):
            continue
        match = re.match(r'`([^`]+)`', cells[0])
        if len(cells) != 3 or not match or match[1] not in names:
            raise ValueError(f'invalid skill example row in {path}: {line}')
        prompt = cells[2].strip('"“”').strip()
        if not prompt:
            raise ValueError(f'empty example prompt in {path}')
        rows = queries.setdefault(match[1], [])
        if prompt not in rows:
            rows.append(prompt)
    return queries


def cell(value):
    return html.escape(str(value)).replace('|', '&#124;').replace('`', '&#96;').replace('\n', ' ')


def findings(report):
    return {(p['level'], p['code'], p['path'], p['message']) for p in report.get('problems', [])}


def picks(row):
    return ', '.join(f'{name}: {count}' for name, count in sorted(row.items())) or 'not measured'


def render(candidate, queries, before, after, *, base, new_queries):
    names = {skill['name'] for skill in candidate['skills']}
    missing = sorted(names - queries.keys() - new_queries.keys())
    current, previous = findings(candidate), findings(base or {})
    lines = ['# Dokimi static diagnostics', '',
             f"Skills checked: {len(names)}. Existing README examples: {sum(map(len, queries.values()))}.",
             'No model or GPU execution. Lexical choices are review hints, not agent selection measurements.', '']
    if base is not None:
        lines += [f'Catalog findings: {len(current - previous)} new; {len(previous - current)} resolved.', '']
    lines += ['## Catalog findings', '', '| Level | Diagnostic | Path | Detail |', '| --- | --- | --- | --- |']
    for row in sorted(current):
        lines.append('| ' + ' | '.join(cell(value) for value in row) + ' |')
    if not current:
        lines.append('| — | No catalog findings | — | — |')
    lines += ['', 'Warnings are heuristic diagnostics and can require no change.', '',
              '## Existing example routing (lexical)', '',
              '| Expected skill | Existing README request | Base picks | Candidate picks |', '| --- | --- | --- | --- |']
    changes = 0
    for name, examples in sorted(queries.items()):
        prior, current_picks = before.get(name, {}), after.get(name, {})
        if current_picks == {name: len(examples)} and (base is None or current_picks == prior):
            continue
        changes += int(base is not None and prior != current_picks)
        prompt = examples[0] if len(examples) == 1 else f'{len(examples)} examples; see queries.json'
        lines.append('| ' + ' | '.join(map(cell, (name, prompt, picks(prior), picks(current_picks)))) + ' |')
    lines += ['', f'Changed routing summaries: {changes}. All choices remain in routing JSON.', '',
              'Without README examples: ' + (', '.join(map(cell, missing)) or 'none') + '.',
              'Example coverage is not comprehensive evaluation coverage.', '']
    if new_queries:
        lines += ['## New README examples', '',
                  'These were added by the candidate and are not regression evidence.', '']
        for name, examples in sorted(new_queries.items()):
            lines.append(f'- {cell(name)}: {len(examples)} new example(s). See new-routing.json for lexical choices.')
    return '\n'.join(lines) + '\n'


def command(arguments, out, label):
    environment = {key: value for key, value in os.environ.items()
                   if key in {'PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'TMP', 'TEMP', 'SYSTEMROOT', 'WINDIR'}}
    with (out / f'{label}.stdout').open('w', encoding='utf-8') as stdout:
        with (out / f'{label}.stderr').open('w', encoding='utf-8') as stderr:
            result = subprocess.run([sys.executable, '-I', '-m', 'dokimi', *arguments], cwd=out,
                                    env=environment, stdout=stdout, stderr=stderr)
    return result.returncode


def load(path, required):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or any(key not in value for key in required):
        raise ValueError(f'incomplete Dokimi report: {path}')
    return value


def check(root, out, label, statuses):
    statuses[label + '-check'] = command(
        ['catalog', 'check', '--root', str(root), '--kind', 'skills', '--strict', '--format', 'json'], out, label + '-check')
    scan = load(out / f'{label}-check.stdout', ('skills',))
    statuses[label + '-static'] = command(
        ['catalog', 'eval', str(root), '--tier', 'static', '--out-dir', str(out / label)], out, label + '-static')
    report = load(out / label / 'catalog.json', ('skills', 'problems', 'status'))
    queries = readme_queries(root / 'README.md', {row['name'] for row in scan['skills']})
    return report, queries


def routing(root, queries, out, label, statuses):
    if not queries:
        return {}
    path = out / f'{label}-queries.json'
    path.write_text(json.dumps(queries, indent=2) + '\n', encoding='utf-8')
    statuses[label] = command(['novelty', 'routing', '--all-vs-all', '--catalog', str(root),
                               '--queries-by-skill', str(path), '--out', str(out / f'{label}.json')], out, label)
    report = load(out / f'{label}.json', ('result',))
    return report['result']['lexical']['confusion']


def run(root, base, out):
    root = root.resolve()
    base = base.resolve() if base else None
    out = out.resolve()
    if any(out.is_relative_to(path) or path.is_relative_to(out) for path in (root, base) if path):
        raise ValueError('output must be outside content checkouts and their ancestors')
    out.mkdir(parents=True, exist_ok=False)
    statuses = {}
    try:
        candidate, candidate_queries = check(root, out, 'candidate', statuses)
        if base:
            previous, base_queries = check(base, out, 'base', statuses)
            names = {skill['name'] for skill in candidate['skills']}
            queries = {name: rows for name, rows in base_queries.items() if name in names}
            removed = sorted(base_queries.keys() - queries.keys())
            before = routing(base, queries, out, 'base-routing', statuses)
            new = {name: [q for q in rows if q not in base_queries.get(name, [])]
                   for name, rows in candidate_queries.items()}
            new = {name: rows for name, rows in new.items() if rows}
        else:
            previous, queries, before, new, removed = None, candidate_queries, {}, {}, []
        after = routing(root, queries, out, 'routing', statuses)
        routing(root, new, out, 'new-routing', statuses)
        coverage = {'existing_queries': queries, 'new_queries': new, 'removed_expected_skills': removed}
        (out / 'queries.json').write_text(json.dumps(coverage, indent=2) + '\n', encoding='utf-8')
        report = render(candidate, queries, before, after, base=previous, new_queries=new)
        if removed:
            report += '\nRemoved skills excluded from routing comparison: ' + ', '.join(map(cell, removed)) + '.\n'
        (out / 'report.md').write_text(report, encoding='utf-8')
    except (OSError, ValueError, KeyError, TypeError) as error:
        statuses['input-or-report-error'] = 2
        detail = '# Dokimi scan incomplete\n\n' + cell(error) + '\n'
        native = out / 'candidate' / 'report.md'
        if native.is_file():
            detail += '\n' + native.read_text(encoding='utf-8')
        (out / 'report.md').write_text(detail, encoding='utf-8')
    (out / 'status.json').write_text(json.dumps(statuses, indent=2) + '\n', encoding='utf-8')
    return max(statuses.values(), default=2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--base', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        raise SystemExit(run(args.root, args.base, args.out))
    except (OSError, ValueError) as error:
        parser.exit(2, f'{error}\n')
