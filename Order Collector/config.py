"""
Application configuration and constants
"""

import os

# Debug Mode - Set to True for verbose logging and headless testing
DEBUG_MODE = os.getenv("ORDER_COLLECTOR_DEBUG", "False").lower() == "true"
HEADLESS_MODE = os.getenv("ORDER_COLLECTOR_HEADLESS", "False").lower() == "true"

# API Configuration
API_BASE_URL = "https://tista.app"
API_LOGIN_URL = f"{API_BASE_URL}/users/sign_in"
API_ORDERS_URL = f"{API_BASE_URL}/orders.json"
API_LOCATIONS_URL = f"{API_BASE_URL}/order_assignments/locations.json"

# Request settings
REQUEST_TIMEOUT = 30
DEFAULT_PER_PAGE = 250
MAX_RETRIES = 3

# Date format for API (DD/MM/YY)
API_DATE_FORMAT = "%d/%m/%y"

# Application settings
APP_NAME = "Order Collector"
APP_VERSION = "1.0.0"

# Credential storage (Windows Credential Manager via keyring)
SERVICE_NAME = "OrderCollector"

# Debug log file
DEBUG_LOG_FILE = "debug.log"
