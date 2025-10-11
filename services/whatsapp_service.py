import requests
import logging
import sys
import io
from typing import Dict, Optional, List

# Configure logging with UTF-8 encoding
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
if sys.platform.startswith('win'):
    handler.stream = io.TextIOWrapper(handler.stream.buffer, encoding='utf-8', errors='replace')
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
        logger.debug("WhatsAppService initialized with phone_number_id: %s", config.WHATSAPP_PHONE_NUMBER_ID)
    
    def send_message(self, payload: Dict) -> Optional[Dict]:
        """Send a message to the WhatsApp Business API."""
        try:
            # Validate payload before sending
            if not payload or not isinstance(payload, dict):
                logger.error("Payload is None or not a dictionary: %s", payload)
                return None
            
            if "to" not in payload:
                logger.error("Missing 'to' parameter in payload: %s", payload)
                return None
            
            if "type" not in payload:
                logger.error("Missing 'type' parameter in payload: %s", payload)
                return None
            
            if "messaging_product" not in payload:
                payload["messaging_product"] = "whatsapp"
                logger.warning("Added missing 'messaging_product' to payload: %s", payload)
            
            logger.info("Sending WhatsApp payload to %s: %s", payload.get("to"), payload)
            
            response = requests.post(self.base_url, json=payload, headers=self.headers)
            response.raise_for_status()
            logger.info("WhatsApp API response: %s - %s", response.status_code, response.text)
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            logger.error("HTTP error sending WhatsApp message: %s - Response: %s", http_err, response.text if response else "No response")
            return None
        except requests.RequestException as e:
            logger.error("Request error sending WhatsApp message: %s", e)
            return None
        except Exception as e:
            logger.error("Unexpected error in send_message: %s", e, exc_info=True)
            return None
    
    def _clean_incoming_payload(self, payload: Dict) -> Dict:
        """
        Clean and extract relevant data from an INCOMING WhatsApp webhook payload.
        This is for processing received messages, not for sending.
        """
        try:
            clean_payload = payload.copy() if isinstance(payload, dict) else {}
            
            if not clean_payload.get("to") and payload.get("contacts"):
                try:
                    contacts = payload.get("contacts", [])
                    if contacts and isinstance(contacts, list) and len(contacts) > 0:
                        wa_id = contacts[0].get("wa_id") or contacts[0].get("input")
                        if wa_id:
                            clean_payload["to"] = wa_id
                            logger.info("Recovered 'to' field from contacts: %s", wa_id)
                except Exception as e:
                    logger.error("Failed to recover 'to' from contacts: %s", e)
            
            unwanted_fields = ['contacts', 'messages', 'input', 'wa_id', 'status']
            for field in unwanted_fields:
                clean_payload.pop(field, None)
            
            return clean_payload
        except Exception as e:
            logger.error("Error cleaning incoming payload: %s, original payload: %s", e, payload)
            return {}

    def create_text_message(self, to: str, text: str) -> Optional[Dict]:
        """Create and send a text message."""
        try:
            if not to or not text:
                logger.error("Invalid parameters: to='%s', text='%s'", to, text)
                return None
            
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual", 
                "to": str(to),
                "type": "text",
                "text": {"body": str(text)}
            }
            logger.debug("Created text message payload for %s", to)
            return self.send_message(payload)
        except Exception as e:
            logger.error("Error creating text message for %s: %s", to, e, exc_info=True)
            return None
    
    def create_button_message_payload(self, to: str, text: str, buttons: List[Dict]) -> Optional[Dict]:
        """Creates a button message payload without sending."""
        try:
            if not to or not text or not buttons:
                logger.error("Invalid parameters: to='%s', text='%s', buttons='%s'", to, text, buttons)
                return None
            
            if not isinstance(buttons, list) or len(buttons) > 3:
                logger.error("Invalid buttons format or too many buttons: %s", buttons)
                return None
            
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": str(to),
                "type": "interactive",
                "interactive": {
                    "type": "button", 
                    "body": {"text": str(text)},
                    "action": {"buttons": buttons}
                }
            }
            logger.debug("Created button message payload for %s", to)
            return payload
        except Exception as e:
            logger.error("Error creating button message payload for %s: %s", to, e, exc_info=True)
            return None

    def send_button_message(self, to: str, text: str, buttons: List[Dict]) -> Optional[Dict]:
        """Sends a button message."""
        payload = self.create_button_message_payload(to, text, buttons)
        if not payload:
            return self.create_text_message(to, text)
        return self.send_message(payload)
    
    def create_button_message(self, to: str, text: str, buttons: List[Dict]) -> Optional[Dict]:
        """Creates and sends a button message (alias for send_button_message for compatibility)."""
        logger.debug("Creating button message for %s with text: %s, buttons: %s", to, text, buttons)
        return self.send_button_message(to, text, buttons)
    
    def create_list_message(self, to: str, text: str, button_text: str, sections: List[Dict]) -> Optional[Dict]:
        """Create and send a list message."""
        try:
            if not to or not text or not button_text or not sections:
                logger.error("Invalid parameters: to='%s', text='%s', button_text='%s', sections='%s'", to, text, button_text, sections)
                return None
            
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": str(to),
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": str(text)},
                    "action": {"button": str(button_text), "sections": sections}
                }
            }
            logger.debug("Created list message payload for %s", to)
            return self.send_message(payload)
        except Exception as e:
            logger.error("Error creating list message for %s: %s", to, e, exc_info=True)
            return self.create_text_message(to, text)
    
    def create_image_message(self, to: str, image_url: str, caption: str = "") -> Optional[Dict]:
        """Creates an image message payload without sending."""
        try:
            if not to or not image_url:
                logger.error("Invalid parameters for image message: to='%s', image_url='%s'", to, image_url)
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
                payload["image"]["caption"] = str(caption)
            
            logger.debug("Created image message payload for %s", to)
            return payload
        except Exception as e:
            logger.error("Error creating image message payload for %s: %s", to, e, exc_info=True)
            return None

    def send_image_message(self, to: str, image_url: str, caption: str = "") -> Optional[Dict]:
        """Sends an image message with an optional caption."""
        try:
            payload = self.create_image_message(to, image_url, caption)
            if not payload:
                return None
            
            return self.send_message(payload)
        except Exception as e:
            logger.error("Error sending image message for %s: %s", to, e, exc_info=True)
            return None

    def send_image_with_buttons(self, to: str, image_url: str, text: str, buttons: List[Dict], button_prompt: str = "") -> Optional[Dict]:
        """
        Sends an image message followed by a button message.
        The image message uses the provided text as the caption.
        The button message uses button_prompt if provided, otherwise falls back to text.
        """
        try:
            # 1. Send the image message
            image_response = self.send_image_message(to, image_url, caption=text)
            
            # 2. Check if the image sent successfully before sending the buttons
            if not image_response:
                logger.error(f"Failed to send image to {to}. Aborting button message.")
                return None

            # 3. Send the button message with button_prompt or fallback to text
            button_text = button_prompt if button_prompt else text
            return self.send_button_message(to, button_text, buttons)
            
        except Exception as e:
            logger.error("Error sending image with buttons for %s: %s", to, e, exc_info=True)
            # Fallback to a simple text message in case of failure
            return self.create_text_message(to, text)

    def send_timeout_message(self, session_id: str) -> Optional[Dict]:
        """Send timeout message to user."""
        try:
            if not session_id:
                logger.error("Invalid session_id for timeout message: %s", session_id)
                return None
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": str(session_id),
                "type": "text",
                "text": {"body": "Your session has timed out due to inactivity. Please send a message to start a new interaction."}
            }
            logger.debug("Created timeout message payload for %s", session_id)
            return self.send_message(payload)
        except Exception as e:
            logger.error("Error sending timeout message for %s: %s", session_id, e, exc_info=True)
            return None
    
    def send_template_message(self, to: str, template_name: str, language_code: str, components: List[Dict]) -> Optional[Dict]:
        """Sends a WhatsApp template message."""
        try:
            if not to or not template_name or not language_code or not components:
                logger.error("Invalid parameters: to='%s', template_name='%s', language_code='%s', components='%s'", to, template_name, language_code, components)
                return None
            
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": str(to),
                "type": "template",
                "template": {
                    "name": str(template_name),
                    "language": {"code": str(language_code)},
                    "components": components
                }
            }
            logger.debug("Created template message payload for %s", to)
            return self.send_message(payload)
        except Exception as e:
            logger.error("Error creating template message for %s: %s", to, e, exc_info=True)
            return self.create_text_message(to, "⚠️ Error sending template message. Please contact support.")

    def validate_contact(self, phone_number: str) -> Optional[Dict]:
        """Validate a phone number using the WhatsApp Business API."""
        try:
            if not phone_number:
                logger.error("Invalid phone_number for contact validation: %s", phone_number)
                return None
            payload = {
                "messaging_product": "whatsapp",
                "contacts": [{"phone_number": str(phone_number)}]
            }
            url = f"https://graph.facebook.com/v17.0/{self.config.WHATSAPP_PHONE_NUMBER_ID}/contacts"
            logger.debug("Validating contact with payload: %s", payload)
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            response_data = response.json()
            logger.info("Contact validation response: %s", response_data)
            return response_data
        except requests.exceptions.HTTPError as http_err:
            logger.error("HTTP error validating contact %s: %s - Response: %s", phone_number, http_err, response.text if response else "No response")
            return None
        except requests.RequestException as e:
            logger.error("Request error validating contact %s: %s", phone_number, e)
            return None
        except Exception as e:
            logger.error("Unexpected error validating contact %s: %s", phone_number, e, exc_info=True)
            return None
        
    