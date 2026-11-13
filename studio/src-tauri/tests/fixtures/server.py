import json
import os
import sys

call_count = 0
for line in sys.stdin:
    request = json.loads(line)
    if 'id' not in request:
        continue
    method = request['method']
    if method == 'initialize':
        result = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'fixture', 'version': '1'}}
    elif method == 'tools/list':
        if request['params'].get('cursor'):
            result = {'tools': [{'name': name, 'description': 'fixture', 'inputSchema': {'type': 'object'}} for name in ['fixture_failure', 'solidworks_save_document']]}
        else:
            result = {'tools': [{'name': 'fixture_echo', 'description': 'echo', 'inputSchema': {'type': 'object'}}], 'nextCursor': 'page2'}
    elif method == 'tools/call':
        call_count += 1
        print(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/progress', 'params': {'progress': 1}}), flush=True)
        args = request['params']
        result = {'content': [{'type': 'text', 'text': json.dumps(args.get('arguments'), ensure_ascii=False)}], 'callCount': call_count, 'outputRoot': os.environ.get('SW_MCP_OUTPUT_ROOT'), 'isError': args['name'] == 'fixture_failure'}
    else:
        print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'error': {'code': -32601, 'message': 'unknown'}}), flush=True)
        continue
    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}), flush=True)
