#!/usr/bin/env python3
"""
Entry point for the Twin voice-controlled home assistant.
This script imports and runs the main application from the src package.
"""

import sys
import os
import asyncio

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from twin.main import main

if __name__ == "__main__":
    asyncio.run(main())
