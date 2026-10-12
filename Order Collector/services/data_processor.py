"""
Data processor - Aggregates and processes order data
"""
from typing import List, Dict, Optional
from collections import defaultdict
from utils.logger import app_logger
from config import DEBUG_MODE


class DataProcessor:
    """Service for processing and aggregating order data"""
    
    # Approved vendors whitelist (API names) in custom sort order
    # Note: Some API names differ from display names (e.g., "ClippingPix" vs "Clipping Pix")
    APPROVED_VENDORS = [
        "Creative Path (P1)",
        "Pixel Path (P2)",
        "Perfect Pixel (GB2)",
        "Grasigner Kitchen",
        "Khandoker Graphics",
        "Graphics Picture",
        "Vectorio",
        "Cutout Edge",
        "Edgebo",
        "Healing Image",
        "Photo Fix Zone",
        "ClippingPix",      # API name (no space)
        "Designing Studio"
    ]
    
    # Map API names to display names (MUST be defined before DISPLAY_TO_ORDER_MAP)
    VENDOR_DISPLAY_MAP = {
        "Creative Path (P1)": "Creative Path (P1)",
        "Pixel Path (P2)": "Pixel Path (P2)",
        "Perfect Pixel (GB2)": "Perfect Pixel (GB2)",
        "Grasigner Kitchen": "Grasigner Kitchen",
        "Khandoker Graphics": "Khandoker Graphics",
        "Graphics Picture": "Graphics Picture",
        "Vectorio": "Vectorio",
        "Cutout Edge": "Cutout Edge",
        "Edgebo": "Edgebo",
        "Healing Image": "Healing Image",
        "Photo Fix Zone": "Photo Fix Zone",
        "ClippingPix": "Clipping Pix",    # Display name (with space)
        "Designing Studio": "Designing Studio"
    }
    
    # Create a mapping for fast lookup and sorting (by API name order)
    VENDOR_ORDER_MAP = {name: idx for idx, name in enumerate(APPROVED_VENDORS)}
    
    # API status values we track
    STATUS_MAP = {
        'cancelled': 'Cancelled'
    }
    
    # Reverse mapping: display name -> sort order index (computed in __init__ or methods)
    # Defined as None here, initialized in group_orders_by_location
    DISPLAY_TO_ORDER_MAP = None
    
    @staticmethod
    def group_orders_by_location(orders: List[Dict]) -> List[Dict]:
        """
        Group orders by location and count each status separately
        
        Args:
            orders: List of order dictionaries from API
        
        Returns:
            List of dicts with location info and status counts
        """
        if not orders:
            app_logger.warning("No orders to process")
            return []
        
        location_data = defaultdict(lambda: {
            'location_title': '',
            'total_orders': 0,
            'cancelled': 0
        })
        
        if DEBUG_MODE:
            app_logger.debug(f"Processing {len(orders)} orders...")
        
        # Pre-initialize ALL 13 approved vendors with zero counts
        # This ensures all vendors appear in results even with 0 orders
        location_data = {}
        for vendor in DataProcessor.APPROVED_VENDORS:
            display_name = DataProcessor.VENDOR_DISPLAY_MAP.get(vendor, vendor)
            location_data[display_name] = {
                'location_title': display_name,
                'total_orders': 0,
                'cancelled': 0
            }
        
        processed_count = 0
        # Track unique order IDs per vendor to avoid double-counting
        vendor_order_ids = {display_name: set() for display_name in location_data}
        
        for order in orders:
            order_id = order.get('id')
            # Extract location info from orderAssignments
            order_assignments = order.get('orderAssignments', [])
            
            for assignment in order_assignments:
                location_title = assignment.get('locationTitle', '').strip()
                
                # Skip empty or whitespace-only location names
                if not location_title:
                    continue
                
                # Filter: only include approved vendors (by API name)
                if location_title not in DataProcessor.APPROVED_VENDORS:
                    continue
                
                # Map to display name
                display_name = DataProcessor.VENDOR_DISPLAY_MAP.get(location_title, location_title)
                status = assignment.get('status', 'unknown').lower()
                
                # Only count if this order hasn't been counted for this vendor yet
                if order_id not in vendor_order_ids[display_name]:
                    vendor_order_ids[display_name].add(order_id)
                    location_data[display_name]['total_orders'] += 1
                    processed_count += 1

                    # Track cancelled status only
                    if status == 'cancelled':
                        location_data[display_name]['cancelled'] += 1
        
        # Sort by custom vendor order (display name order)
        # Build sort map at runtime to avoid class attribute evaluation order issues
        display_to_order = {
            DataProcessor.VENDOR_DISPLAY_MAP[k]: v 
            for k, v in DataProcessor.VENDOR_ORDER_MAP.items()
        }
        
        result = sorted(
            location_data.values(),
            key=lambda x: display_to_order.get(x['location_title'], 999)
        )
        
        app_logger.info(f"Processed {processed_count} assignments into {len(result)} locations")
        
        if DEBUG_MODE and result:
            app_logger.debug("Location summary:")
            for loc in result[:3]:  # Show top 3
                app_logger.debug(f"  {loc['location_title']}: {loc['total_orders']} orders")
        
        return result
    
    @staticmethod
    def get_total_summary(orders: List[Dict], api_total_records: int = None) -> Dict:
        """
        Get overall summary statistics
        
        Args:
            orders: List of order dictionaries
            api_total_records: Total unique orders from API pagination metadata
        
        Returns:
            Dict with summary statistics
        """
        summary = {
            'total_orders': 0,
            'cancelled': 0
        }

        for order in orders:
            assignments = order.get('orderAssignments', [])
            for assignment in assignments:
                status = assignment.get('status', 'unknown').lower()
                summary['total_orders'] += 1

                if status == 'cancelled':
                    summary['cancelled'] += 1
        
        # Calculate total fulfilled
        summary['total_fulfilled'] = summary['total_orders'] - summary['cancelled']
        
        # If API total_records is provided, use it for unique order count
        if api_total_records is not None:
            summary['unique_orders'] = api_total_records
        else:
            # Fallback to unique order IDs
            unique_ids = set()
            for order in orders:
                unique_ids.add(order.get('id'))
            summary['unique_orders'] = len(unique_ids)

        return summary
    
    @staticmethod
    def format_for_display(processed_data: List[Dict]) -> List[List]:
        """
        Format processed data for table display
        
        Args:
            processed_data: List of location data dicts
        
        Returns:
            List of rows for table display
        """
        rows = []
        
        for item in processed_data:
            total_fulfilled = item['total_orders'] - item['cancelled']
            rows.append([
                item['location_title'],
                item['total_orders'],
                item['cancelled'],
                total_fulfilled
            ])
        
        return rows
    
    @staticmethod
    def debug_order_structure(orders: List[Dict]) -> None:
        """Print detailed order structure for debugging"""
        if not DEBUG_MODE:
            return
        
        if not orders:
            app_logger.debug("No orders to debug")
            return
        
        app_logger.debug("=" * 60)
        app_logger.debug("DEBUG: Order Structure Analysis")
        app_logger.debug("=" * 60)
        
        sample = orders[0]
        app_logger.debug(f"Total orders: {len(orders)}")
        app_logger.debug(f"Sample order ID: {sample.get('id', 'N/A')}")
        
        app_logger.debug("\nTop-level keys:")
        for key, value in sample.items():
            value_type = type(value).__name__
            if isinstance(value, list):
                app_logger.debug(f"  {key}: list[{len(value)} items]")
            elif isinstance(value, dict):
                app_logger.debug(f"  {key}: dict[{len(value)} keys]")
            else:
                app_logger.debug(f"  {key}: {value_type} = {str(value)[:100]}")
        
        # Check orderAssignments structure
        assignments = sample.get('orderAssignments', [])
        if assignments:
            app_logger.debug(f"\norderAssignments structure (first item):")
            for key, value in assignments[0].items():
                app_logger.debug(f"  {key}: {type(value).__name__} = {value}")
        
        app_logger.debug("=" * 60)
