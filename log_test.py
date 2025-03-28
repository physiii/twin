#!/usr/bin/env python3
"""Test script to verify logging works correctly with our changes."""

import os
import sys
import logging
import logger

# Initialize both logging systems
logger.setup_logging()

# Log from the main logger
logger.logger.info("Test message from logger module")

# Import the audio module to test its logging
from audio import log_available_audio_devices

# Test logging from the audio module
log_available_audio_devices()

print("Logging test complete, everything working!") 