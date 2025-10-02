import os
from dotenv import load_dotenv
import logging

load_dotenv()

class Config:
    def __init__(self):
        # Database configuration
        self.DB_URL = os.getenv('DB_URL')
        self.DB_HOST = os.getenv('DB_HOST')
        self.DB_PORT = os.getenv('DB_PORT')
        self.DB_NAME = os.getenv('DB_NAME')
        self.DB_USER = os.getenv('DB_USER')
        self.DB_PASSWORD = os.getenv('DB_PASSWORD')
        self.DB_SSLMODE = os.getenv('DB_SSLMODE')

        # WhatsApp configuration
        self.WHATSAPP_ACCESS_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN')
        self.WHATSAPP_PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
        self.VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
        self.APP_SECRET = os.getenv('APP_SECRET') 

        # Payment configuration
        self.PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY')
        self.PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY')
        self.SUBACCOUNT_CODE = "ACCT_iwv6csej0ra4k7g"
        
        #self.SUBACCOUNT_CODE = "ACCT_u9knhyzn5eq4iop"
        self.SUBACCOUNT_PERCENTAGE = 1
        self.MERCHANT_PHONE_NUMBERS = [
            "2348096500003",
        "2347082345056",
        "2348055614455",
        "2348129750653"]
      
        
        
        
        # Merchant ID from environment variable
        self.MERCHANT_ID = os.getenv('MERCHANT_ID', '20')
        
        # Other services
        self.Maps_API_KEY = os.getenv('Maps_API_KEY')
        self.AZURE_API_KEY = os.getenv('AZURE_API_KEY')
        self.AZURE_ENDPOINT = os.getenv('AZURE_ENDPOINT')
        self.AZURE_DEPLOYMENT_NAME = os.getenv('AZURE_DEPLOYMENT_NAME')
        self.AZURE_API_VERSION = os.getenv('AZURE_API_VERSION')
        
        
        
        # Feature flags
        self.ENABLE_AI_FEATURES = os.getenv('ENABLE_AI_FEATURES', 'false').lower() == 'true'
        self.ENABLE_LOCATION_FEATURES = os.getenv('ENABLE_LOCATION_FEATURES', 'false').lower() == 'true'

        # Flask configuration
        self.FLASK_ENV = os.getenv('FLASK_ENV', 'development')
        self.FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
        self.APP_PORT = int(os.getenv('APP_PORT', 5000))
        self.CALLBACK_BASE_URL = os.getenv('CALLBACK_BASE_URL')

        # File paths
        self.DATA_DIR = os.getenv('DATA_DIR', 'data')
        self.LOGS_DIR = os.getenv('LOGS_DIR', 'logs')

        self.ORDER_DETAILS_FILE = os.getenv('ORDER_DETAILS_FILE', os.path.join(self.DATA_DIR, 'orders.json'))
        self.ENQUIRY_DETAILS_FILE = os.getenv('ENQUIRY_DETAILS_FILE', os.path.join(self.DATA_DIR, 'enquiries.json'))
        self.COMPLAINT_DETAILS_FILE = os.getenv('COMPLAINT_DETAILS_FILE', os.path.join(self.DATA_DIR, 'complaints.json'))
        self.LEAD_TRACKER_DATA_FILE = os.getenv('LEAD_TRACKER_DATA_FILE', os.path.join(self.DATA_DIR, 'leads.json'))

        # Renamed PRODUCT_FILE to PRODUCTS_FILE for consistency with DataManager
        self.PRODUCTS_FILE = os.getenv('PRODUCTS_FILE', os.path.join(self.DATA_DIR, 'products.json'))

        # Session configuration
        self.SESSION_TIMEOUT = int(os.getenv('SESSION_TIMEOUT', 3600))  # 30 minutes default

# Define the configure_logging function
def configure_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # You can customize this further, e.g.,
    # logging.getLogger('werkzeug').setLevel(logging.ERROR) # Suppress Flask/Werkzeug access logs
    # file_handler = logging.FileHandler('app.log')
    # file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    # logging.getLogger().addHandler(file_handler)