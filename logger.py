# utils/logger.py
import logging
import os
from datetime import datetime
from typing import Optional
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Define color schemes
COLORS = {
    'DEBUG': Fore.CYAN,
    'INFO': Fore.GREEN,
    'WARNING': Fore.YELLOW,
    'ERROR': Fore.RED,
    'CRITICAL': Fore.RED + Style.BRIGHT
}

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        # Save original levelname
        orig_levelname = record.levelname
        # Add color to the levelname
        record.levelname = f"{COLORS.get(record.levelname, '')}{record.levelname}{Style.RESET_ALL}"
        # Format the message
        result = super().format(record)
        # Restore original levelname
        record.levelname = orig_levelname
        return result

logger = logging.getLogger('twin')

def setup_logging(log_level: Optional[str] = None) -> None:
    """Configure application logging with color-coded output"""
    
    # Set log level
    level = getattr(logging, (log_level or 'DEBUG').upper())
    logger.setLevel(level)
    
    # Clear existing handlers
    logger.handlers = []
    logger.propagate = False
    
    # Create logs directory
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    
    # Set up log file
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    trade_env = os.getenv('TRADE_ENV', 'dev').lower()
    log_file = os.path.join(log_dir, f"trade_{trade_env}_{timestamp}.log")
    
    # File handler configuration
    file_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler configuration
    console_formatter = ColoredFormatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Configure third-party logging
    for lib in ['urllib3', 'matplotlib', 'yfinance', 'peewee']:
        logging.getLogger(lib).setLevel(logging.WARNING)
    
    logger.info(f"Logging initialized → {log_file}")