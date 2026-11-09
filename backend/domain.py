"""Pure CAD contracts and evidence rules, independent of UI, HTTP and model vendor."""
from __future__ import annotations
import json
import math

READ_TOOLS = {'solidworks_bounding_box', 'solidworks_mass_properties', 'solidworks_inspect_hole_features',
              'solidworks_inspect_configurations', 'solidworks_list_edges', 'solidworks_inspect_native_bodies'}
WRITE_TOOLS = {'solidworks_create_basic_part', 'solidworks_new_document', 'solidworks_sketch_and_extrude',
               'solidworks_revolve', 'solidworks_create_hole_feature', 'solidworks_fillet', 'solidworks_chamfer',
               'solidworks_shell', 'solidworks_pattern', 'solidworks_mirror_feature', 'solidworks_update_dimension',
               'solidworks_set_appearance', 'solidworks_save_document', 'solidworks_export_active',
               'solidworks_set_custom_properties', 'solidworks_create_configuration', 'solidworks_activate_configuration'}
CREATE_TOOLS = {'solidworks_create_basic_part', 'solidworks_new_document'}
BAD_STATES = {'error', 'failed', 'fail', 'blocked', 'invalid', 'timeout'}
WARN_STATES = {'warn', 'warning', 'review_required', 'needs_review', 'partial'}
SUCCESS_KEYS = {'success', 'rebuild_ok', 'rebuild_succeeded', 'rebuild_success', 'feature_created', 'saved', 'save_ok', 'save_success', 'exported'}


def unpack_result(raw):
    if isinstance(raw, str):
        try: return unpack_result(json.loads(raw))
        except (ValueError, TypeError): return {'status': 'unknown', 'message': raw[:3000]}
    if not isinstance(raw, dict): return {'status': 'unknown', 'data': raw}
    if raw.get('isError') is True:
        return {'status': 'error', 'message': str(raw.get('content', 'MCP 调用失败'))[:3000]}
    if 'content' in raw and isinstance(raw['content'], list):
        texts = [c.get('text', '') for c in raw['content'] if c.get('type') == 'text']
        for text in texts:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict): return unpack_result(parsed)
            except (ValueError, TypeError): pass
        if isinstance(raw.get('structuredContent'), dict): return unpack_result(raw['structuredContent'])
        return {'status': 'unknown', 'message': '\n'.join(texts)[:3000]}
    if set(raw) == {'result'}: return unpack_result(raw['result'])
    return raw


def verdict(payload):
    """Conservative operation verdict; boolean evidence must really be boolean."""
    failures, warnings, positives = [], [], []
    def walk(node, prefix='', optional=False):
        if isinstance(node, dict):
            optional = optional or node.get('required') is False
            status = str(node.get('status', '')).lower()
            target = warnings if optional else failures
            if status in BAD_STATES: target.append(node.get('message') or node.get('reason') or status)
            if status in WARN_STATES: warnings.append(status)
            if status in {'ok', 'success', 'passed', 'pass', 'completed'}: positives.append(status)
            if node.get('isError') is True: target.append('MCP 返回错误')
            if node.get('manual_review_required') is True: warnings.append('需要人工核验')
            if node.get('required') is True:
                for key in ('passed', 'success', 'ok'):
                    if key in node and node[key] is False: target.append(prefix+key+'=false')
                    elif key in node and type(node[key]) is not bool: warnings.append('必要检查证据不确定')
            for key, value in node.items():
                if key in SUCCESS_KEYS:
                    if value is False: target.append(prefix + key + '=false')
                    elif value is True: positives.append(key)
                    elif not (key=='saved' and value is None and not node.get('output_path')):
                        warnings.append(prefix+key+' 缺少明确布尔证据')
                if key == 'errors' and value: target.append(str(value))
                if key in {'content', 'artifact_refs', 'previews', 'document'}: continue
                if isinstance(value, (dict, list)): walk(value, prefix+key+'.', optional)
        elif isinstance(node, list):
            for value in node: walk(value,prefix,optional)
    walk(payload)
    if failures: return 'failed', '；'.join(map(str, failures))[:1200]
    if warnings: return 'review_required', '检查已返回，仍需人工复核：'+'；'.join(map(str,warnings))[:800]
    if positives: return 'passed', '操作及返回状态已核验'
    return 'review_required', '返回结果缺少明确成功证据，需人工复核'


def assert_result(payload, assertion):
    current = payload
    try:
        for part in assertion['path'].split('.'):
            current = current[int(part)] if isinstance(current, list) else current[part]
    except (KeyError, IndexError, ValueError, TypeError):
        raise ValueError('验收依据缺失：' + assertion['path'])
    expected = json.loads(assertion['expected_json'])
    op = assertion['op']
    if op == 'equals': passed = type(current) is type(expected) and current == expected
    elif op == 'nonempty': passed = bool(current)
    elif op in {'approx', 'gte', 'lte'}:
        if isinstance(current, bool) or isinstance(expected, bool): raise ValueError('数值验收不能使用布尔值')
        actual, target = float(current), float(expected)
        if not math.isfinite(actual) or not math.isfinite(target): raise ValueError('验收数值无效')
        if op == 'approx':
            tolerance=assertion.get('tolerance',.1)
            if isinstance(tolerance,bool) or not math.isfinite(float(tolerance)) or float(tolerance)<0: raise ValueError('验收公差必须是有限非负数')
            passed = abs(actual-target) <= float(tolerance)
        elif op == 'gte': passed = actual >= target
        else: passed = actual <= target
    else: raise ValueError('不支持的验收比较方式')
    if not passed: raise ValueError('验收未通过：%s，实测 %s，要求 %s' % (assertion['path'], current, expected))
    return '%s = %s' % (assertion['path'], current)


def object_schema(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}

ACTION_SCHEMA = object_schema({'tool': {'type': 'string'}, 'arguments_json': {'type': 'string'}})
ASSERT_SCHEMA = object_schema({'path': {'type': 'string'}, 'op': {'type': 'string', 'enum': ['equals','approx','gte','lte','nonempty']},
                              'expected_json': {'type': 'string'}, 'tolerance': {'type': 'number'}})
CHECK_SCHEMA = object_schema({'label': {'type': 'string'}, 'tool': {'type': 'string'}, 'arguments_json': {'type': 'string'},
                             'assertions': {'type': 'array', 'items': ASSERT_SCHEMA}})
STEP_SCHEMA = object_schema({'title': {'type': 'string'}, 'action': ACTION_SCHEMA,
                            'checks': {'type': 'array', 'items': CHECK_SCHEMA}})
PLAN_SCHEMA = object_schema({'message': {'type': 'string'}, 'summary': {'type': 'string'},
                            'steps': {'type': 'array', 'items': STEP_SCHEMA}})

LESSON_SCHEMA = object_schema({
    'title': {'type':'string'}, 'when_to_use': {'type':'string'},
    'procedure': {'type':'array','items':{'type':'string'}},
    'verification': {'type':'array','items':{'type':'string'}},
    'pitfalls': {'type':'array','items':{'type':'string'}},
    'evidence_ids': {'type':'array','items':{'type':'string'}}})
SUMMARY_SCHEMA = object_schema({
    'summary': {'type':'string'}, 'decisions': {'type':'array','items':{'type':'string'}},
    'open_items': {'type':'array','items':{'type':'string'}},
    'lessons': {'type':'array','items':LESSON_SCHEMA}})
