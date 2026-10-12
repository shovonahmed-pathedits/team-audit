"""
Data fetching service - Handles order data retrieval with parallel fetching
"""

from typing import List, Dict, Optional, Tuple, Callable
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from api.client import TistaAPI
from utils.logger import app_logger


class DataFetcher:
    """Service for fetching and managing order data"""

    MAX_DATE_WORKERS = 5
    MAX_PAGE_WORKERS = 3
    MAX_RETRIES = 1

    def __init__(self, api_client: TistaAPI):
        self.api = api_client
        self.progress_callback: Optional[Callable] = None
        self._cancel_requested = False

    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates"""
        self.progress_callback = callback

    def _update_progress(
        self,
        message: str,
        value: int = -1,
        phase: str = None,
        completed: int = None,
        total: int = None,
        failed: int = None,
    ):
        """Send progress update if callback is set"""
        if self.progress_callback:
            full_message = message
            if phase:
                full_message = f"[{phase}] {message}"
            if completed is not None and total is not None:
                full_message += f" ({completed}/{total})"
            if failed is not None and failed > 0:
                full_message += f" | Failed: {failed}"
            self.progress_callback(full_message, value)

    def _get_date_list(self, start_date: str, end_date: str) -> List[str]:
        """
        Get list of dates between start and end (inclusive)

        Args:
            start_date: Start date (DD/MM/YY)
            end_date: End date (DD/MM/YY)

        Returns:
            List of date strings in DD/MM/YY format
        """
        try:
            start = datetime.strptime(start_date, "%d/%m/%y")
            end = datetime.strptime(end_date, "%d/%m/%y")

            dates = []
            current = start
            while current <= end:
                dates.append(current.strftime("%d/%m/%y"))
                current += timedelta(days=1)

            return dates
        except ValueError as e:
            app_logger.error(f"Invalid date format: {e}")
            return [start_date]

    def _worker_fetch_date(
        self, date: str, location_id: Optional[int], per_page: int
    ) -> Tuple[str, bool, Dict]:
        """
        Thread-safe worker function for parallel date fetch.
        Creates NEW TistaAPI instance per thread to avoid conflicts.
        """
        thread_api = TistaAPI()

        thread_api.session.cookies.update(self.api.session.cookies)
        thread_api.is_authenticated = self.api.is_authenticated
        thread_api.session_email = self.api.session_email
        thread_api.csrf_token = self.api.csrf_token
        thread_api.csrf_param = self.api.csrf_param

        try:
            success, data = thread_api._fetch_orders_internal(
                location_id=location_id, start_date=date, page=1, per_page=per_page
            )
            return (date, success, data)
        except Exception as e:
            app_logger.error(f"Error fetching {date}: {e}")
            return (date, False, {"error": str(e)})

    def _worker_fetch_page(
        self, date: str, page: int, location_id: Optional[int], per_page: int
    ) -> Tuple[str, int, bool, List[Dict]]:
        """Thread-safe worker for parallel page fetch"""
        thread_api = TistaAPI()

        thread_api.session.cookies.update(self.api.session.cookies)
        thread_api.is_authenticated = self.api.is_authenticated
        thread_api.session_email = self.api.session_email

        try:
            success, data = thread_api._fetch_orders_internal(
                location_id=location_id, start_date=date, page=page, per_page=per_page
            )
            if success:
                orders = data.get("orders", [])
                return (date, page, True, orders)
            return (date, page, False, [])
        except Exception as e:
            app_logger.error(f"Error fetching {date} page {page}: {e}")
            return (date, page, False, [])

    def _fetch_with_retry(self, func, *args, max_retries: int = 1) -> Tuple:
        """Execute function with retry logic"""
        last_result = None
        for attempt in range(max_retries + 1):
            result = func(*args)
            if isinstance(result, tuple) and len(result) >= 2:
                success = result[1]
                if success:
                    return result
            last_result = result
        return last_result

    def fetch_orders_with_progress(
        self,
        location_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        per_page: int = 250,
    ) -> Tuple[bool, List[Dict], Dict, str]:
        """
        Fetch all orders with PARALLEL fetching for maximum speed.

        Strategy:
        1. Fetch first page of ALL dates in parallel
        2. Retry failed dates once
        3. Fetch remaining pages in parallel
        4. Retry failed pages once
        5. Report any remaining failures

        Args:
            location_id: Filter by location ID
            start_date: Start date (DD/MM/YY)
            end_date: End date (DD/MM/YY)
            per_page: Results per page (default 250)

        Returns:
            Tuple of (success, orders, meta, error_message)
        """
        try:
            if not start_date:
                return False, [], {}, "Start date is required"

            if not self.api.is_authenticated:
                return False, [], {}, "Not authenticated"

            date_list = self._get_date_list(start_date, end_date)
            if end_date and end_date != start_date:
                app_logger.info(
                    f"Date range: {len(date_list)} days to fetch (PARALLEL mode)"
                )
            else:
                date_list = [start_date]

            all_orders = []
            total_records = 0
            failed_dates = []
            failed_pages = []
            date_results = {}

            total_tasks = len(date_list)
            self._update_progress(
                "Fetching dates in parallel...",
                5,
                phase="PARALLEL",
                completed=0,
                total=total_tasks,
            )

            # ==================== PHASE 1: Parallel Date Fetch ====================
            with ThreadPoolExecutor(max_workers=self.MAX_DATE_WORKERS) as executor:
                futures = {
                    executor.submit(
                        self._worker_fetch_date, date, location_id, per_page
                    ): date
                    for date in date_list
                }

                completed = 0
                for future in as_completed(futures):
                    date, success, data = future.result()
                    completed += 1
                    progress = int((completed / total_tasks) * 40)

                    if success:
                        orders = data.get("orders", [])
                        meta = data.get("meta", {})
                        pagination = meta.get("pagination", {})
                        total_pages = pagination.get("total_pages", 1)
                        day_total = pagination.get("total_records", 0)

                        date_results[date] = {
                            "orders": orders,
                            "total_pages": total_pages,
                            "day_total": day_total,
                        }
                        all_orders.extend(orders)
                        total_records += day_total

                        self._update_progress(
                            f"Date {date}: {day_total} orders, {total_pages} pages",
                            progress,
                            phase="PARALLEL",
                            completed=completed,
                            total=total_tasks,
                        )
                    else:
                        failed_dates.append(date)
                        app_logger.warning(
                            f"Failed to fetch {date}: {data.get('error')}"
                        )
                        self._update_progress(
                            f"Failed: {date}",
                            progress,
                            phase="PARALLEL",
                            completed=completed,
                            total=total_tasks,
                            failed=len(failed_dates),
                        )

            # ==================== PHASE 1b: Retry Failed Dates ====================
            if failed_dates:
                self._update_progress(
                    f"Retrying {len(failed_dates)} failed dates...", 40, phase="RETRY"
                )
                for date in failed_dates[:]:
                    date, success, data = self._worker_fetch_date(
                        date, location_id, per_page
                    )
                    if success:
                        failed_dates.remove(date)
                        orders = data.get("orders", [])
                        meta = data.get("meta", {})
                        pagination = meta.get("pagination", {})
                        total_pages = pagination.get("total_pages", 1)
                        day_total = pagination.get("total_records", 0)

                        date_results[date] = {
                            "orders": orders,
                            "total_pages": total_pages,
                            "day_total": day_total,
                        }
                        all_orders.extend(orders)
                        total_records += day_total
                    else:
                        app_logger.error(f"Retry failed for {date}")

            # ==================== PHASE 2: Parallel Page Fetch ====================
            page_tasks = 0
            for date_info in date_results.values():
                if date_info["total_pages"] > 1:
                    page_tasks += date_info["total_pages"] - 1

            if page_tasks > 0:
                self._update_progress(
                    f"Fetching remaining pages in parallel ({page_tasks} pages)...",
                    50,
                    phase="PAGES",
                    completed=0,
                    total=page_tasks,
                )

                with ThreadPoolExecutor(max_workers=self.MAX_PAGE_WORKERS) as executor:
                    page_futures = []
                    for date, date_info in date_results.items():
                        total_pages = date_info["total_pages"]
                        for page in range(2, total_pages + 1):
                            future = executor.submit(
                                self._worker_fetch_page,
                                date,
                                page,
                                location_id,
                                per_page,
                            )
                            page_futures.append(future)

                    completed = 0
                    page_completed = 0
                    for future in as_completed(page_futures):
                        date, page, success, orders = future.result()
                        completed += 1
                        progress = 50 + int((completed / page_tasks) * 40)

                        if success:
                            all_orders.extend(orders)
                            page_completed += 1
                            self._update_progress(
                                f"Page {page} for {date}",
                                progress,
                                phase="PAGES",
                                completed=completed,
                                total=page_tasks,
                            )
                        else:
                            failed_pages.append(f"{date}-page{page}")
                            self._update_progress(
                                f"Failed: {date} page {page}",
                                progress,
                                phase="PAGES",
                                completed=completed,
                                total=page_tasks,
                                failed=len(failed_pages),
                            )

                # ==================== PHASE 2b: Retry Failed Pages ====================
                if failed_pages:
                    self._update_progress(
                        f"Retrying {len(failed_pages)} failed pages...",
                        90,
                        phase="RETRY",
                    )
                    for page_key in failed_pages[:]:
                        date, page_str = page_key.split("-page")
                        page = int(page_str)
                        date, page, success, orders = self._worker_fetch_page(
                            date, page, location_id, per_page
                        )
                        if success:
                            failed_pages.remove(page_key)
                            all_orders.extend(orders)

            # ==================== COMPLETE ====================
            self._update_progress("Processing data...", 95)

            combined_meta = {
                "pagination": {
                    "total_records": total_records,
                    "total_days": len(date_list),
                },
                "api_total_records": total_records,
                "failed_dates": failed_dates,
                "failed_pages": failed_pages,
                "parallel_mode": True,
                "max_workers": self.MAX_DATE_WORKERS,
            }

            if failed_dates or failed_pages:
                error_msg = f"Partial fetch complete. Failed: {len(failed_dates)} dates, {len(failed_pages)} pages"
                app_logger.warning(error_msg)
                self._update_progress(
                    error_msg, 100, failed=len(failed_dates) + len(failed_pages)
                )
            else:
                self._update_progress(f"Complete! {total_records} total orders", 100)

            return True, all_orders, combined_meta, ""

        except Exception as e:
            error_msg = str(e)
            app_logger.error(f"Error during fetch: {error_msg}")
            self._update_progress(f"Error: {error_msg}", -1)
            return False, [], {}, error_msg

    def fetch_locations(self) -> Tuple[bool, List[Dict], str]:
        """
        Fetch available locations

        Returns:
            Tuple of (success, locations, error_message)
        """
        try:
            self._update_progress("Fetching locations...", 0)
            success, locations = self.api.fetch_locations()

            if success:
                self._update_progress(f"Found {len(locations)} locations", 100)
                return True, locations, ""
            else:
                return False, [], "Failed to fetch locations"

        except Exception as e:
            error_msg = str(e)
            app_logger.error(f"Error fetching locations: {error_msg}")
            return False, [], error_msg
