# webserver.py

import asyncio
from aiohttp import web
import logging
from command_processor import process_command_text  # Import the command processor

logger = logging.getLogger(__name__)

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

async def start_webserver(context):
    app = web.Application()
    app['context'] = context
    app.router.add_post('/command', handle_command)
    runner = web.AppRunner(app)
    await runner.setup()
    # Bind to '0.0.0.0' to allow access on any interface
    site = web.TCPSite(runner, '0.0.0.0', 8454)
    await site.start()
    logger.info('HTTP server started on port 8080 and accessible publicly')
    return runner
