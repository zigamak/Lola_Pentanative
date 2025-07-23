import json
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from config import Config
from handlers.webhook_handler import WebhookHandler
from handlers.payment_handler import PaymentHandler
from handlers.product_sync_handler import ProductSyncHandler
from utils.session_manager import SessionManager
from utils.data_manager import DataManager
from services.whatsapp_service import WhatsAppService
from services.payment_service import PaymentService
from services.location_service import LocationService

# Load environment variables from .env file
load_dotenv()

# Configure logging for the application
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize the Flask application
app = Flask(__name__)

# Initialize the configuration object
config = Config()

# --- Initialize core service objects ---
try:
    session_manager = SessionManager(config.SESSION_TIMEOUT)
    data_manager = DataManager(config)
    whatsapp_service = WhatsAppService(config)
    payment_service = PaymentService(config)
    location_service = LocationService(config)
    product_sync_handler = ProductSyncHandler(config)
    # Trigger initial sync on startup
    success = product_sync_handler.sync_products_to_json()
    if success:
        logger.info("Initial product sync successful on startup")
    else:
        logger.warning("Initial product sync failed on startup")
except Exception as e:
    logger.error(f"Error initializing a core service: {e}", exc_info=True)
    exit(1)

# Initialize the WebhookHandler
webhook_handler = WebhookHandler(config)

# Initialize the PaymentHandler
try:
    payment_handler = PaymentHandler(
        config,
        session_manager,
        data_manager,
        whatsapp_service,
        payment_service,
        location_service
    )
except Exception as e:
    logger.error(f"Error initializing PaymentHandler: {e}", exc_info=True)
    exit(1)

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """
    Endpoint for WhatsApp webhook verification.
    Handles the GET request from Meta to verify the webhook URL.
    """
    return webhook_handler.verify_webhook(request)

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Endpoint for receiving incoming WhatsApp messages.
    Handles the POST request containing message data from WhatsApp.
    """
    return webhook_handler.handle_webhook(request)

@app.route("/payment-callback", methods=["GET", "POST"])
def payment_callback():
    """
    Endpoint for Paystack payment callbacks/redirects.
    Receives payment success/failure notifications from Paystack.
    """
    return payment_handler.handle_payment_callback(request)

@app.route("/sync-products", methods=["POST"])
def sync_products():
    """
    Endpoint to trigger syncing of product data from PostgreSQL to products.json.
    Requires an API key in the Authorization header for security.
    """
    try:
        expected_api_key = config.SYNC_API_KEY
        if not request.headers.get('Authorization') == f'Bearer {expected_api_key}':
            logger.warning("Unauthorized attempt to access /sync-products endpoint")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        success = product_sync_handler.sync_products_to_json()
        if success:
            logger.info("Products synced successfully via API")
            return jsonify({"status": "success", "message": "Products synced successfully"}), 200
        else:
            logger.error("Failed to sync products via API")
            return jsonify({"status": "error", "message": "Failed to sync products"}), 500
    except Exception as e:
        logger.error(f"Error syncing products via API: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    # This block will now primarily contain informational messages.
    # Gunicorn will be used to run the 'app' Flask instance directly.
    logger.info("Preparing to start WhatsApp bot server with Gunicorn...")
    logger.info(f"Webhook URL: {config.CALLBACK_BASE_URL}/webhook")
    logger.info(f"Payment Callback: {config.CALLBACK_BASE_URL}/payment-callback")
    logger.info(f"Product Sync Endpoint: {config.CALLBACK_BASE_URL}/sync-products")
    logger.info("Logs: Check bot.log file for detailed logs")
    logger.info("To run this application, use Gunicorn from your terminal:")
    logger.info(f"gunicorn -w 4 -b 0.0.0.0:{config.APP_PORT} app:app")

