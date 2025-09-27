import logging
import os
import json
import time
from typing import Dict, List
import psycopg2
from psycopg2.extras import RealDictCursor
import threading
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging with UTF-8 encoding
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

class ProductSyncHandler:
    """Handles syncing product data for a specific merchant from PostgreSQL database to a JSON file."""

    def __init__(self, config):
        self.config = config
        self.db_params = {
            'dbname': self.config.DB_NAME,
            'user': self.config.DB_USER,
            'password': self.config.DB_PASSWORD,
            'host': self.config.DB_HOST,
            'port': self.config.DB_PORT
        }
        self.merchant_id = self.config.MERCHANT_ID
        self.json_file_path = self.config.PRODUCTS_FILE
        self.sync_interval = int(os.getenv('PRODUCT_SYNC_INTERVAL_MINUTES', 5)) * 60  # Sync interval in seconds
        self._ensure_directory_exists()
        self._stop_event = threading.Event()
        self._sync_thread = None

    def _ensure_directory_exists(self):
        """Ensures the directory for the JSON file exists."""
        directory = os.path.dirname(self.json_file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")

    def _sync_products_loop(self):
        """The main loop for syncing products at a set interval."""
        while not self._stop_event.is_set():
            self.sync_products_to_json()
            # Wait for the next sync interval or until the stop event is set
            self._stop_event.wait(self.sync_interval)
        logger.info("Product sync thread stopped.")

    def start_sync(self):
        """Starts the product sync thread."""
        if self._sync_thread is None or not self._sync_thread.is_alive():
            logger.info(f"Starting product sync thread. Sync interval: {self.sync_interval/60} minutes.")
            self._sync_thread = threading.Thread(target=self._sync_products_loop)
            self._sync_thread.daemon = True  # Allows the thread to exit when the main program exits
            self._sync_thread.start()

    def stop_sync(self):
        """Stops the product sync thread."""
        if self._sync_thread and self._sync_thread.is_alive():
            logger.info("Stopping product sync thread...")
            self._stop_event.set()
            self._sync_thread.join()

    def sync_products_to_json(self) -> bool:
        """Fetches products for a specific merchant from the database and saves them to products.json."""
        logger.info(f"Initiating product sync for merchant {self.merchant_id}...")
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT
                            id,
                            merchant_details_id AS merchant_id,
                            product_name,
                            product_category,
                            variant_name,
                            price,
                            currency,
                            availability_status,
                            description,
                            date_created,
                            last_updated,
                            quantity,
                            channel,
                            food_share_pattern
                        FROM whatsapp_merchant_product_inventory
                        WHERE availability_status = true AND merchant_details_id = %s
                    """
                    cur.execute(query, (self.merchant_id,))
                    rows = cur.fetchall()

                    menu_data: Dict[str, List[Dict]] = {}
                    for row in rows:
                        category = row['product_category'] or 'Uncategorized'
                        if category not in menu_data:
                            menu_data[category] = []
                        
                        item = {
                            'id': str(row['id']),
                            'name': row['product_name'],
                            'variant': row['variant_name'],
                            'price': float(row['price']) if row['price'] is not None else 0.0,
                            'currency': row['currency'],
                            'availability_status': row['availability_status'],
                            'description': row['description'],
                            'quantity': row['quantity'],
                            'channel': row['channel'],
                            'food_share_pattern': row['food_share_pattern']
                        }
                        menu_data[category].append(item)

                    try:
                        with open(self.json_file_path, 'w', encoding='utf-8') as f:
                            json.dump(menu_data, f, indent=2)
                        logger.info(f"Successfully synced {len(rows)} products for merchant {self.merchant_id} to {self.json_file_path}")
                        return True
                    except Exception as e:
                        logger.error(f"Error writing to {self.json_file_path}: {e}")
                        return False

        except psycopg2.Error as e:
            logger.error(f"Database error while syncing products: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error while syncing products: {e}")
            return False