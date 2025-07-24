import json
import os
import logging
import datetime
import uuid
from typing import Dict, Any, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

class DataManager:
    """Handles data operations, including user details and orders from PostgreSQL and other data from JSON files."""

    def __init__(self, config):
        self.config = config
        self.db_params = {
            'dbname': self.config.DB_NAME,
            'user': self.config.DB_USER,
            'password': self.config.DB_PASSWORD,
            'host': self.config.DB_HOST,
            'port': self.config.DB_PORT
        }
        self._ensure_data_directory_exists()
        self.user_details = self.load_user_details()
        self.menu_data = self.load_products_data() # Initial load

    def _ensure_data_directory_exists(self):
        """Ensures the data directory exists for JSON files."""
        data_dir = os.path.dirname(self.config.PRODUCTS_FILE)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir)
            logger.info(f"Created data directory: {data_dir}")

    def _load_json_data(self, file_path: str) -> Any:
        """Helper to load JSON data from a file."""
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from {file_path}: {e}")
            except Exception as e:
                logger.error(f"Error loading data from {file_path}: {e}")
        logger.warning(f"File not found or empty: {file_path}")
        return []

    def _save_json_data(self, file_path: str, data: Any):
        """Helper to save JSON data to a file."""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Data saved to {file_path}")
        except Exception as e:
            logger.error(f"Error saving data to {file_path}: {e}")

    def load_products_data(self) -> Dict:
        """Load product data from JSON file."""
        menu_data = self._load_json_data(self.config.PRODUCTS_FILE)
        if not isinstance(menu_data, dict):
            logger.warning(f"Product data in {self.config.PRODUCTS_FILE} is not a dictionary. Initializing as empty.")
            return {}
        return menu_data

    def reload_products_data(self):
        """Reloads product data from the JSON file. Call this after a sync."""
        logger.info("Reloading product data in DataManager...")
        self.menu_data = self.load_products_data()
        logger.info(f"Product data reloaded. Contains {len(self.menu_data)} categories.")

    def load_user_details(self) -> Dict[str, Dict[str, str]]:
        """Load user details from the whatsapp_user_details table."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT 
                            user_id,
                            user_name,
                            user_number,
                            address,
                            user_perferred_name,
                            address2,
                            address3
                        FROM whatsapp_user_details
                    """
                    cur.execute(query)
                    rows = cur.fetchall()

                    user_details_dict = {}
                    for row in rows:
                        user_id = row['user_id']
                        user_details_dict[user_id] = {
                            "name": row['user_name'] or '',
                            "phone_number": row['user_number'] or '',
                            "address": row['address'] or '',
                            "user_perferred_name": row['user_perferred_name'] or '',
                            "address2": row['address2'] or '',
                            "address3": row['address3'] or '',
                            "display_name": row['user_perferred_name'] or row['user_name'] or 'Guest' if row['user_id'] == row['user_number'] else row['user_name'] or 'Guest'
                        }
                    logger.info(f"Successfully loaded {len(user_details_dict)} user details from database")
                    return user_details_dict
        except psycopg2.Error as e:
            logger.error(f"Database error while loading user details: {e}", exc_info=True)
            return {}
        except Exception as e:
            logger.error(f"Unexpected error while loading user details: {e}", exc_info=True)
            return {}

    def save_user_details(self, user_id: str, data: Dict[str, str]):
        """Save or update user details in the whatsapp_user_details table."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    query = """
                        INSERT INTO whatsapp_user_details (
                            user_id, user_name, user_number, address, 
                            user_perferred_name, address2, address3
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id) DO UPDATE
                        SET 
                            user_name = EXCLUDED.user_name,
                            user_number = EXCLUDED.user_number,
                            address = EXCLUDED.address,
                            user_perferred_name = EXCLUDED.user_perferred_name,
                            address2 = EXCLUDED.address2,
                            address3 = EXCLUDED.address3
                    """
                    cur.execute(query, (
                        user_id,
                        data.get("name", ""),
                        data.get("phone_number", user_id),
                        data.get("address", ""),
                        data.get("user_perferred_name", data.get("name", "")),
                        data.get("address2", ""),
                        data.get("address3", "")
                    ))
                    conn.commit()
                    self.user_details[user_id] = {
                        "name": data.get("name", ""),
                        "phone_number": data.get("phone_number", user_id),
                        "address": data.get("address", ""),
                        "user_perferred_name": data.get("user_perferred_name", data.get("name", "")),
                        "address2": data.get("address2", ""),
                        "address3": data.get("address3", ""),
                        "display_name": data.get("user_perferred_name", data.get("name", "Guest")) if user_id == data.get("phone_number", user_id) else data.get("name", "Guest")
                    }
                    logger.info(f"User details for {user_id} saved to database")
        except psycopg2.Error as e:
            logger.error(f"Database error while saving user details for {user_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error while saving user details for {user_id}: {e}", exc_info=True)

    def get_user_data(self, user_id: str) -> Optional[Dict[str, str]]:
        """Retrieves user-specific data, returning user_perferred_name if user_id matches user_number."""
        user_data = self.user_details.get(user_id)
        if user_data:
            logger.debug(f"Retrieved user data for {user_id}: {user_data}")
            return user_data
        logger.debug(f"No user data found for {user_id}")
        return None

    def save_user_order(self, order_data: Dict):
        """Save a new order to the whatsapp_orders and whatsapp_order_details tables."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    # Insert into whatsapp_orders
                    order_query = """
                        INSERT INTO whatsapp_orders (
                            order_id, merchant_id, user_id, user_name, user_number, 
                            business_type_id, address, status, total_amount, 
                            payment_reference, payment_method_type, timestamp
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    merchant_id = getattr(self.config, 'MERCHANT_ID', None)
                    business_type_id = getattr(self.config, 'BUSINESS_TYPE_ID', None)

                    cur.execute(order_query, (
                        order_data.get("order_id"),
                        merchant_id,
                        order_data.get("user_id"),
                        order_data.get("user_name"),
                        order_data.get("user_number"),
                        business_type_id,
                        order_data.get("address"),
                        order_data.get("status"),
                        int(order_data.get("total_amount") * 100),
                        order_data.get("payment_reference", ""),
                        order_data.get("payment_method_type", ""),
                        order_data.get("timestamp")
                    ))

                    # Insert into whatsapp_order_details
                    order_details_query = """
                        INSERT INTO whatsapp_order_details (
                            order_id, item_name, quantity, unit_price
                        )
                        VALUES (%s, %s, %s, %s)
                    """
                    order_items = order_data.get("items", [])
                    for item in order_items:
                        cur.execute(order_details_query, (
                            order_data.get("order_id"),
                            item.get("item_name"),
                            item.get("quantity"),
                            item.get("unit_price")
                        ))

                    conn.commit()
                    logger.info(f"Order {order_data.get('order_id')} and its details saved to database")
        except psycopg2.Error as e:
            logger.error(f"Database error while saving order {order_data.get('order_id', 'unknown')}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error while saving order {order_data.get('order_id', 'unknown')}: {e}", exc_info=True)

    def update_order_status(self, order_id: str, status: str, payment_data: Optional[Dict] = None) -> bool:
        """Update order status in the whatsapp_orders table."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    query = """
                        UPDATE whatsapp_orders
                        SET status = %s,
                            payment_reference = %s,
                            payment_method_type = %s
                        WHERE order_id = %s
                        RETURNING order_id
                    """
                    payment_reference = payment_data.get("payment_reference", "") if payment_data else ""
                    payment_method_type = payment_data.get("payment_method_type", "") if payment_data else ""
                    cur.execute(query, (status, payment_reference, payment_method_type, order_id))
                    result = cur.fetchone()
                    conn.commit()
                    if result:
                        logger.info(f"Order {order_id} status updated to {status} in database")
                        return True
                    else:
                        logger.warning(f"Order {order_id} not found in database for status update")
                        return False
        except psycopg2.Error as e:
            logger.error(f"Database error while updating order {order_id} status: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error while updating order {order_id} status: {e}", exc_info=True)
            return False

    def save_enquiry_to_db(self, enquiry_data: Dict):
        """Save a new enquiry to the whatsapp_enquiry_details table."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    query = """
                        INSERT INTO whatsapp_enquiry_details (
                            merchant_id, user_name, user_id, enquiry_categories, 
                            enquiry_text, timestamp, channel
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    merchant_id = getattr(self.config, 'MERCHANT_ID', None) 
                    
                    cur.execute(query, (
                        merchant_id,
                        enquiry_data.get("user_name"),
                        enquiry_data.get("user_id"),
                        enquiry_data.get("enquiry_categories", ""), 
                        enquiry_data.get("enquiry_text"),
                        enquiry_data.get("timestamp"),
                        enquiry_data.get("channel", "whatsapp")
                    ))
                    conn.commit()
                    logger.info(f"Enquiry {enquiry_data.get('enquiry_id', 'unknown')} saved to database")
        except psycopg2.Error as e:
            logger.error(f"Database error while saving enquiry {enquiry_data.get('enquiry_id', 'unknown')}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error while saving enquiry {enquiry_data.get('enquiry_id', 'unknown')}: {e}", exc_info=True)

    def save_enquiry(self, enquiry_data: Dict):
        """Save enquiry. Delegates to database save."""
        self.save_enquiry_to_db(enquiry_data)
        
    def save_complaint_to_db(self, complaint_data: Dict):
        """Save a new complaint to the whatsapp_complaint_details table."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    query = """
                        INSERT INTO whatsapp_complaint_details (
                            complaint_id, merchant_id, user_name, user_id, 
                            complaint_categories, complaint_text, timestamp
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    merchant_id = getattr(self.config, 'MERCHANT_ID', None) 
                    
                    cur.execute(query, (
                        complaint_data.get("complaint_id"),
                        merchant_id,
                        complaint_data.get("user_name"),
                        complaint_data.get("user_id"),
                        complaint_data.get("complaint_categories", ""),
                        complaint_data.get("complaint_text"),
                        complaint_data.get("timestamp")
                    ))
                    conn.commit()
                    logger.info(f"Complaint {complaint_data.get('complaint_id', 'unknown')} saved to database")
        except psycopg2.Error as e:
            logger.error(f"Database error while saving complaint {complaint_data.get('complaint_id', 'unknown')}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error while saving complaint {complaint_data.get('complaint_id', 'unknown')}: {e}", exc_info=True)

    def save_complaint(self, complaint_data: Dict):
        """Save complaint. Delegates to database save."""
        self.save_complaint_to_db(complaint_data)

    def _save_to_file(self, filename: str, data: Dict, data_type: str):
        """Generic method to save data (like enquiry/complaint if not using DB) to JSON file."""
        existing_data = self._load_json_data(filename)
        if not isinstance(existing_data, list):
            existing_data = []
        
        existing_data.append(data)
        self._save_json_data(filename, existing_data)
        logger.info(f"{data_type.capitalize()} details saved to {filename}")

    def get_address_from_order_details(self, phone_number: str) -> Optional[str]:
        """Get the most recent address for a phone number from whatsapp_orders."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT address, timestamp
                        FROM whatsapp_orders
                        WHERE user_number = %s AND address IS NOT NULL
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """
                    cur.execute(query, (phone_number,))
                    result = cur.fetchone()
                    if result:
                        logger.debug(f"Found address '{result['address']}' for phone number {phone_number}")
                        return result['address']
                    logger.debug(f"No address found for phone number {phone_number}")
                    return None
        except psycopg2.Error as e:
            logger.error(f"Database error while fetching address for {phone_number}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error while fetching address for {phone_number}: {e}", exc_info=True)
            return None

    def get_order_by_payment_reference(self, payment_reference: str) -> Optional[Dict]:
        """Get order data by payment reference from whatsapp_orders."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT 
                            order_id, merchant_id, user_id, user_name, user_number,
                            business_type_id, address, status, total_amount,
                            payment_reference, payment_method_type, timestamp
                        FROM whatsapp_orders
                        WHERE payment_reference = %s
                    """
                    cur.execute(query, (payment_reference,))
                    result = cur.fetchone()
                    if result:
                        order_data = dict(result)
                        order_data['total_amount'] = order_data['total_amount'] / 100.0
                        logger.debug(f"Found order for payment reference {payment_reference}: {order_data}")
                        return order_data
                    logger.debug(f"No order found for payment reference {payment_reference}")
                    return None
        except psycopg2.Error as e:
            logger.error(f"Database error while fetching order by payment reference {payment_reference}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error while fetching order by payment reference {payment_reference}: {e}", exc_info=True)
            return None

    def update_session_state(self, session_id: str, state: Dict):
        """Placeholder for session state update."""
        logger.debug(f"DataManager: Session state update requested for {session_id} (Pass-through).")
        pass