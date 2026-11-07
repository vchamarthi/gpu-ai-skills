# SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The diagnostic adapter preserves author-written queries and exposes PR changes."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('dokimi_static', Path(__file__).parents[1] / 'scripts/dokimi_static.py')
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)


class ReadmeQueries(unittest.TestCase):
    def read(self, text, names):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'README.md'
            path.write_text(text)
            return scanner.readme_queries(path, set(names))

    def test_only_example_tables_supply_queries(self):
        text = '''| Skill | Useful for | Example prompt |
|---|---|---|
| `example` *(experimental)* | description is not a query | "Try this request." |

| Skill | Notes | Command |
|---|---|---|
| `example` | other table | do not use this |
'''
        self.assertEqual(self.read(text, ['example']), {'example': ['Try this request.']})

    def test_prompts_preserve_escaped_pipes_and_deduplicate(self):
        text = '| Skill | Useful for | Example prompt |\n|---|---|---|\n'
        text += '| `example` | usage | "Read a \\| b." |\n' * 2
        self.assertEqual(self.read(text, ['example']), {'example': ['Read a | b.']})

    def test_unknown_skill_and_empty_prompt_are_input_errors(self):
        for row in ('| `unknown` | usage | "request" |', '| `example` | usage | "" |'):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.read('| Skill | Useful for | Example prompt |\n|---|---|---|\n' + row, ['example'])

    def test_absent_examples_remain_unmeasured(self):
        self.assertEqual(self.read('# No examples\n', ['example']), {})


class DiagnosticReport(unittest.TestCase):
    def test_changed_routing_and_paths_are_visible_without_downloading_json(self):
        candidate = {'skills': [{'name': 'example'}, {'name': 'rival'}],
                     'problems': [{'level': 'warn', 'code': 'link-missing', 'path': 'skills/example/SKILL.md',
                                   'message': 'missing reference'}]}
        base = {'skills': [{'name': 'example'}, {'name': 'rival'}], 'problems': []}
        before = {'example': {'example': 1}}
        after = {'example': {'rival': 1}}
        report = scanner.render(candidate, {'example': ['Existing user request']}, before, after,
                                base=base, new_queries={})
        self.assertIn('skills/example/SKILL.md', report)
        self.assertIn('Existing user request', report)
        self.assertIn('example: 1', report)
        self.assertIn('rival: 1', report)
        self.assertIn('1 new', report)
        self.assertIn('rival', report.split('Without README examples:', 1)[1])

    def test_warning_text_and_example_prompts_cannot_inject_markdown(self):
        candidate = {'skills': [{'name': 'example'}], 'problems': [
            {'level': 'warn', 'code': 'warning', 'path': 'path|injected', 'message': '<script>bad</script>'}]}
        report = scanner.render(candidate, {'example': ['request|text']}, {}, {'example': {'rival': 1}},
                                base=None, new_queries={})
        self.assertNotIn('<script>', report)
        self.assertIn('path&#124;injected', report)
        self.assertIn('request&#124;text', report)

    def test_new_examples_are_not_presented_as_regression_evidence(self):
        candidate = {'skills': [{'name': 'new-skill'}], 'problems': []}
        report = scanner.render(candidate, {}, {}, {}, base=None,
                                new_queries={'new-skill': ['An added example']})
        self.assertIn('New README examples', report)
        self.assertIn('not regression evidence', report)


class WorkflowContract(unittest.TestCase):
    def test_no_provider_secrets_personal_workflow_or_write_permission_is_needed(self):
        text = (Path(__file__).parents[1] / '.github/workflows/dokimi.yml').read_text()
        self.assertIn('repository: intel/dokimi', text)
        for forbidden in ('secrets.', 'vars.', ': write', '/.github/workflows/', '--model', '--provider'):
            self.assertNotIn(forbidden, text)
        self.assertIn('path: base', text)
        self.assertIn('persist-credentials: false', text)


class AdapterExecution(unittest.TestCase):
    def test_candidate_rewording_does_not_replace_the_baseline_query(self):
        import json
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root, base, out = Path(tmp).resolve() / 'head', Path(tmp).resolve() / 'base', Path(tmp).resolve() / 'out'
            root.mkdir()
            base.mkdir()
            report = {'skills': [{'name': 'example'}, {'name': 'added'}], 'problems': []}
            def checked(path, output, label, statuses):
                statuses[label] = 0
                queries = {'example': ['original request']} if path == base else {
                    'example': ['reworded request'], 'added': ['new request']}
                return report, queries
            def routed(path, queries, output, label, statuses):
                statuses[label] = 0
                return {name: {name: len(rows)} for name, rows in queries.items()}
            with patch.object(scanner, 'check', checked), patch.object(scanner, 'routing', routed):
                self.assertEqual(scanner.run(root, base, out), 0)
            coverage = json.loads((out / 'queries.json').read_text())
            self.assertEqual(coverage['existing_queries'], {'example': ['original request']})
            self.assertEqual(coverage['new_queries'], {'example': ['reworded request'], 'added': ['new request']})
            self.assertIn('not regression evidence', (out / 'report.md').read_text())

    def test_nonzero_tool_exit_and_unusable_input_fail_and_preserve_reports(self):
        import json
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / 'head', Path(tmp) / 'out'
            root.mkdir()
            def checked(path, output, label, statuses):
                statuses[label] = 1
                return {'skills': [{'name': 'example'}], 'problems': []}, {}
            with patch.object(scanner, 'check', checked):
                self.assertEqual(scanner.run(root, None, out), 1)
            self.assertEqual(json.loads((out / 'status.json').read_text())['candidate'], 1)
            self.assertTrue((out / 'report.md').is_file())
            with patch.object(scanner, 'check', side_effect=ValueError('bad input')):
                self.assertEqual(scanner.run(root, None, Path(tmp) / 'bad-out'), 2)
            self.assertIn('bad input', (Path(tmp) / 'bad-out/report.md').read_text())

    def test_reused_output_and_output_inside_content_are_refused(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / 'head', Path(tmp) / 'out'
            root.mkdir()
            out.mkdir()
            (out / 'keep').write_text('existing evidence')
            with patch.object(scanner, 'check', side_effect=AssertionError('output guard bypassed')):
                with self.assertRaises(FileExistsError):
                    scanner.run(root, None, out)
            with self.assertRaises(ValueError):
                scanner.run(root, None, root / 'reports')
            self.assertEqual((out / 'keep').read_text(), 'existing evidence')
