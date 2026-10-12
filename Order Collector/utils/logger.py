"""
Logging utility for debugging and error tracking
"""
import logging
import os
from config import DEBUG_MODE, DEBUG_LOG_FILE


def setup_logger(name: str, level: int = None) -> logging.Logger:
    """
    Setup and return a logger instance
    
    Args:
        name: Logger name
        level: Logging level (uses DEBUG if DEBUG_MODE else INFO)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Set level based on debug mode
    if level is None:
        level = logging.DEBUG if DEBUG_MODE else logging.INFO
    
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    simple_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(simple_formatter if not DEBUG_MODE else detailed_formatter)
    logger.addHandler(console_handler)
    
    # File handler - always write to debug.log in debug mode
    if DEBUG_MODE:
        os.makedirs('logs', exist_ok=True)
        log_file = os.path.join('logs', DEBUG_LOG_FILE)
        file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='w')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)
        
        logger.debug("=" * 80)
        logger.debug("DEBUG MODE ENABLED - Verbose logging active")
        logger.debug("=" * 80)
    
    return logger


# Create default application logger
app_logger = setup_logger('OrderCollector')


def log_api_request(method: str, url: str, status_code: int = None, response_data: str = None):
    """Log API request details (only in debug mode)"""
    if DEBUG_MODE:
        app_logger.debug(f"API REQUEST: {method} {url}")
        if status_code:
            app_logger.debug(f"API RESPONSE: Status {status_code}")
        if response_data:
            # Truncate long responses
            if len(response_data) > 1000:
                response_data = response_data[:1000] + "... [truncated]"
            app_logger.debug(f"API DATA: {response_data}")


def log_api_error(method: str, url: str, error: str):
    """Log API error details"""
    if DEBUG_MODE:
        app_logger.error(f"API ERROR: {method} {url}")
        app_logger.error(f"ERROR DETAILS: {error}")
