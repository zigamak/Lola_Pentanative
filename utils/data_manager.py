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
        self.menu_data = self.load_products_data()

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
        """Save a new order to the whatsapp_orders table."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    query = """
                        INSERT INTO whatsapp_orders (
                            order_id, merchant_details_id, customer_id, 
                            business_type_id, address, status, total_amount,
                            payment_reference, payment_method_type, timestamp,
                            timestamp_enddate, DateAdded
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    merchant_details_id = getattr(self.config, 'MERCHANT_ID', None) # Assuming MERCHANT_ID maps to merchant_details_id
                    business_type_id = getattr(self.config, 'BUSINESS_TYPE_ID', None)

                    cur.execute(query, (
                        order_data.get("order_id"),
                        merchant_details_id,
                        order_data.get("user_id"), # Maps to customer_id in DB
                        business_type_id,
                        order_data.get("address"),
                        order_data.get("status"),
                        int(order_data.get("total_amount") * 100),
                        order_data.get("payment_reference", ""),
                        order_data.get("payment_method_type", ""),
                        order_data.get("timestamp"),
                        None, # Assuming timestamp_enddate is populated later or is nullable
                        datetime.datetime.now() # Populate DateAdded with current timestamp
                    ))
                    conn.commit()
                    logger.info(f"Order {order_data.get('order_id')} saved to database")
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

    def save_enquiry(self, enquiry_data: Dict):
        """Save enquiry to file."""
        self._save_to_file(self.config.ENQUIRY_DETAILS_FILE, enquiry_data, "enquiry")

    def save_complaint(self, complaint_data: Dict):
        """Save complaint to file."""
        self._save_to_file(self.config.COMPLAINT_DETAILS_FILE, complaint_data, "complaint")

    def _save_to_file(self, filename: str, data: Dict, data_type: str):
        """Generic method to save data (like enquiry/complaint) to JSON file."""
        existing_data = self._load_json_data(filename)
        if not isinstance(existing_data, list):
            existing_data = []

        existing_data.append(data)
        self._save_json_data(filename, existing_data)
        logger.info(f"{data_type.capitalize()} details saved to {filename}")

    def get_address_from_order_details(self, phone_number: str) -> Optional[str]:
        """
        Get the most recent address for a phone number.
        This function now fetches the address from 'whatsapp_user_details'
        as per the new requirement, instead of 'whatsapp_orders'.
        A more descriptive name for this function might be get_address_from_user_details.
        """
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Querying whatsapp_user_details as per the latest instruction
                    query = """
                        SELECT address, address2, address3
                        FROM whatsapp_user_details
                        WHERE user_number = %s
                        LIMIT 1 -- Assuming one user number maps to one set of addresses
                    """
                    cur.execute(query, (phone_number,))
                    result = cur.fetchone()
                    if result:
                        # Prioritize address, then address2, then address3
                        if result.get('address'):
                            logger.debug(f"Found primary address '{result['address']}' for phone number {phone_number} from user details.")
                            return result['address']
                        elif result.get('address2'):
                            logger.debug(f"Found secondary address '{result['address2']}' for phone number {phone_number} from user details.")
                            return result['address2']
                        elif result.get('address3'):
                            logger.debug(f"Found tertiary address '{result['address3']}' for phone number {phone_number} from user details.")
                            return result['address3']
                    logger.debug(f"No address found for phone number {phone_number} in whatsapp_user_details.")
                    return None
        except psycopg2.Error as e:
            logger.error(f"Database error while fetching address for {phone_number} from user details: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error while fetching address for {phone_number} from user details: {e}", exc_info=True)
            return None

    def get_order_by_payment_reference(self, payment_reference: str) -> Optional[Dict]:
        """Get order data by payment reference from whatsapp_orders."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT
                            order_id, merchant_details_id, customer_id,
                            business_type_id, address, status, total_amount,
                            payment_reference, payment_method_type, timestamp,
                            timestamp_enddate, DateAdded
                        FROM whatsapp_orders
                        WHERE payment_reference = %s
                    """
                    cur.execute(query, (payment_reference,))
                    result = cur.fetchone()
                    if result:
                        order_data = dict(result)
                        order_data['total_amount'] = order_data['total_amount'] / 100.0
                        # Map DB column names back to code's expected names if necessary
                        order_data['user_id'] = order_data.pop('customer_id')
                        order_data['merchant_id'] = order_data.pop('merchant_details_id')
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