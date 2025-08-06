import json
import logging
import hmac
import hashlib
from utils.session_manager import SessionManager
from utils.data_manager import DataManager
from services.whatsapp_service import WhatsAppService
from services.payment_service import PaymentService
from services.location_service import LocationService
from handlers.message_processor import MessageProcessor
from handlers.payment_handler import PaymentHandler

logger = logging.getLogger(__name__)

class WebhookHandler:
    """Handles WhatsApp and Paystack webhook requests."""
    
    def __init__(self, config):
        self.config = config
        self.session_manager = SessionManager(config.SESSION_TIMEOUT)
        self.data_manager = DataManager(config)
        self.whatsapp_service = WhatsAppService(config)
        self.payment_service = PaymentService(config)
        self.location_service = LocationService(config)
        self.message_processor = MessageProcessor(
            config, 
            self.session_manager, 
            self.data_manager, 
            self.whatsapp_service, 
            self.payment_service,
            self.location_service
        )
        self.payment_handler = PaymentHandler(
            config,
            self.session_manager,
            self.data_manager,
            self.whatsapp_service,
            self.payment_service,
            self.location_service
        )
    
    def verify_webhook(self, request):
        """Handle WhatsApp webhook verification."""
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and token == self.config.VERIFY_TOKEN:
            logger.info("WhatsApp webhook verified successfully!")
            return challenge, 200
        
        logger.error("WhatsApp webhook verification failed. Mismatched tokens or mode.")
        return "Verification failed", 403
    
    def handle_webhook(self, request):
        """Handle incoming webhook messages (WhatsApp or Paystack)."""
        try:
            # Check if this is a Paystack webhook based on the presence of the X-Paystack-Signature header
            paystack_signature = request.headers.get('X-Paystack-Signature')
            if paystack_signature:
                return self._handle_paystack_webhook(request)
            
            # Handle WhatsApp webhook
            data = request.get_json()
            if not data:
                logger.error("No JSON data received in webhook POST request.")
                return {"status": "error", "message": "No data received"}, 400

            logger.debug(f"Received WhatsApp webhook data: {json.dumps(data, indent=2)}")

            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])

                    if not messages:
                        continue

                    message = messages[0]
                    phone_number = message.get("from")

                    if not phone_number:
                        logger.error("No 'from' phone number found in the message.")
                        continue

                    # Extract user name from contacts
                    user_name = None
                    contacts = value.get("contacts", [])
                    if contacts:
                        user_name = contacts[0].get("profile", {}).get("name")

                    # Extract message text and location based on message type
                    message_data = self._extract_message_data(message)

                    if message_data:
                        logger.info(f"Processing message from {phone_number} (User: {user_name or 'Unknown'}): {message_data}")
                        response_payload = self.message_processor.process_message(message_data, phone_number, user_name)
                        if response_payload:
                            self.whatsapp_service.send_message(response_payload)
                    else:
                        logger.warning(f"No valid message data extracted for {phone_number}. Message type: {message.get('type')}")

            return {"status": "success"}, 200
        except Exception as e:
            logger.error(f"Error processing webhook: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}, 500
    
    def _handle_paystack_webhook(self, request):
        """Handle Paystack webhook requests."""
        try:
            # Verify Paystack signature
            paystack_secret_key = self.config.PAYSTACK_SECRET_KEY
            signature = request.headers.get('X-Paystack-Signature')
            body = request.get_data()

            # Compute HMAC SHA512 signature
            computed_signature = hmac.new(
                paystack_secret_key.encode('utf-8'),
                body,
                hashlib.sha512
            ).hexdigest()

            if not hmac.compare_digest(signature, computed_signature):
                logger.error("Invalid Paystack webhook signature")
                return {"status": "error", "message": "Invalid signature"}, 401

            # Parse webhook data
            webhook_data = request.get_json()
            if not webhook_data:
                logger.error("No JSON data received in Paystack webhook POST request.")
                return {"status": "error", "message": "No data received"}, 400

            logger.debug(f"Received Paystack webhook data: {json.dumps(webhook_data, indent=2)}")

            # Pass the webhook data to PaymentHandler
            self.payment_handler.handle_payment_webhook(
                webhook_data=webhook_data,
                session_manager=self.session_manager,
                whatsapp_service=self.whatsapp_service
            )

            return {"status": "success"}, 200
        except Exception as e:
            logger.error(f"Error processing Paystack webhook: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}, 500
    
    def _extract_message_data(self, message):
        """Extract text and location from different message types."""
        message_type = message.get("type")
        
        if message_type == "text":
            return {"type": "text", "text": message["text"]["body"]}
        elif message_type == "button":
            return {"type": "text", "text": message["button"]["payload"]}
        elif message_type == "interactive":
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                return {"type": "text", "text": interactive["button_reply"]["id"]}
            elif interactive.get("type") == "list_reply":
                message_text = interactive["list_reply"]["id"]
                logger.info(f"List reply received: id='{message_text}', title='{interactive['list_reply']['title']}'")
                return {"type": "text", "text": message_text}
        elif message_type == "location":
            location = message.get("location", {})
            return {
                "type": "location",
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "name": location.get("name"),
                "address": location.get("address")
            }
        
        return None