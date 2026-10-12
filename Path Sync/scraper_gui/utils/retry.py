"""Retry utilities for HTTP requests with exponential backoff."""

import time
import logging
from functools import wraps
from typing import Callable, Any, Optional

logger = logging.getLogger("tista_scraper")


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 2.0,
    max_delay: float = 10.0,
    multiplier: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """Decorator that retries a function with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 2)
        max_delay: Maximum delay cap in seconds (default: 10)
        multiplier: Multiplier for exponential backoff (default: 2)
        exceptions: Tuple of exceptions to catch and retry (default: all)

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(
                            f"Failed after {max_attempts} attempts: {func.__name__}"
                        )
                        raise

                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * multiplier, max_delay)

            raise last_exception

        return wrapper

    return decorator


def retry_on_predicate(
    max_attempts: int = 3,
    initial_delay: float = 2.0,
    max_delay: float = 10.0,
    multiplier: float = 2.0,
) -> Callable:
    """Decorator that retries a function based on return value predicate.

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 2)
        max_delay: Maximum delay cap in seconds (default: 10)
        multiplier: Multiplier for exponential backoff (default: 2)

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay

            for attempt in range(1, max_attempts + 1):
                result = func(*args, **kwargs)

                if result is not None:
                    return result

                if attempt == max_attempts:
                    logger.error(
                        f"Failed after {max_attempts} attempts: {func.__name__}"
                    )
                    return result

                logger.warning(
                    f"Attempt {attempt}/{max_attempts} returned None for {func.__name__}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                delay = min(delay * multiplier, max_delay)

            return result

        return wrapper

    return decorator
