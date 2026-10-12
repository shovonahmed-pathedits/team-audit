"""
API endpoint definitions for Tista application
"""
from config import API_BASE_URL


class Endpoints:
    """API endpoint URLs"""
    
    BASE_URL = API_BASE_URL
    
    # Authentication
    LOGIN = f"{API_BASE_URL}/users/sign_in"
    LOGOUT = f"{API_BASE_URL}/users/sign_out"
    
    # Orders
    ORDERS = f"{API_BASE_URL}/orders.json"
    ORDER_DETAIL = f"{API_BASE_URL}/orders/{{order_id}}.json"
    
    # Locations/Vendors
    LOCATIONS = f"{API_BASE_URL}/order_assignments/locations.json"
    
    @staticmethod
    def orders_url(location_id: int = None, start_date: str = None, 
                   end_date: str = None, page: int = 1, per_page: int = 100) -> str:
        """
        Build orders API URL with query parameters
        
        Note: The API only supports single date filtering with created_at_between.
        For date ranges, fetch each day separately and combine results.
        
        Args:
            location_id: Filter by location ID
            start_date: Start date (DD/MM/YY format) - used as single date or start of range
            end_date: End date (DD/MM/YY format) - ignored if different from start_date
            page: Page number for pagination
            per_page: Results per page
        
        Returns:
            Complete URL with query parameters
        """
        params = []
        
        if location_id:
            params.append(f"q%5Border_assignments_location_id_eq%5D={location_id}")
        
        # API only supports single date with created_at_between
        if start_date:
            params.append(f"q%5Bcreated_at_between%5D={start_date}")
        
        params.append(f"page={page}")
        params.append(f"per={per_page}")
        
        query_string = "&".join(params)
        return f"{Endpoints.ORDERS}?{query_string}"
