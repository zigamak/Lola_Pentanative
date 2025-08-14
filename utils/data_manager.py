import json
import os
import logging
import datetime
import uuid
from typing import Dict, Any, List, Optional, Union
import psycopg2
from psycopg2.extras import RealDictCursor
import sys
import io

# Configure logging with UTF-8 encoding to handle emojis
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
if sys.platform.startswith('win'):
    handler.stream = io.TextIOWrapper(handler.stream.buffer, encoding='utf-8', errors='replace')
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Define a Lead data structure for clarity and type hinting
class Lead:
    def __init__(self, merchant_details_id, phone_number, user_name, user_id=None, source="whatsapp",
                 first_contact=None, last_interaction=None, interaction_count=0,
                 status="new_lead", has_added_to_cart=False, has_placed_order=False,
                 total_cart_value=0.0, conversion_stage="initial_contact", final_order_value=0.0,
                 converted_at=None):
        
        self.merchant_details_id = merchant_details_id
        self.user_id = user_id if user_id is not None else phone_number
        self.user_name = user_name
        self.phone_number = phone_number
        self.source = source
        self.first_contact = first_contact if first_contact else datetime.datetime.now(datetime.timezone.utc)
        self.last_interaction = last_interaction if last_interaction else datetime.datetime.now(datetime.timezone.utc)
        self.interaction_count = interaction_count
        self.status = status
        self.has_added_to_cart = has_added_to_cart
        self.has_placed_order = has_placed_order
        self.total_cart_value = total_cart_value
        self.conversion_stage = conversion_stage
        self.final_order_value = final_order_value
        self.converted_at = converted_at

    def to_dict(self):
        return self.__dict__

class DataManager:
    """Handles data operations, including user details, orders, and leads from PostgreSQL and other data from JSON files."""

    def __init__(self, config):
        self.config = config
        # Retrieve merchant_id from config
        self.merchant_id = getattr(self.config, 'MERCHANT_ID', None)
        if not self.merchant_id:
            logger.error("MERCHANT_ID is not set in config. Using default value '18'.")
            self.merchant_id = '18'  # Default value if not set
        self.db_params = {
            'dbname': self.config.DB_NAME,
            'user': self.config.DB_USER,
            'password': self.config.DB_PASSWORD,
            'host': self.config.DB_HOST,
            'port': self.config.DB_PORT
        }
        self._ensure_data_directory_exists()
        self._ensure_database_columns()
        self.user_details = self.load_user_details()
        self.menu_data = self.load_products_data()

    def _ensure_data_directory_exists(self):
        """Ensures the data directory exists for JSON files."""
        data_dir = os.path.dirname(self.config.PRODUCTS_FILE)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir)
            logger.info(f"Created data directory: {data_dir}")

    def _ensure_database_columns(self):
        """Ensure required columns exist in the whatsapp_orders table."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    # Check and add customers_note column
                    cur.execute("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'whatsapp_orders' 
                        AND column_name = 'customers_note';
                    """)
                    if not cur.fetchone():
                        cur.execute("""
                            ALTER TABLE whatsapp_orders
                            ADD COLUMN customers_note TEXT;
                        """)
                        logger.info("Added customers_note column to whatsapp_orders table.")
                    else:
                        logger.debug("customers_note column already exists in whatsapp_orders table.")

                    # Check and add service_charge column
                    cur.execute("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'whatsapp_orders' 
                        AND column_name = 'service_charge';
                    """)
                    if not cur.fetchone():
                        cur.execute("""
                            ALTER TABLE whatsapp_orders
                            ADD COLUMN service_charge NUMERIC(10,2) DEFAULT 0.0;
                        """)
                        logger.info("Added service_charge column to whatsapp_orders table.")
                    else:
                        logger.debug("service_charge column already exists in whatsapp_orders table.")

                    conn.commit()
        except psycopg2.Error as e:
            logger.error(f"Database error while ensuring columns in whatsapp_orders: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error while ensuring columns in whatsapp_orders: {e}", exc_info=True)

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

    def check_inventory(self, product_id: str, requested_quantity: int) -> bool:
        """Check if sufficient inventory exists for a product."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT quantity
                        FROM whatsapp_merchant_product_inventory
                        WHERE merchant_details_id = %s AND id = %s
                        """,
                        (self.merchant_id, product_id)
                    )
                    result = cur.fetchone()
                    if result and result[0] >= requested_quantity:
                        logger.info(f"Sufficient inventory for product id {product_id}: available {result[0]}, requested {requested_quantity}")
                        return True
                    logger.warning(f"Insufficient inventory for product id {product_id}: available {result[0] if result else 0}, requested {requested_quantity}")
                    return False
        except psycopg2.Error as e:
            logger.error(f"Database error checking inventory for product {product_id}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking inventory for product {product_id}: {e}", exc_info=True)
            return False

    def restore_inventory(self, order_id: str, order_items: List[Dict]) -> bool:
        """Restore inventory in whatsapp_merchant_product_inventory for cancelled orders."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    success = True
                    for item in order_items:
                        product_id = item.get("product_id")
                        quantity = item.get("quantity")
                        if not product_id or not quantity:
                            logger.error(f"Invalid order item for order {order_id}: missing product_id or quantity: {item}")
                            success = False
                            continue
                        cur.execute(
                            """
                            UPDATE whatsapp_merchant_product_inventory
                            SET quantity = quantity + %s,
                                last_updated = %s
                            WHERE merchant_details_id = %s AND id = %s
                            """,
                            (quantity, datetime.datetime.now(datetime.timezone.utc), self.merchant_id, product_id)
                        )
                        logger.info(f"Restored inventory for product id {product_id} by {quantity} for order {order_id}")
                    conn.commit()
                    return success
        except psycopg2.Error as e:
            logger.error(f"Database error restoring inventory for order {order_id}: {e}", exc_info=True)
            conn.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error restoring inventory for order {order_id}: {e}", exc_info=True)
            conn.rollback()
            return False

    def check_low_inventory(self, product_id: str, threshold: int = 5) -> bool:
        """Check if inventory is below threshold and notify merchant."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT quantity
                        FROM whatsapp_merchant_product_inventory
                        WHERE merchant_details_id = %s AND id = %s
                        """,
                        (self.merchant_id, product_id)
                    )
                    result = cur.fetchone()
                    if result and result[0] <= threshold:
                        logger.warning(f"Low inventory for product id {product_id}: {result[0]} units remaining")
                        if self.merchant_phone_number and self.whatsapp_service:
                            self.whatsapp_service.create_text_message(
                                self.merchant_phone_number,
                                f"⚠️ Low inventory alert: Product ID {product_id} has {result[0]} units remaining. Please restock."
                            )
                        return True
                    return False
        except psycopg2.Error as e:
            logger.error(f"Database error checking low inventory for product {product_id}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking low inventory for product {product_id}: {e}", exc_info=True)
            return False
    
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

    def save_user_order(self, order_data: Dict) -> Optional[str]:
        """Save user order and order items to the database."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    # Validate or fetch product_id for each item
                    for item in order_data["items"]:
                        if not item.get("product_id"):
                            # Try to fetch product_id from whatsapp_merchant_product_inventory based on item_name
                            product_id = self._get_product_id_by_name(item["item_name"])
                            if not product_id:
                                logger.error(f"No product_id found for item {item['item_name']} in whatsapp_merchant_product_inventory")
                                return None
                            item["product_id"] = product_id
                            logger.debug(f"Assigned product_id {product_id} to item {item['item_name']}")

                    # Insert into whatsapp_orders
                    cur.execute(
                        """
                        INSERT INTO whatsapp_orders (
                            merchant_details_id, customer_id, business_type_id, address, status,
                            total_amount, payment_reference, payment_method_type, service_charge,
                            timestamp, timestamp_enddate, dateadded, customers_note
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            self.merchant_id,
                            order_data["customer_id"],
                            '1',  # Assuming business_type_id is fixed; adjust as needed
                            order_data["address"],
                            order_data["status"],
                            order_data["total_amount"],
                            order_data["payment_reference"],
                            order_data["payment_method_type"],
                            order_data.get("service_charge", 0.0),
                            order_data["timestamp"],
                            order_data["timestamp"],  # Adjust enddate if needed
                            order_data["timestamp"],
                            order_data.get("customers_note", "")
                        )
                    )
                    order_id = cur.fetchone()[0]
                    logger.info(f"Saved order {order_id} for customer {order_data['customer_id']}")

                    # Insert into whatsapp_order_details
                    for item in order_data["items"]:
                        cur.execute(
                            """
                            INSERT INTO whatsapp_order_details (
                                order_id, item_name, quantity, unit_price, subtotal,
                                total_price, dateadded, product_id
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                order_id,
                                item["item_name"],
                                item["quantity"],
                                item["unit_price"],
                                item["quantity"] * item["unit_price"],
                                item["quantity"] * item["unit_price"],
                                order_data["timestamp"],
                                item["product_id"]
                            )
                        )
                        logger.info(f"Saved order item {item['item_name']} for order {order_id}")

                    conn.commit()
                    return str(order_id)
        except psycopg2.Error as e:
            logger.error(f"Database error saving order for customer {order_data['customer_id']}: {e}", exc_info=True)
            conn.rollback()
            return None
        except Exception as e:
            logger.error(f"Unexpected error saving order for customer {order_data['customer_id']}: {e}", exc_info=True)
            conn.rollback()
            return None

    def update_order_status(self, order_id: str, status: str, additional_data: Dict) -> bool:
        """Update order status and additional data."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE whatsapp_orders
                        SET status = %s,
                            payment_reference = %s,
                            payment_method_type = %s,
                            service_charge = %s,
                            dateadded = %s
                        WHERE id = %s AND merchant_details_id = %s
                        """,
                        (
                            status,
                            additional_data.get("payment_reference"),
                            additional_data.get("payment_method_type", "paystack"),
                            additional_data.get("service_charge", 0.0),
                            datetime.datetime.now(datetime.timezone.utc),
                            order_id,
                            self.merchant_id
                        )
                    )
                    conn.commit()
                    logger.info(f"Updated order {order_id} to status {status}")
                    return True
        except psycopg2.Error as e:
            logger.error(f"Database error updating order {order_id}: {e}", exc_info=True)
            conn.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating order {order_id}: {e}", exc_info=True)
            conn.rollback()
            return False
        
    def reduce_inventory(self, order_id: str, order_items: List[Dict]) -> bool:
        """Reduce inventory in whatsapp_merchant_product_inventory for order items."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    success = True
                    for item in order_items:
                        product_id = item.get("product_id")
                        quantity = item.get("quantity")
                        if not product_id:
                            # Try to fetch product_id by item_name
                            product_id = self._get_product_id_by_name(item.get("item_name"))
                            if not product_id:
                                logger.error(f"Invalid order item for order {order_id}: missing product_id and could not resolve from item_name {item.get('item_name')}")
                                success = False
                                continue
                        if not quantity:
                            logger.error(f"Invalid order item for order {order_id}: missing quantity: {item}")
                            success = False
                            continue
                        # Check if sufficient inventory exists
                        cur.execute(
                            """
                            SELECT quantity
                            FROM whatsapp_merchant_product_inventory
                            WHERE merchant_details_id = %s AND id = %s
                            """,
                            (self.merchant_id, product_id)
                        )
                        result = cur.fetchone()
                        if not result or result[0] < quantity:
                            logger.error(f"Insufficient inventory for product_id {product_id} in order {order_id}: available {result[0] if result else 0}, requested {quantity}")
                            success = False
                            continue
                        # Reduce inventory
                        cur.execute(
                            """
                            UPDATE whatsapp_merchant_product_inventory
                            SET quantity = quantity - %s,
                                last_updated = %s
                            WHERE merchant_details_id = %s AND id = %s
                            """,
                            (quantity, datetime.datetime.now(datetime.timezone.utc), self.merchant_id, product_id)
                        )
                        logger.info(f"Reduced inventory for product_id {product_id} by {quantity} for order {order_id}")
                    conn.commit()
                    return success
        except psycopg2.Error as e:
            logger.error(f"Database error reducing inventory for order {order_id}: {e}", exc_info=True)
            conn.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error reducing inventory for order {order_id}: {e}", exc_info=True)
            conn.rollback()
            return False

    def save_enquiry_to_db(self, enquiry_data: Dict) -> Optional[int]:
        """Save a new enquiry to the whatsapp_enquiry_details table and return the new refId."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    query = """
                        INSERT INTO whatsapp_enquiry_details (
                            merchant_details_id, user_name, user_id, enquiry_categories, 
                            enquiry_text, timestamp, channel
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING "refId"
                    """
                    merchant_id = getattr(self.config, 'MERCHANT_ID', None)
                    if not merchant_id:
                        logger.error("MERCHANT_ID is not set in config, cannot save enquiry.")
                        return None
                    
                    cur.execute(query, (
                        merchant_id,
                        enquiry_data.get("user_name"),
                        enquiry_data.get("user_id"),
                        enquiry_data.get("enquiry_categories", ""),
                        enquiry_data.get("enquiry_text"),
                        enquiry_data.get("timestamp"),
                        enquiry_data.get("channel", "whatsapp")
                    ))
                    enquiry_id = cur.fetchone()[0]
                    conn.commit()
                    logger.info(f"Enquiry {enquiry_id} saved to database")
                    return enquiry_id
        except psycopg2.Error as e:
            logger.error(f"Database error while saving enquiry: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error while saving enquiry: {e}", exc_info=True)
        return None

    def save_enquiry(self, enquiry_data: Dict) -> Optional[int]:
        """Save enquiry. Delegates to database save and returns the new enquiry ID."""
        return self.save_enquiry_to_db(enquiry_data)

    def save_complaint_to_db(self, complaint_data: Dict) -> Optional[int]:
        """Save a new complaint to the whatsapp_complaint_details table and return the new complaint_id."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        INSERT INTO whatsapp_complaint_details (
                            merchant_details_id, user_name, user_id, phone_number,
                            complaint_categories, complaint_text, timestamp, channel,
                            status, priority
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING complaint_id
                    """
                    merchant_id = getattr(self.config, 'MERCHANT_ID', None)
                    if not merchant_id:
                        logger.error("MERCHANT_ID is not set in config, cannot save complaint.")
                        return None
                    
                    complaint_categories = complaint_data.get("complaint_categories", json.dumps(["General"]))
                    complaint_text = complaint_data.get("complaint_text")
                    timestamp = complaint_data.get("timestamp", datetime.datetime.now(datetime.timezone.utc))
                    channel = complaint_data.get("channel", "whatsapp")
                    user_name = complaint_data.get("user_name", "Guest")
                    user_id = complaint_data.get("user_id", None)
                    phone_number = complaint_data.get("phone_number", None)
                    status = complaint_data.get("status", "open")
                    priority = complaint_data.get("priority", "medium")

                    cur.execute(query, (
                        merchant_id,
                        user_name,
                        user_id,
                        phone_number,
                        complaint_categories,
                        complaint_text,
                        timestamp,
                        channel,
                        status,
                        priority
                    ))
                    result = cur.fetchone()
                    if result is None:
                        logger.error("No complaint_id returned after insert.")
                        return None
                    complaint_id = result['complaint_id']
                    conn.commit()
                    logger.info(f"Complaint {complaint_id} saved to database")
                    return complaint_id
        except psycopg2.Error as e:
            logger.error(f"Database error while saving complaint: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error while saving complaint: {e}", exc_info=True)
            return None

    def save_complaint(self, complaint_data: Dict) -> Optional[int]:
        """Save complaint. Delegates to database save and returns the new complaint ID."""
        return self.save_complaint_to_db(complaint_data)

    def _save_to_file(self, filename: str, data: Dict, data_type: str):
        """Generic method to save data (like enquiry/complaint if not using DB) to JSON file."""
        existing_data = self._load_json_data(filename)
        if not isinstance(existing_data, list):
            existing_data = []
        
        existing_data.append(data)
        self._save_json_data(filename, existing_data)
        logger.info(f"{data_type.capitalize()} details saved to {filename}")

    def get_address_from_order_details(self, phone_number: str) -> Optional[str]:
        """Get the most recent address for a phone number from whatsapp_orders, with fallback to whatsapp_user_details."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT address, timestamp
                        FROM whatsapp_orders
                        WHERE customer_id = %s AND address IS NOT NULL
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """
                    cur.execute(query, (phone_number,))
                    result = cur.fetchone()
                    if result:
                        logger.debug(f"Found address '{result['address']}' for phone number {phone_number} in whatsapp_orders")
                        return result['address']

                    logger.debug(f"No address found in whatsapp_orders for phone number {phone_number}. Trying whatsapp_user_details.")
                    query = """
                        SELECT address
                        FROM whatsapp_user_details
                        WHERE user_number = %s AND address IS NOT NULL
                        LIMIT 1
                    """
                    cur.execute(query, (phone_number,))
                    result = cur.fetchone()
                    if result:
                        logger.debug(f"Found address '{result['address']}' for phone number {phone_number} in whatsapp_user_details")
                        return result['address']
                    
                    logger.debug(f"No address found in whatsapp_user_details for phone number {phone_number}")
                    return None
        except psycopg2.Error as e:
            logger.error(f"Database error while retrieving address for phone number {phone_number}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error while retrieving address for phone number {phone_number}: {e}", exc_info=True)
            return None

    def get_order_by_id(self, order_id: str) -> Optional[Dict]:
        """Retrieve order by ID."""
        try:
            # Validate order_id first
            if not order_id or str(order_id).lower() == "none":
                logger.error(f"Invalid order_id provided: {order_id}")
                return None
                
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT id, customer_id, address, status, total_amount,
                            payment_reference, payment_method_type, service_charge,
                            dateadded, customers_note
                        FROM whatsapp_orders
                        WHERE id = %s AND merchant_details_id = %s
                        """,
                        (order_id, self.merchant_id)
                    )
                    result = cur.fetchone()
                    if result:
                        return {
                            "id": result['id'],
                            "customer_id": result['customer_id'],
                            "address": result['address'],
                            "status": result['status'],
                            "total_amount": float(result['total_amount']),
                            "payment_reference": result['payment_reference'],
                            "payment_method_type": result['payment_method_type'],
                            "service_charge": float(result['service_charge']),
                            "dateadded": result['dateadded'],
                            "customers_note": result['customers_note']
                        }
                    logger.warning(f"Order {order_id} not found")
                    return None
        except psycopg2.Error as e:
            logger.error(f"Database error retrieving order {order_id}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving order {order_id}: {e}", exc_info=True)
            return None
        
    def get_order_by_payment_reference(self, payment_reference: str) -> Optional[Dict]:
        """Retrieve order by payment reference."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, customer_id, address, status, total_amount,
                               payment_reference, payment_method_type, service_charge,
                               dateadded, customers_note
                        FROM whatsapp_orders
                        WHERE payment_reference = %s AND merchant_details_id = %s
                        """,
                        (payment_reference, self.merchant_id)
                    )
                    result = cur.fetchone()
                    if result:
                        return {
                            "id": result[0],
                            "customer_id": result[1],
                            "address": result[2],
                            "status": result[3],
                            "total_amount": float(result[4]),
                            "payment_reference": result[5],
                            "payment_method_type": result[6],
                            "service_charge": float(result[7]),
                            "dateadded": result[8],
                            "customers_note": result[9]
                        }
                    logger.warning(f"Order with payment reference {payment_reference} not found")
                    return None
        except psycopg2.Error as e:
            logger.error(f"Database error retrieving order for payment reference {payment_reference}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving order for payment reference {payment_reference}: {e}", exc_info=True)
            return None

    def get_order_items(self, order_id: str) -> List[Dict]:
        """Retrieve order items by order ID."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT item_name, quantity, unit_price, subtotal, product_id
                        FROM whatsapp_order_details
                        WHERE order_id = %s
                        """,
                        (order_id,)
                    )
                    results = cur.fetchall()
                    items = [
                        {
                            "item_name": row[0],
                            "quantity": row[1],
                            "unit_price": float(row[2]),
                            "subtotal": float(row[3]),
                            "product_id": row[4]
                        } for row in results
                    ]
                    logger.info(f"Retrieved {len(items)} items for order {order_id}")
                    return items
        except psycopg2.Error as e:
            logger.error(f"Database error retrieving items for order {order_id}: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"Unexpected error retrieving items for order {order_id}: {e}", exc_info=True)
            return []


    def save_lead(self, lead: Lead):
        """Save or update a lead in the whatsapp_leads table."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    query = """
                        INSERT INTO whatsapp_leads (
                            merchant_details_id, user_id, user_name, phone_number, source,
                            first_contact, last_interaction, interaction_count, status,
                            has_added_to_cart, has_placed_order, total_cart_value,
                            conversion_stage, final_order_value, converted_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (merchant_details_id, user_id) DO UPDATE
                        SET 
                            user_name = EXCLUDED.user_name,
                            phone_number = EXCLUDED.phone_number,
                            source = EXCLUDED.source,
                            first_contact = EXCLUDED.first_contact,
                            last_interaction = EXCLUDED.last_interaction,
                            interaction_count = EXCLUDED.interaction_count,
                            status = EXCLUDED.status,
                            has_added_to_cart = EXCLUDED.has_added_to_cart,
                            has_placed_order = EXCLUDED.has_placed_order,
                            total_cart_value = EXCLUDED.total_cart_value,
                            conversion_stage = EXCLUDED.conversion_stage,
                            final_order_value = EXCLUDED.final_order_value,
                            converted_at = EXCLUDED.converted_at
                    """
                    # Ensure correct types for database insertion
                    total_cart_value = float(lead.total_cart_value) if lead.total_cart_value is not None else 0.0
                    final_order_value = float(lead.final_order_value) if lead.final_order_value is not None else 0.0
                    converted_at = lead.converted_at if lead.converted_at else None

                    # Log values for debugging
                    logger.debug(f"Saving lead {lead.user_id}: "
                                f"merchant_details_id={lead.merchant_details_id}, "
                                f"user_id={lead.user_id}, user_name={lead.user_name}, "
                                f"phone_number={lead.phone_number}, source={lead.source}, "
                                f"first_contact={lead.first_contact}, last_interaction={lead.last_interaction}, "
                                f"interaction_count={lead.interaction_count}, status={lead.status}, "
                                f"has_added_to_cart={lead.has_added_to_cart}, has_placed_order={lead.has_placed_order}, "
                                f"total_cart_value={total_cart_value}, conversion_stage={lead.conversion_stage}, "
                                f"final_order_value={final_order_value}, converted_at={converted_at}")

                    cur.execute(query, (
                        lead.merchant_details_id,
                        lead.user_id,
                        lead.user_name,
                        lead.phone_number,
                        lead.source,
                        lead.first_contact,
                        lead.last_interaction,
                        lead.interaction_count,
                        lead.status,
                        lead.has_added_to_cart,
                        lead.has_placed_order,
                        total_cart_value,
                        lead.conversion_stage,
                        final_order_value,
                        converted_at
                    ))
                    conn.commit()
                    logger.info(f"Lead {lead.user_id} saved to whatsapp_leads table")
        except psycopg2.Error as e:
            logger.error(f"Database error while saving lead {lead.user_id} to whatsapp_leads: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error while saving lead {lead.user_id} to whatsapp_leads: {e}", exc_info=True)
            raise
    def get_lead(self, merchant_details_id: str, user_id: str) -> Optional[Lead]:
        """Retrieve a lead from the whatsapp_leads table."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT 
                            merchant_details_id, user_id, user_name, phone_number, source,
                            first_contact, last_interaction, interaction_count, status,
                            has_added_to_cart, has_placed_order, total_cart_value,
                            conversion_stage, final_order_value, converted_at
                        FROM whatsapp_leads
                        WHERE merchant_details_id = %s AND user_id = %s
                    """
                    cur.execute(query, (merchant_details_id, user_id))
                    result = cur.fetchone()
                    if result:
                        logger.info(f"Retrieved lead {user_id} for merchant {merchant_details_id} from whatsapp_leads")
                        return Lead(**result)
                    else:
                        logger.debug(f"No lead found for user {user_id} and merchant {merchant_details_id} in whatsapp_leads")
                        return None
        except psycopg2.Error as e:
            logger.error(f"Database error while retrieving lead {user_id} from whatsapp_leads: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error while retrieving lead {user_id} from whatsapp_leads: {e}", exc_info=True)
            return None

    def get_product_by_name(self, product_name: str) -> Optional[Dict]:
        """Retrieve product details by name from products file."""
        try:
            with open(self.products_file, 'r', encoding='utf-8') as f:
                products = json.load(f)
            for product in products:
                if product.get('name').lower() == product_name.lower():
                    return product
            logger.warning(f"Product {product_name} not found in {self.products_file}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving product {product_name}: {e}", exc_info=True)
            return None

    def _get_product_id_by_name(self, product_name: str) -> Optional[str]:
        """Retrieve product_id from whatsapp_merchant_product_inventory by product_name."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id
                        FROM whatsapp_merchant_product_inventory
                        WHERE merchant_details_id = %s AND product_name = %s
                        """,
                        (self.merchant_id, product_name)
                    )
                    result = cur.fetchone()
                    if result:
                        logger.debug(f"Found product_id {result[0]} for product_name {product_name}")
                        return str(result[0])
                    logger.warning(f"No product found with name {product_name} for merchant {self.merchant_id}")
                    return None
        except psycopg2.Error as e:
            logger.error(f"Database error retrieving product_id for {product_name}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving product_id for {product_name}: {e}", exc_info=True)
            return None
    
    def save_feedback_to_db(self, feedback_data: Dict) -> bool:
        """Save feedback data to the whatsapp_feedback table."""
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    INSERT INTO whatsapp_feedback (phone_number, user_name, order_id, rating, comment, timestamp, session_duration)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """
                cur.execute(query, (
                    feedback_data['phone_number'],
                    feedback_data['user_name'],
                    feedback_data['order_id'],
                    feedback_data['rating'],
                    feedback_data['comment'],
                    feedback_data['timestamp'],
                    feedback_data['session_duration']
                ))
                self.conn.commit()
                feedback_id = cur.fetchone()['id']
                logger.info(f"Saved feedback to database with ID {feedback_id} for order {feedback_data['order_id']}")
                return True
        except Exception as e:
            logger.error(f"Error saving feedback to database: {str(e)}", exc_info=True)
            self.conn.rollback()
            return False

    def get_feedback_analytics(self) -> Dict[str, Any]:
        """Get feedback analytics summary from database."""
        try:
            with self.data_manager.conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT phone_number, user_name, order_id, rating, comment, timestamp, session_duration
                    FROM whatsapp_feedback
                """
                cur.execute(query)
                feedback_list = cur.fetchall()

            if not feedback_list:
                return {"total_feedback": 0, "message": "No feedback data available"}

            total_feedback = len(feedback_list)
            rating_counts = {}
            total_comments = 0
            recent_feedback = []

            for feedback in feedback_list:
                rating = feedback.get("rating", "unknown")
                rating_counts[rating] = rating_counts.get(rating, 0) + 1

                if feedback.get("comment", "").strip():
                    total_comments += 1

                if len(recent_feedback) < 10:
                    recent_feedback.append({
                        "order_id": feedback.get("order_id", "N/A"),
                        "rating": rating,
                        "comment": feedback.get("comment", "")[:100] + "..." if len(feedback.get("comment", "")) > 100 else feedback.get("comment", ""),
                        "timestamp": feedback.get("timestamp", "N/A")
                    })

            rating_percentages = {
                rating: round((count / total_feedback) * 100, 1)
                for rating, count in rating_counts.items()
            }

            return {
                "total_feedback": total_feedback,
                "rating_counts": rating_counts,
                "rating_percentages": rating_percentages,
                "total_comments": total_comments,
                "comment_percentage": round((total_comments / total_feedback) * 100, 1),
                "recent_feedback": recent_feedback,
                "last_updated": datetime.datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting feedback analytics: {str(e)}", exc_info=True)
            return {"error": "Failed to load feedback analytics"}
        
    def get_lead_by_phone_number(self, phone_number: str) -> Optional[Lead]:
        """Retrieve a lead by phone number from the whatsapp_leads table."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    merchant_id = getattr(self.config, 'MERCHANT_ID', '18')
                    query = """
                        SELECT 
                            merchant_details_id, user_id, user_name, phone_number, source,
                            first_contact, last_interaction, interaction_count, status,
                            has_added_to_cart, has_placed_order, total_cart_value,
                            conversion_stage, final_order_value, converted_at
                        FROM whatsapp_leads
                        WHERE merchant_details_id = %s AND phone_number = %s
                    """
                    cur.execute(query, (merchant_id, phone_number))
                    result = cur.fetchone()
                    if result:
                        logger.info(f"Retrieved lead by phone number {phone_number} from whatsapp_leads")
                        return Lead(**result)
                    else:
                        logger.debug(f"No lead found for phone number {phone_number} in whatsapp_leads")
                        return None
        except psycopg2.Error as e:
            logger.error(f"Database error while retrieving lead by phone {phone_number} from whatsapp_leads: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error while retrieving lead by phone {phone_number} from whatsapp_leads: {e}", exc_info=True)
            return None

    def get_leads_by_status(self, status: str) -> List[Lead]:
        """Retrieve leads by status from the whatsapp_leads table."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    merchant_id = getattr(self.config, 'MERCHANT_ID', '18')
                    query = """
                        SELECT 
                            merchant_details_id, user_id, user_name, phone_number, source,
                            first_contact, last_interaction, interaction_count, status,
                            has_added_to_cart, has_placed_order, total_cart_value,
                            conversion_stage, final_order_value, converted_at
                        FROM whatsapp_leads
                        WHERE merchant_details_id = %s AND status = %s
                        ORDER BY last_interaction DESC
                    """
                    cur.execute(query, (merchant_id, status))
                    results = cur.fetchall()
                    leads = [Lead(**result) for result in results]
                    logger.info(f"Retrieved {len(leads)} leads with status {status} from whatsapp_leads")
                    return leads
        except psycopg2.Error as e:
            logger.error(f"Database error while retrieving leads by status {status} from whatsapp_leads: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"Unexpected error while retrieving leads by status {status} from whatsapp_leads: {e}", exc_info=True)
            return []

    def get_abandoned_cart_leads(self, hours_ago: int = 24) -> List[Dict]:
        """Get leads with abandoned carts for remarketing from whatsapp_leads."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    merchant_id = getattr(self.config, 'MERCHANT_ID', '18')
                    cutoff_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_ago)
                    
                    query = """
                        SELECT 
                            user_id, user_name, phone_number, total_cart_value,
                            last_interaction, conversion_stage
                        FROM whatsapp_leads
                        WHERE merchant_details_id = %s 
                        AND has_added_to_cart = true 
                        AND has_placed_order = false
                        AND last_interaction < %s
                        AND total_cart_value > 0
                        ORDER BY total_cart_value DESC
                    """
                    cur.execute(query, (merchant_id, cutoff_time))
                    results = cur.fetchall()
                    abandoned_carts = [dict(result) for result in results]
                    logger.info(f"Retrieved {len(abandoned_carts)} abandoned carts from {hours_ago} hours ago from whatsapp_leads")
                    return abandoned_carts
        except psycopg2.Error as e:
            logger.error(f"Database error while retrieving abandoned carts from whatsapp_leads: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"Unexpected error while retrieving abandoned carts from whatsapp_leads: {e}", exc_info=True)
            return []