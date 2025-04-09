#!/usr/bin/env python3
"""
Main entry point for the Twin application.
This script sets up the proper Python path and runs the application.
"""

import os
import sys
import asyncio

# Add the parent directory to the Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Import the main function from the twin package
from twin.main import main

if __name__ == "__main__":
    # Run the main function
    asyncio.run(main()) 