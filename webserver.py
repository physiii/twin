# webserver.py

from aiohttp import web
import logging
import socket
from command import process_command_text 
import logging
logger = logging.getLogger('twin')

async def handle_command(request):
    data = await request.json()
    text = data.get('text')
    if text:
        context = request.app['context']
        inference_response = await process_command_text(text, context)
        if inference_response:
            return web.json_response(inference_response)
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

    # Bind to '0.0.0.0' to allow access on any interface
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f'HTTP server started on port {port} and accessible publicly')
    return runner
