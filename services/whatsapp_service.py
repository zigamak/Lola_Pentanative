import requests
import logging

# Configure logging with UTF-8 encoding
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
handler.stream.reconfigure(encoding='utf-8')  # Force UTF-8 encoding
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

class WhatsAppService:
    """Service for sending WhatsApp messages."""
    
    def __init__(self, config):
        self.config = config
        self.base_url = f"https://graph.facebook.com/v17.0/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"
        self.headers = {
            "Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
    
    def send_message(self, payload):
        """Send a message to the WhatsApp Business API."""
        try:
            # Validate payload has required fields
            if not payload:
                logger.error("Payload is None or empty")
                return None
                
            if not payload.get("to"):
                logger.error(f"Missing 'to' parameter in payload: {payload}")
                return None
                
            if not payload.get("type"):
                logger.error(f"Missing 'type' parameter in payload: {payload}")
                return None
            
            # Clean the payload to remove any unwanted fields
            clean_payload = self._clean_payload(payload)
            
            # Log the payload for debugging
            logger.info(f"Sending WhatsApp payload: {clean_payload}")
            
            # Ensure messaging_product is always present
            if "messaging_product" not in clean_payload:
                clean_payload["messaging_product"] = "whatsapp"
                logger.warning("Added missing messaging_product to payload")
                
            response = requests.post(self.base_url, json=clean_payload, headers=self.headers)
            response.raise_for_status()
            logger.info(f"WhatsApp API response: {response.status_code} - {response.text}")
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error sending WhatsApp message: {http_err} - {response.text}")
        except requests.RequestException as e:
            logger.error(f"Error sending WhatsApp message: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in send_message: {e}", exc_info=True)
        return None
    
    def _clean_payload(self, payload):
        """Clean payload to remove unwanted fields that might cause API errors."""
        try:
            # Create a copy to avoid modifying the original
            clean_payload = payload.copy() if isinstance(payload, dict) else payload
            
            if not isinstance(clean_payload, dict):
                logger.error(f"Payload is not a dictionary: {type(payload)} - {payload}")
                return {"messaging_product": "whatsapp"}  # Minimal fallback
            
            # Remove fields that shouldn't be in outgoing messages
            unwanted_fields = ['contacts', 'messages', 'input', 'wa_id']
            for field in unwanted_fields:
                if field in clean_payload:
                    logger.warning(f"Removing unwanted field '{field}' from payload")
                    del clean_payload[field]
            
            return clean_payload
        except Exception as e:
            logger.error(f"Error cleaning payload: {e}, payload: {payload}")
            return {"messaging_product": "whatsapp"}  # Minimal fallback
    
    def create_text_message(self, to, text):
        """Create and send a text message."""
        try:
            # Validate inputs
            if not to or not text:
                logger.error(f"Invalid parameters: to='{to}', text='{text}'")
                return None
                
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual", 
                "to": str(to),  # Ensure 'to' is a string
                "type": "text",
                "text": {"body": str(text)}  # Ensure 'text' is a string
            }
            logger.debug(f"Created text message payload for {to}: {payload}")
            return self.send_message(payload)
        except Exception as e:
            logger.error(f"Error creating text message for {to}: {e}", exc_info=True)
            return None
    
    def create_button_message(self, to, text, buttons):
        """Create and send a button message."""
        try:
            # Validate inputs
            if not to or not text or not buttons:
                logger.error(f"Invalid parameters: to='{to}', text='{text}', buttons='{buttons}'")
                return None
                
            # Validate buttons format
            if not isinstance(buttons, list) or len(buttons) > 3:
                logger.error(f"Invalid buttons format or too many buttons: {buttons}")
                # Fallback to text message
                return self.create_text_message(to, text)
            
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": str(to),  # Ensure 'to' is a string
                "type": "interactive",
                "interactive": {
                    "type": "button", 
                    "body": {"text": str(text)},  # Ensure 'text' is a string
                    "action": {"buttons": buttons}
                }
            }
            logger.debug(f"Created button message payload for {to}: {payload}")
            return self.send_message(payload)
        except Exception as e:
            logger.error(f"Error creating button message for {to}: {e}", exc_info=True)
            # Fallback to text message
            return self.create_text_message(to, text)
    
    def create_list_message(self, to, text, button_text, sections):
        """Create and send a list message."""
        try:
            # Validate inputs
            if not to or not text or not button_text or not sections:
                logger.error(f"Invalid parameters: to='{to}', text='{text}', button_text='{button_text}', sections='{sections}'")
                return None
                
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": str(to),  # Ensure 'to' is a string
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": str(text)},  # Ensure 'text' is a string
                    "action": {"button": str(button_text), "sections": sections}
                }
            }
            logger.debug(f"Created list message payload for {to}: {payload}")
            return self.send_message(payload)
        except Exception as e:
            logger.error(f"Error creating list message for {to}: {e}", exc_info=True)
            # Fallback to text message
            return self.create_text_message(to, text)
    
    def send_image_message(self, to: str, image_url: str, caption: str = "") -> dict:
        """
        Sends an image message with an optional caption.

        Args:
            to (str): The recipient's WhatsApp ID.
            image_url (str): The URL of the image to send.
            caption (str, optional): An optional caption for the image. Defaults to "".

        Returns:
            dict: The response from the WhatsApp API, or None if an error occurred.
        """
        try:
            if not to or not image_url:
                logger.error(f"Invalid parameters for image message: to='{to}', image_url='{image_url}'")
                return None

            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": str(to),
                "type": "image",
                "image": {
                    "link": image_url
                }
            }
            if caption:
                payload["image"]["caption"] = str(caption) # Ensure caption is a string
            
            logger.debug(f"Created image message payload for {to}: {payload}")
            return self.send_message(payload)
        except Exception as e:
            logger.error(f"Error creating image message for {to}: {e}", exc_info=True)
            return None

    def send_timeout_message(self, session_id):
        """Send timeout message to user."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": session_id,
            "type": "text",
            "text": {"body": "Your session has timed out due to inactivity. Please send a message to start a new interaction."}
        }
        return self.send_message(payload)
    
    def send_template_message(self, to: str, template_name: str, language_code: str, components: list) -> dict:
        """
        Sends a WhatsApp template message.

        Args:
            to (str): The recipient's WhatsApp ID.
            template_name (str): The name of the template to send.
            language_code (str): The language code for the template (e.g., 'en').
            components (list): List of component dictionaries for template parameters.

        Returns:
            dict: The response from the WhatsApp API, or None if an error occurred.
        """
        try:
            # Validate inputs
            if not to or not template_name or not language_code or not components:
                logger.error(f"Invalid parameters: to='{to}', template_name='{template_name}', language_code='{language_code}', components='{components}'")
                return None
                
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": str(to),  # Ensure 'to' is a string
                "type": "template",
                "template": {
                    "name": str(template_name),
                    "language": {"code": str(language_code)},
                    "components": components
                }
            }
            logger.debug(f"Created template message payload for {to}: {payload}")
            return self.send_message(payload)
        except Exception as e:
            logger.error(f"Error creating template message for {to}: {e}", exc_info=True)
            # Fallback to text message with error information
            return self.create_text_message(to, f"⚠️ Error sending template message. Please contact support.")