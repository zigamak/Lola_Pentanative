import logging
import os
import json
from typing import Dict, List
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

class ProductSyncHandler:
    """Handles syncing product data from PostgreSQL database to a JSON file."""

    def __init__(self, config):
        self.config = config
        self.db_params = {
            'dbname': self.config.DB_NAME,
            'user': self.config.DB_USER,
            'password': self.config.DB_PASSWORD,
            'host': self.config.DB_HOST,
            'port': self.config.DB_PORT
        }
        self.json_file_path = self.config.PRODUCTS_FILE
        self._ensure_directory_exists()

    def _ensure_directory_exists(self):
        """Ensures the directory for the JSON file exists."""
        directory = os.path.dirname(self.json_file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")

    def sync_products_to_json(self) -> bool:
        """Fetches products from the database and saves them to products.json."""
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
                            quantity
                        FROM whatsapp_merchant_product_inventory
                        WHERE availability_status = true
                    """
                    cur.execute(query)
                    rows = cur.fetchall()

                    menu_data: Dict[str, List[Dict]] = {}
                    for row in rows:
                        category = row['product_category'] or 'Uncategorized'
                        if category not in menu_data:
                            menu_data[category] = []

                        # Corrected Line: Handle NoneType for 'price'
                        price_value = float(row['price']) if row['price'] is not None else 0.0

                        item = {
                            'id': str(row['id']),
                            'name': row['product_name'],
                            'variant': row['variant_name'],
                            'price': price_value, # Use the handled price_value
                            'currency': row['currency'],
                            'availability_status': row['availability_status'],
                            'description': row['description'],
                            'quantity': row['quantity']
                        }
                        menu_data[category].append(item)

                    try:
                        with open(self.json_file_path, 'w', encoding='utf-8') as f:
                            json.dump(menu_data, f, indent=2)
                        logger.info(f"Successfully synced {len(rows)} products to {self.json_file_path}")
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