"""Test infrastructure: query real Codex skill discovery without starting a model turn."""

import asyncio
import json


async def response(process, request_id):
    """Read a bounded app-server response, failing on errors or premature exit."""
    async def read():
        """Ignore unrelated notifications until the requested response arrives."""
        while True:
            line = await process.stdout.readline()
            if not line:
                raise ValueError('App server exited before skill discovery')
            message = json.loads(line)
            if message.get('id') == request_id:
                if 'error' in message:
                    raise ValueError(str(message['error']))
                return message['result']
    return await asyncio.wait_for(read(), timeout=30)


async def send(process, message):
    """Write one JSON-RPC message over the documented stdio transport."""
    process.stdin.write((json.dumps(message) + '\n').encode())
    await process.stdin.drain()


async def discover(environment, cwd):
    """Initialize an isolated server and read skills/list, then stop it without a turn."""
    process = await asyncio.create_subprocess_exec(
        'codex', 'app-server', '--stdio', env=environment, cwd=str(cwd),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL)
    try:
        await send(process, {'id': 1, 'method': 'initialize', 'params': {
            'clientInfo': {'name': 'bymax-install-test', 'version': '1.0.0'}}})
        await response(process, 1)
        await send(process, {'method': 'initialized', 'params': {}})
        await send(process, {'id': 2, 'method': 'skills/list', 'params': {
            'cwds': [str(cwd)], 'forceReload': True}})
        return await response(process, 2)
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
