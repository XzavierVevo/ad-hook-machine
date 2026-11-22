import logging
import os
from pathlib import Path
from datetime import datetime
from . import config

def setup_logger(name: str = "hook_generator") -> logging.Logger:
    """
    Setup and configure the logger to save to a file and output to console.
    """
    # Create logs directory if it doesn't exist
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create a unique log file for this run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = config.LOGS_DIR / f"run_{timestamp}.log"
    
    # Configure logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # Prevent duplicate handlers if setup is called multiple times
    if logger.handlers:
        return logger
        
    # File handler (stores everything including DEBUG)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    
    # Console handler (stores INFO and above for user visibility)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"Logging initialized. Log file: {log_file}")
    
    return logger

def log_data(data: any, message: str = "Data payload:"):
    """
    Helper to log large data objects to the log file at DEBUG level.
    """
    import json
    try:
        data_str = json.dumps(data, indent=2, ensure_ascii=False)
        bot_logger.debug(f"{message}\n{data_str}")
    except Exception as e:
        bot_logger.debug(f"{message} (JSON serialization failed: {e})\n{str(data)[:1000]}...")

# Create a default logger instance
bot_logger = setup_logger()

