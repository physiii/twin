# webserver.py - Web server for handling incoming commands

from aiohttp import web
import logging
import socket
from ..ai.generator import process_user_text

logger = logging.getLogger('twin')

async def handle_command(request):
    data = await request.json()
    text = data.get('text')
    if text:
        context = request.app['context']
        # From the webserver, assume always awake (force_awake=True) so we skip wake detection
        # and directly go to inference.
        result = await process_user_text(text, context, is_awake=True, force_awake=True)
        if result["inference_response"]:
            return web.json_response(result["inference_response"])
        else:
            return web.Response(text='No response from inference', status=500)
    else:
        return web.Response(text='No text provided', status=400)

def is_port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('0.0.0.0', port)) != 0

async def start_webserver(context):
    app = web.Application()
    app['context'] = context
    app.router.add_post('/command', handle_command)
    runner = web.AppRunner(app)
    await runner.setup()

    port = 8454
    while not is_port_available(port):
        port += 1

    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f'HTTP server started on port {port} and accessible publicly')
    return runner
