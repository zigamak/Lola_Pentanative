import json
import os
import logging
import datetime
import uuid
from typing import Dict, Any, List, Optional, Union
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

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
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Insert into whatsapp_orders, letting the database generate the id
                    order_query = """
                        INSERT INTO whatsapp_orders (
                            merchant_details_id, customer_id, 
                            business_type_id, address, status, total_amount, 
                            payment_reference, payment_method_type, timestamp, 
                            timestamp_enddate, dateadded
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """
                    # Provide a default for MERCHANT_ID and BUSINESS_TYPE_ID if they are not set in config
                    merchant_details_id = getattr(self.config, 'MERCHANT_ID', '18')
                    business_type_id = getattr(self.config, 'BUSINESS_TYPE_ID', '1')

                    # Validate merchant_details_id
                    if merchant_details_id is None:
                        logger.error("MERCHANT_ID is not set in config and no default provided.")
                        raise ValueError("MERCHANT_ID is required but was not provided.")

                    order_timestamp = order_data.get("timestamp", datetime.datetime.now(datetime.timezone.utc))
                    order_timestamp_enddate = order_data.get("timestamp_enddate", datetime.datetime.now(datetime.timezone.utc))
                    order_dateadded = order_data.get("dateadded", datetime.datetime.now(datetime.timezone.utc))

                    cur.execute(order_query, (
                        merchant_details_id,
                        order_data.get("customer_id"),
                        business_type_id,
                        order_data.get("address"),
                        order_data.get("status"),
                        float(order_data.get("total_amount", 0.0)),
                        order_data.get("payment_reference", ""),
                        order_data.get("payment_method_type", ""),
                        order_timestamp,
                        order_timestamp_enddate,
                        order_dateadded
                    ))
                    order_id = cur.fetchone()['id']

                    # Insert into whatsapp_order_details
                    order_details_query = """
                        INSERT INTO whatsapp_order_details (
                            order_id, item_name, quantity, unit_price, subtotal, total_price, dateadded
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    order_items = order_data.get("items", [])
                    if not order_items:
                        logger.warning(f"No items provided for order {order_id}")
                    
                    for item in order_items:
                        item_name = item.get("item_name")
                        quantity = item.get("quantity")
                        unit_price = float(item.get("unit_price", 0.0))
                        item_subtotal = quantity * unit_price
                        item_total_price = item_subtotal 
                        item_dateadded = datetime.datetime.now(datetime.timezone.utc)

                        cur.execute(order_details_query, (
                            order_id,
                            item_name,
                            quantity,
                            unit_price,
                            item_subtotal,
                            item_total_price,
                            item_dateadded
                        ))

                    conn.commit()
                    logger.info(f"Order {order_id} and its details saved to database")
                    return order_id  # Return the generated id for use in OrderHandler
        except psycopg2.Error as e:
            logger.error(f"Database error while saving order {order_data.get('customer_id', 'unknown')}: {e}", exc_info=True)
            raise # Re-raise the exception after logging
        except Exception as e:
            logger.error(f"Unexpected error while saving order {order_data.get('customer_id', 'unknown')}: {e}", exc_info=True)
            raise # Re-raise the exception after logging
            
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
                        WHERE id = %s
                        RETURNING id
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
        """Save a new complaint to the whatsapp_complaint_details table and return the new ref_id."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    query = """
                        INSERT INTO whatsapp_complaint_details (
                            merchant_details_id, complaint_categories, complaint_text, 
                            timestamp, channel, user_name, user_id
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING ref_id
                    """
                    merchant_id = getattr(self.config, 'MERCHANT_ID', None)
                    if not merchant_id:
                        logger.error("MERCHANT_ID is not set in config, cannot save complaint.")
                        return None
                    
                    # Ensure timestamp and channel are in the data dictionary if they aren't
                    complaint_data.setdefault("timestamp", datetime.datetime.now(datetime.timezone.utc))
                    complaint_data.setdefault("channel", "whatsapp")

                    cur.execute(query, (
                        merchant_id,
                        complaint_data.get("complaint_categories", ""),
                        complaint_data.get("complaint_text"),
                        complaint_data.get("timestamp"),
                        complaint_data.get("channel"),
                        complaint_data.get("user_name"),
                        complaint_data.get("user_id")
                    ))
                    complaint_ref_id = cur.fetchone()[0]
                    conn.commit()
                    logger.info(f"Complaint {complaint_ref_id} saved to database")
                    return complaint_ref_id
        except psycopg2.Error as e:
            logger.error(f"Database error while saving complaint: {e}", exc_info=True)
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
                    # Query whatsapp_orders by customer_id
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

                    # Fallback: Query whatsapp_user_details by user_number
                    logger.debug(f"No address found in whatsapp_orders for phone number {phone_number}. Trying whatsapp_user_details (user_number).")
                    query = """
                        SELECT address, address2, address3
                        FROM whatsapp_user_details
                        WHERE user_number = %s
                        LIMIT 1
                    """
                    cur.execute(query, (phone_number,))
                    result = cur.fetchone()
                    if result:
                        if result.get('address'):
                            logger.debug(f"Found primary address '{result['address']}' for phone number {phone_number} in whatsapp_user_details")
                            return result['address']
                        elif result.get('address2'):
                            logger.debug(f"Found secondary address '{result['address2']}' for phone number {phone_number} in whatsapp_user_details")
                            return result['address2']
                        elif result.get('address3'):
                            logger.debug(f"Found tertiary address '{result['address3']}' for phone number {phone_number} in whatsapp_user_details")
                            return result['address3']

                    # Final fallback: Query whatsapp_user_details by user_id
                    logger.debug(f"No address found in whatsapp_user_details (user_number). Trying user_id.")
                    query = """
                        SELECT address, address2, address3
                        FROM whatsapp_user_details
                        WHERE user_id = %s
                        LIMIT 1
                    """
                    cur.execute(query, (phone_number,))
                    result = cur.fetchone()
                    if result:
                        if result.get('address'):
                            logger.debug(f"Found primary address '{result['address']}' for phone number {phone_number} in whatsapp_user_details (user_id)")
                            return result['address']
                        elif result.get('address2'):
                            logger.debug(f"Found secondary address '{result['address2']}' for phone number {phone_number} in whatsapp_user_details (user_id)")
                            return result['address2']
                        elif result.get('address3'):
                            logger.debug(f"Found tertiary address '{result['address3']}' for phone number {phone_number} in whatsapp_user_details (user_id)")
                            return result['address3']

                    logger.debug(f"No address found for phone number {phone_number} in either whatsapp_orders or whatsapp_user_details")
                    return None
        except psycopg2.Error as e:
            logger.error(f"Database error while fetching address for {phone_number}: {e}", exc_info=True)
            logger.debug(f"Database connection parameters: {self.db_params}")
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
                            id, merchant_details_id, customer_id,
                            business_type_id, address, status, total_amount,
                            payment_reference, payment_method_type, timestamp,
                            timestamp_enddate, dateadded
                        FROM whatsapp_orders
                        WHERE payment_reference = %s
                    """
                    cur.execute(query, (payment_reference,))
                    result = cur.fetchone()
                    if result:
                        order_data = dict(result)
                        order_data['total_amount'] = float(order_data['total_amount'])
                        order_data['order_id'] = str(order_data.pop('id'))  # Map id to order_id for compatibility
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

    # --- New Methods for Leads Management ---

    def create_or_update_lead(self, lead_data: Union[Lead, Dict]) -> bool:
        """
        Creates a new lead or updates an existing one in the whatsapp_leads table.
        This method uses ON CONFLICT to handle both creation and updates efficiently.
        """
        if isinstance(lead_data, Lead):
            data = lead_data.to_dict()
        else:
            data = lead_data

        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    query = """
                        INSERT INTO whatsapp_leads (
                            merchant_details_id, user_id, user_name, phone_number,
                            source, first_contact, last_interaction,
                            interaction_count, status, has_added_to_cart,
                            has_placed_order, total_cart_value, conversion_stage,
                            final_order_value, converted_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (phone_number) DO UPDATE SET
                            user_name = EXCLUDED.user_name,
                            last_interaction = EXCLUDED.last_interaction,
                            interaction_count = whatsapp_leads.interaction_count + 1,
                            status = EXCLUDED.status,
                            has_added_to_cart = EXCLUDED.has_added_to_cart,
                            has_placed_order = EXCLUDED.has_placed_order,
                            total_cart_value = EXCLUDED.total_cart_value,
                            conversion_stage = EXCLUDED.conversion_stage,
                            final_order_value = EXCLUDED.final_order_value,
                            converted_at = EXCLUDED.converted_at
                    """
                    cur.execute(query, (
                        data.get('merchant_details_id'),
                        data.get('user_id'),
                        data.get('user_name'),
                        data.get('phone_number'),
                        data.get('source'),
                        data.get('first_contact'),
                        data.get('last_interaction'),
                        data.get('interaction_count'),
                        data.get('status'),
                        data.get('has_added_to_cart'),
                        data.get('has_placed_order'),
                        data.get('total_cart_value'),
                        data.get('conversion_stage'),
                        data.get('final_order_value'),
                        data.get('converted_at')
                    ))
                    conn.commit()
                    logger.info(f"Lead details for {data.get('phone_number')} saved/updated in database.")
                    return True
        except psycopg2.Error as e:
            logger.error(f"Database error while saving/updating lead for {data.get('phone_number')}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error while saving/updating lead for {data.get('phone_number')}: {e}", exc_info=True)
            return False

    def get_lead_by_phone_number(self, phone_number: str) -> Optional[Dict]:
        """Retrieves lead data by phone number from the whatsapp_leads table."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT 
                            merchant_details_id, user_id, user_name, phone_number,
                            source, first_contact, last_interaction,
                            interaction_count, status, has_added_to_cart,
                            has_placed_order, total_cart_value, conversion_stage,
                            final_order_value, converted_at
                        FROM whatsapp_leads
                        WHERE phone_number = %s
                    """
                    cur.execute(query, (phone_number,))
                    result = cur.fetchone()
                    if result:
                        logger.debug(f"Found lead for phone number {phone_number}")
                        # Convert Numeric types to float for consistency
                        result['total_cart_value'] = float(result['total_cart_value'])
                        result['final_order_value'] = float(result['final_order_value'])
                        return dict(result)
                    logger.debug(f"No lead found for phone number {phone_number}")
                    return None
        except psycopg2.Error as e:
            logger.error(f"Database error while fetching lead for {phone_number}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error while fetching lead for {phone_number}: {e}", exc_info=True)
            return None

    def get_abandoned_carts(self, hours_ago: int = 24) -> List[Dict]:
        """
        Retrieves leads with abandoned carts from the whatsapp_leads table.
        An abandoned cart is a lead that has 'has_added_to_cart' = TRUE,
        'has_placed_order' = FALSE, and a last_interaction time older than 'hours_ago'.
        """
        abandoned_threshold = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_ago)
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT
                            merchant_details_id, user_id, user_name, phone_number,
                            total_cart_value, last_interaction, conversion_stage
                        FROM whatsapp_leads
                        WHERE has_added_to_cart = TRUE
                          AND has_placed_order = FALSE
                          AND last_interaction < %s
                    """
                    cur.execute(query, (abandoned_threshold,))
                    results = cur.fetchall()
                    
                    abandoned_carts = []
                    for row in results:
                        cart_data = dict(row)
                        # Convert numeric types
                        cart_data['total_cart_value'] = float(cart_data['total_cart_value'])
                        abandoned_carts.append(cart_data)
                        
                    logger.info(f"Found {len(abandoned_carts)} abandoned carts older than {hours_ago} hours.")
                    return abandoned_carts
        except psycopg2.Error as e:
            logger.error(f"Database error while fetching abandoned carts: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"Unexpected error while fetching abandoned carts: {e}", exc_info=True)
            return []

    def get_lead_analytics(self) -> Dict[str, Any]:
        """
        Retrieves a summary of lead analytics from the whatsapp_leads table.
        """
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Total leads
                    cur.execute("SELECT COUNT(*) AS total_leads FROM whatsapp_leads;")
                    total_leads = cur.fetchone()['total_leads']

                    # New leads (status = 'new_lead')
                    cur.execute("SELECT COUNT(*) AS new_leads FROM whatsapp_leads WHERE status = 'new_lead';")
                    new_leads = cur.fetchone()['new_leads']

                    # Converted leads (status = 'converted')
                    cur.execute("SELECT COUNT(*) AS converted_leads FROM whatsapp_leads WHERE has_placed_order = TRUE;")
                    converted_leads = cur.fetchone()['converted_leads']

                    # Abandoned carts
                    cur.execute("SELECT COUNT(*) AS abandoned_carts FROM whatsapp_leads WHERE has_added_to_cart = TRUE AND has_placed_order = FALSE;")
                    abandoned_carts = cur.fetchone()['abandoned_carts']
                    
                    # Total conversion value
                    cur.execute("SELECT SUM(final_order_value) AS total_revenue FROM whatsapp_leads WHERE has_placed_order = TRUE;")
                    total_revenue_result = cur.fetchone()['total_revenue']
                    total_revenue = float(total_revenue_result) if total_revenue_result else 0.0

                    return {
                        'total_leads': total_leads,
                        'new_leads': new_leads,
                        'converted_leads': converted_leads,
                        'abandoned_carts': abandoned_carts,
                        'total_revenue': total_revenue
                    }
        except psycopg2.Error as e:
            logger.error(f"Database error while fetching lead analytics: {e}", exc_info=True)
            return {}
        except Exception as e:
            logger.error(f"Unexpected error while fetching lead analytics: {e}", exc_info=True)
            return {}