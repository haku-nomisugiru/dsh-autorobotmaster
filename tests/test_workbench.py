"""Safety and workflow regression tests; no AI process or CAD session is started."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
spec = importlib.util.spec_from_file_location('workbench_server_under_test', ROOT / 'backend' / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def schema(properties, required=()):
    return {
        'type': 'object',
        'properties': {'params': {'type': 'object', 'properties': properties,
                                  'required': list(required), 'additionalProperties': False}},
        'required': ['params'], 'additionalProperties': False,
    }


# These strict catalog contracts intentionally belong to the upstream service,
# not to Workbench.validate_action. A changed catalog must change validation.
def catalog():
    fmt = {'response_format': {'type': 'string', 'enum': ['json', 'markdown']}}
    return [
        {'name': 'solidworks_create_basic_part', 'description': 'Create a box/cylinder',
         'inputSchema': schema(dict(fmt, shape={'type': 'string', 'enum': ['box', 'cylinder']},
                                    output_path={'type': 'string'}, width_mm={'type': 'number', 'exclusiveMinimum': 0},
                                    height_mm={'type': 'number', 'exclusiveMinimum': 0}, depth_mm={'type': 'number', 'exclusiveMinimum': 0}))},
        {'name': 'solidworks_new_document', 'description': 'Create a document',
         'inputSchema': schema(dict(fmt, doc_type={'type': 'string', 'enum': ['part', 'assembly', 'drawing']},
                                    template_path={'type': 'string'}))},
        {'name': 'solidworks_update_dimension', 'description': 'Change a driving dimension',
         'inputSchema': schema(dict(fmt, dimension_name={'type': 'string'}, value_mm={'type': 'number'}),
                               ['dimension_name', 'value_mm'])},
        {'name': 'solidworks_save_document', 'description': 'Save',
         'inputSchema': schema(dict(fmt, path={'type': 'string'}))},
        {'name': 'solidworks_bounding_box', 'description': 'Measure actual geometry', 'inputSchema': schema(fmt)},
    ]


def action(tool, **params):
    params.setdefault('response_format', 'json')
    return {'tool': tool, 'arguments_json': json.dumps({'params': params})}


def raw_step(tool, title='A modeling operation', checks=None, **params):
    return {'title': title, 'action': action(tool, **params), 'checks': [] if checks is None else checks}


def assertion(path='size_mm.0', op='approx', expected=80.0, tolerance=.1):
    return {'path': path, 'op': op, 'expected_json': json.dumps(expected), 'tolerance': tolerance}


class FakeProvider:
    def status(self):
        return {'status': 'ready', 'message': 'Test provider'}

    def query(self, *args, **kwargs):
        raise AssertionError('Workflow tests must not invoke an AI process')


class FakeBridge:
    """Minimal document simulation with observable mutation/checkpoint effects."""
    def __init__(self):
        self.calls = []
        self.active = None
        self.version = 0
        self.fail_mutations = 0
        self.mutation_start_versions = []
        self.on_call = None
        self.review_payload = {'status': 'review_required', 'manual_review_required': True, 'rebuild_ok': True}

    def list_tools(self):
        return catalog()

    def call(self, name, arguments):
        self.calls.append((name, copy.deepcopy(arguments)))
        params = arguments.get('params', {})
        if self.on_call:
            self.on_call(name, len(self.calls))
        if name == 'solidworks_create_basic_part':
            path = Path(params['output_path'])
            self.version = 0
            self.active = {'title': path.name, 'path': str(path), 'type': 1}
            self._write(path)
            return self._success()
        if name == 'solidworks_new_document':
            self.active = {'title': 'TestPart', 'path': '', 'type': 1}
            self.version = 0
            return self._success()
        if name == 'solidworks_connect':
            return {'status': 'success', 'active_document': copy.deepcopy(self.active)}
        if name == 'solidworks_save_document':
            path = Path(params.get('path') or self.active['path'])
            self._write(path)
            self.active.update(title=path.name, path=str(path))
            return self._success(saved=True)
        if name == 'solidworks_update_dimension':
            self.mutation_start_versions.append(self.version)
            self.version += 1
            if self.fail_mutations:
                self.fail_mutations -= 1
                return {'status': 'failed', 'success': False, 'message': 'Injected failure after CAD was modified'}
            return self._success()
        if name == 'solidworks_open_document':
            path = Path(params['path'])
            self.version = json.loads(path.read_text())['version']
            self.active = {'title': path.name, 'path': str(path), 'type': 1}
            return self._success()
        if name == 'solidworks_bounding_box':
            return {'status': 'success', 'size_mm': [80.0 + self.version, 60.0, 8.0]}
        if name == 'solidworks_review_active':
            return copy.deepcopy(self.review_payload)
        if name == 'solidworks_health_check':
            return {'status': 'success', 'checks': {'missing_com_dependencies': []}}
        raise AssertionError('Unexpected CAD tool: ' + name)

    def _write(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'version': self.version}), encoding='utf-8')

    def _success(self, **extra):
        result = {'status': 'success', 'success': True, 'rebuild_ok': True, 'document': copy.deepcopy(self.active)}
        result.update(extra)
        return result

    def close(self):
        pass


class ResultEvidenceTests(unittest.TestCase):
    def test_json_text_result_unwraps(self):
        self.assertEqual(server.unpack_result('{"status":"success","saved":true}')['saved'], True)

    def test_mcp_text_result_and_result_wrapper_unwrap(self):
        payload = {'content': [{'type': 'text', 'text': json.dumps({'result': json.dumps({'status': 'failed'})})}]}
        self.assertEqual(server.unpack_result(payload)['status'], 'failed')

    def test_structured_content_is_used_when_text_is_only_acknowledgement(self):
        payload = {'content': [{'type': 'text', 'text': 'Action completed.'}],
                   'structuredContent': {'result': '{"status":"success","saved":true}'}}
        self.assertTrue(server.unpack_result(payload)['saved'])

    def test_protocol_error_cannot_be_overridden_by_success_content(self):
        payload = {'isError': True, 'content': [{'type': 'text', 'text': '{"status":"success"}'}]}
        self.assertEqual(server.verdict(server.unpack_result(payload))[0], 'failed')

    def test_unknown_text_cannot_prove_success(self):
        self.assertNotEqual(server.verdict(server.unpack_result('Something happened'))[0], 'passed')

    def test_nested_required_failed_check_overrides_top_level_success(self):
        payload = {'status': 'success', 'verification': {'checks': [{'required': True, 'passed': False, 'name': 'Hole location'}]}}
        self.assertEqual(server.verdict(payload)[0], 'failed')

    def test_optional_failed_check_is_not_a_required_failure(self):
        payload = {'status': 'success', 'checks': [{'required': False, 'passed': False, 'name': 'Optional thumbnail'}]}
        self.assertNotEqual(server.verdict(payload)[0], 'failed')

    def test_explicit_failed_rebuild_overrides_status(self):
        self.assertEqual(server.verdict({'status': 'success', 'rebuild_ok': False})[0], 'failed')

    def test_unknown_or_string_rebuild_evidence_never_passes(self):
        for value in (None, 'False', 'false', 'True', 1):
            with self.subTest(value=value):
                self.assertNotEqual(server.verdict({'status': 'success', 'rebuild_ok': value})[0], 'passed')

    def test_manual_review_flag_is_preserved(self):
        self.assertEqual(server.verdict({'status': 'success', 'manual_review_required': True})[0], 'review_required')


class NumericAcceptanceTests(unittest.TestCase):
    def test_measurement_within_tolerance_passes(self):
        self.assertIn('size_mm.0', server.assert_result({'size_mm': [80.04]}, assertion()))

    def test_measurement_outside_tolerance_fails(self):
        with self.assertRaises(ValueError):
            server.assert_result({'size_mm': [81]}, assertion())

    def test_missing_or_out_of_bounds_measurement_is_not_accepted(self):
        for result in ({}, {'size_mm': []}):
            with self.subTest(result=result), self.assertRaises(ValueError):
                server.assert_result(result, assertion())

    def test_boolean_is_not_a_numeric_measurement(self):
        with self.assertRaises(ValueError):
            server.assert_result({'size_mm': [True]}, assertion(expected=1))
        with self.assertRaises(ValueError):
            server.assert_result({'size_mm': [1]}, assertion(expected=True))

    def test_nonfinite_measurements_are_rejected(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                server.assert_result({'size_mm': [value]}, assertion())

    def test_nonfinite_tolerance_is_not_an_unbounded_pass(self):
        for tolerance in (float('nan'), float('inf'), -float('inf')):
            with self.subTest(tolerance=tolerance), self.assertRaises(ValueError):
                server.assert_result({'size_mm': [80.0]}, assertion(tolerance=tolerance))

    def test_equals_does_not_coerce_boolean_to_one(self):
        with self.assertRaises(ValueError):
            server.assert_result({'count': True}, assertion(path='count', op='equals', expected=1))


class WorkbenchTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rm-workbench-test-')
        self.addCleanup(self.temp.cleanup)
        self.bridge = FakeBridge()
        self.app = server.Workbench(root=Path(self.temp.name), bridge=self.bridge, provider=FakeProvider())
        self.app.catalog = catalog()
        self.addCleanup(self.stop_worker)

    def stop_worker(self):
        self.app.cancel.set()
        with self.app.changed:
            self.app.paused = False
            self.app.changed.notify_all()
        if self.app.worker is not None:
            self.app.worker.join(timeout=3)

    def plan(self, modify=False, checks=None):
        path = Path(self.app.state['output_dir']) / 'part.SLDPRT'
        items = [raw_step('solidworks_create_basic_part', shape='box', width_mm=80.0,
                          height_mm=60.0, depth_mm=8.0, output_path=str(path), checks=checks)]
        if modify:
            items.append(raw_step('solidworks_update_dimension', dimension_name='D1@Sketch1', value_mm=81.0))
        return self.app.validate_plan(items, Path(self.app.state['output_dir']))

    def install_plan(self, modify=False, checks=None):
        self.app.state.update(steps=self.plan(modify, checks), phase='ready', busy=False)
        self.app.save()

    def wait_worker(self, timeout=3):
        if self.app.worker is not None:
            self.app.worker.join(timeout)
            self.assertFalse(self.app.worker.is_alive(), 'Worker did not finish: ' + str(self.app.snapshot()))


class PlanBoundaryTests(WorkbenchTestCase):
    def test_valid_catalog_conforming_plan_gets_final_review(self):
        steps = self.plan()
        self.assertTrue(steps[-1]['final_review'])
        self.assertFalse(steps[0]['action']['done'])

    def test_unknown_or_assembly_tool_is_rejected(self):
        for tool in ('solidworks_delete_everything', 'solidworks_add_component'):
            with self.subTest(tool=tool), self.assertRaises(ValueError):
                self.app.validate_plan([raw_step(tool)], Path(self.app.state['output_dir']))

    def test_required_mcp_argument_wrapper_is_enforced(self):
        item = raw_step('solidworks_create_basic_part')
        item['action']['arguments_json'] = json.dumps({'shape': 'box'})
        with self.assertRaises((ValueError, jsonschema.ValidationError)):
            self.app.validate_plan([item], Path(self.app.state['output_dir']))

    def test_unknown_mcp_parameter_is_not_silently_discarded(self):
        item = raw_step('solidworks_create_basic_part', shape='box', guessed_field='unsafe')
        with self.assertRaises((ValueError, jsonschema.ValidationError)):
            self.app.validate_plan([item], Path(self.app.state['output_dir']))

    def test_new_catalog_constraint_is_honored(self):
        create = next(t for t in self.app.catalog if t['name'] == 'solidworks_create_basic_part')
        create['inputSchema']['properties']['params']['required'] = ['depth_mm']
        with self.assertRaises((ValueError, jsonschema.ValidationError)):
            self.app.validate_plan([raw_step('solidworks_create_basic_part', shape='box')], Path(self.app.state['output_dir']))

    def test_output_cannot_escape_current_project(self):
        outside = Path(self.temp.name) / 'outside.SLDPRT'
        for target in (str(outside), str(Path(self.app.state['output_dir']) / '..' / '..' / 'outside.SLDPRT')):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.app.validate_plan([raw_step('solidworks_create_basic_part', output_path=target)], Path(self.app.state['output_dir']))

    def test_new_task_cannot_mutate_the_user_active_document(self):
        item = raw_step('solidworks_update_dimension', dimension_name='D1@Sketch1', value_mm=81)
        with self.assertRaises(ValueError):
            self.app.validate_plan([item], Path(self.app.state['output_dir']))

    def test_assembly_document_creation_is_rejected(self):
        with self.assertRaises(ValueError):
            self.app.validate_plan([raw_step('solidworks_new_document', doc_type='assembly')], Path(self.app.state['output_dir']))

    def test_check_cannot_execute_a_mutating_tool(self):
        check = dict(action('solidworks_save_document', path=str(Path(self.app.state['output_dir'])/'check.SLDPRT')),
                     label='Wrong checker', assertions=[assertion()])
        with self.assertRaises(ValueError):
            self.plan(checks=[check])

    def test_read_check_without_assertion_is_rejected(self):
        check = dict(action('solidworks_bounding_box'), label='Measure', assertions=[])
        with self.assertRaises(ValueError):
            self.plan(checks=[check])


class LifecycleTests(WorkbenchTestCase):
    def test_successful_cad_run_still_requires_human_acceptance(self):
        self.install_plan()
        self.app.start_run()
        self.wait_worker()
        self.assertEqual(self.app.state['phase'], 'review_required')
        self.assertNotEqual(self.app.state['phase'], 'completed')
        self.assertTrue(any(name == 'solidworks_review_active' for name, _ in self.bridge.calls))
        self.app.control('accept')
        self.assertEqual(self.app.state['phase'], 'completed')
        self.assertTrue(all(s['status'] == 'passed' for s in self.app.state['steps']))

    def test_failed_review_cannot_be_accepted(self):
        self.bridge.review_payload = {'status': 'success', 'rebuild_ok': False}
        self.install_plan()
        self.app.start_run()
        self.wait_worker()
        self.assertEqual(self.app.state['phase'], 'failed')
        with self.assertRaises(ValueError):
            self.app.control('accept')
        self.assertNotEqual(self.app.state['phase'], 'completed')

    def test_acceptance_fails_when_active_document_has_changed(self):
        self.install_plan()
        self.app.start_run()
        self.wait_worker()
        self.bridge.active = {'title': 'UserOriginal.SLDPRT', 'path': str(Path(self.temp.name)/'UserOriginal.SLDPRT'), 'type': 1}
        with self.assertRaises(ValueError):
            self.app.control('accept')
        self.assertNotEqual(self.app.state['phase'], 'completed')

    def test_numeric_design_check_failure_does_not_become_completed(self):
        check = dict(action('solidworks_bounding_box'), label='Width', assertions=[assertion(expected=999.0)])
        self.install_plan(checks=[check])
        self.app.start_run()
        self.wait_worker()
        self.assertEqual(self.app.state['phase'], 'failed')
        with self.assertRaises(ValueError):
            self.app.control('accept')

    def test_retry_restores_before_failed_mutation_not_partial_result(self):
        self.bridge.fail_mutations = 1
        self.install_plan(modify=True)
        self.app.start_run()
        self.wait_worker()
        self.assertEqual(self.app.state['phase'], 'failed')
        self.assertEqual(self.bridge.version, 1, 'First failed tool should have left a partial modification')
        self.app.control('retry')
        self.wait_worker()
        self.assertEqual(self.app.state['phase'], 'review_required')
        self.assertEqual(self.bridge.mutation_start_versions, [0, 0], 'Retry must begin from the saved checkpoint')
        self.assertEqual(sum(n == 'solidworks_create_basic_part' for n, _ in self.bridge.calls), 1,
                         'An already successful creation must not be repeated')
        self.assertTrue(any(n == 'solidworks_open_document' for n, _ in self.bridge.calls))

    def test_checkpoint_is_persisted_before_mutation_and_survives_process_interruption(self):
        class SimulatedProcessExit(BaseException):
            pass

        self.install_plan(modify=True)
        observed = {}
        def crash_during_mutation(name, count):
            if name != 'solidworks_update_dimension':
                return
            persisted = json.loads(self.app.state_path.read_text(encoding='utf-8'))
            modifying_step = next(s for s in persisted['steps']
                                  if s.get('action', {}).get('tool') == 'solidworks_update_dimension')
            observed.update(checkpoint=modifying_step.get('checkpoint'),
                            status=modifying_step['status'], busy=persisted['busy'])
            # The remote CAD operation changed and saved its active model, but
            # the orchestrator dies before it can record a result or catch an error.
            self.bridge.version = 7
            self.bridge._write(Path(self.bridge.active['path']))
            raise SimulatedProcessExit()

        self.bridge.on_call = crash_during_mutation
        self.app.state.update(phase='running', busy=True)
        self.app.save()
        with self.assertRaises(SimulatedProcessExit):
            self.app.run()
        self.assertEqual(observed.get('status'), 'running')
        self.assertTrue(observed.get('busy'))
        self.assertIsNotNone(observed.get('checkpoint'),
                             'Checkpoint ownership must reach state.json before the modifying MCP call begins')
        checkpoint = Path(observed['checkpoint'])
        self.assertTrue(checkpoint.is_file(), 'A persisted checkpoint must name a real model snapshot')
        self.assertEqual(json.loads(checkpoint.read_text())['version'], 0,
                         'The checkpoint must contain the model before the failed modification')
        self.assertEqual(self.bridge.version, 7)

        self.bridge.on_call = None
        restarted = server.Workbench(root=Path(self.temp.name), bridge=self.bridge, provider=FakeProvider())
        restarted.catalog = catalog()
        self.assertEqual(restarted.state['phase'], 'failed')
        self.assertEqual(restarted.state['steps'][1]['checkpoint'], str(checkpoint))
        restarted.control('retry')
        restarted.worker.join(timeout=3)
        self.assertFalse(restarted.worker.is_alive())
        self.assertEqual(restarted.state['phase'], 'review_required')
        self.assertEqual(self.bridge.mutation_start_versions, [0],
                         'Recovery must restore the persisted checkpoint rather than retrying from partial CAD state')
        self.assertEqual(self.bridge.version, 1)

    def test_retry_from_manual_review_rechecks_without_repeating_modeling(self):
        self.install_plan(modify=True)
        self.app.start_run()
        self.wait_worker()
        self.assertEqual(self.app.state['phase'], 'review_required')
        modeling_before = [(name, args) for name, args in self.bridge.calls
                           if name in {'solidworks_create_basic_part', 'solidworks_update_dimension'}]
        review_count = sum(name == 'solidworks_review_active' for name, _ in self.bridge.calls)
        attempts_before = [s['attempt'] for s in self.app.state['steps'] if not s.get('final_review')]
        self.app.control('retry')
        self.wait_worker()
        self.assertEqual(self.app.state['phase'], 'review_required')
        modeling_after = [(name, args) for name, args in self.bridge.calls
                          if name in {'solidworks_create_basic_part', 'solidworks_update_dimension'}]
        self.assertEqual(modeling_after, modeling_before, 'Rechecking must not recreate or modify geometry')
        self.assertEqual(sum(name == 'solidworks_review_active' for name, _ in self.bridge.calls), review_count + 1)
        self.assertEqual([s['attempt'] for s in self.app.state['steps'] if not s.get('final_review')], attempts_before)
        self.assertNotEqual(self.app.state['phase'], 'completed', 'A rerun review still needs human acceptance')

    def test_cancel_after_current_call_returns_prevents_next_mcp_call(self):
        self.install_plan(modify=True)
        stopped_at = []
        def hook(name, count):
            if name == 'solidworks_connect' and not stopped_at:
                stopped_at.append(count)
                self.app.control('cancel')
        self.bridge.on_call = hook
        self.app.start_run()
        self.wait_worker()
        self.assertEqual(self.app.state['phase'], 'cancelled')
        self.assertEqual(len(self.bridge.calls), stopped_at[0],
                         'Cancellation must take effect before a subsequent save/mutation call')
        self.assertFalse(any(n == 'solidworks_update_dimension' for n, _ in self.bridge.calls))

    def test_pause_after_current_call_blocks_next_mcp_call_until_resume(self):
        self.install_plan(modify=True)
        stopped = threading.Event()
        stopped_at = []
        def hook(name, count):
            if name == 'solidworks_connect' and not stopped_at:
                stopped_at.append(count)
                self.app.control('pause')
                stopped.set()
        self.bridge.on_call = hook
        self.app.start_run()
        self.assertTrue(stopped.wait(timeout=2))
        try:
            time.sleep(.08)
            self.assertEqual(self.app.state['phase'], 'paused')
            self.assertEqual(len(self.bridge.calls), stopped_at[0], 'Paused run must not invoke the next MCP tool')
        finally:
            if self.app.state['phase'] == 'paused':
                self.app.control('resume')
        self.wait_worker()
        self.assertEqual(self.app.state['phase'], 'review_required')

    def test_interrupted_persisted_run_cannot_restart_as_completed(self):
        self.install_plan()
        self.app.state.update(phase='running', busy=True)
        self.app.state['steps'][0]['status'] = 'running'
        self.app.save()
        restarted = server.Workbench(root=Path(self.temp.name), bridge=FakeBridge(), provider=FakeProvider())
        self.assertFalse(restarted.state['busy'])
        self.assertEqual(restarted.state['phase'], 'failed')
        self.assertNotEqual(restarted.state['steps'][0]['status'], 'passed')
        with self.assertRaises(ValueError):
            restarted.control('accept')

    def test_snapshot_does_not_expose_executable_actions(self):
        self.install_plan()
        state = self.app.snapshot()
        self.assertNotIn('action', state['steps'][0])
        self.assertNotIn('owned_document', state)
        self.assertIn('action', self.app.state['steps'][0], 'Taking a snapshot must not alter runnable state')


if __name__ == '__main__':
    unittest.main(verbosity=2)
