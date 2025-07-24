import logging
from flask import current_app, jsonify
import json
import requests
import re
from typing import Dict, Optional

# Import with fallback to handle different project structures
try:
    from app.services.python_service import generate_response
except ImportError:
    try:
        from ..services.python_service import generate_response
    except ImportError as e:
        logging.error(f"Failed to import generate_response: {e}")
        def generate_response(message_body: str, wa_id: str, name: str) -> str:
            """Fallback response generator if openai_service not available"""
            return f"Hi {name}! Our chatbot service is currently unavailable. Please try again later."


def log_http_response(response: requests.Response) -> None:
    """Log HTTP response details"""
    logging.info(f"Status: {response.status_code}")
    logging.info(f"Content-type: {response.headers.get('content-type')}")
    logging.info(f"Body: {response.text}")


def get_text_message_input(recipient: str, text: str) -> str:
    """Generate the JSON payload for a WhatsApp text message"""
    return json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text
        }
    })


def send_message(data: str) -> requests.Response:
    """Send message via WhatsApp API"""
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}"
    }

    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{current_app.config['PHONE_NUMBER_ID']}/messages"

    try:
        response = requests.post(
            url,
            data=data,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        log_http_response(response)
        return response
    except requests.Timeout:
        logging.error("Timeout occurred while sending message")
        return jsonify({
            "status": "error",
            "message": "Request timed out"
        }), 408
    except requests.RequestException as e:
        logging.error(f"Request failed due to: {e}")
        return jsonify({
            "status": "error",
            "message": "Failed to send message"
        }), 500


def process_text_for_whatsapp(text: str) -> str:
    """Format text for WhatsApp display"""
    # Remove brackets
    text = re.sub(r"\【.*?\】", "", text).strip()
    # Convert markdown bold (*text*) to WhatsApp bold (*text*)
    return re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)


def process_whatsapp_message(body: Dict) -> Optional[requests.Response]:
    """Process incoming WhatsApp message and send response"""
    try:
        # Extract message details
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        contacts = value["contacts"][0]
        messages = value["messages"][0]

        wa_id = contacts["wa_id"]
        name = contacts["profile"]["name"]
        message_body = messages["text"]["body"]

        # Generate and send response
        response = generate_response(message_body, wa_id, name)
        formatted_response = process_text_for_whatsapp(response)
        message_data = get_text_message_input(wa_id, formatted_response)
        
        return send_message(message_data)

    except KeyError as e:
        logging.error(f"Missing key in WhatsApp message: {e}")
        return None
    except Exception as e:
        logging.error(f"Error processing WhatsApp message: {e}")
        return None


def is_valid_whatsapp_message(body: Dict) -> bool:
    """Validate WhatsApp webhook message structure"""
    try:
        return all([
            body.get("object"),
            body.get("entry"),
            body["entry"][0].get("changes"),
            body["entry"][0]["changes"][0].get("value"),
            body["entry"][0]["changes"][0]["value"].get("messages"),
            body["entry"][0]["changes"][0]["value"]["messages"][0]
        ])
    except (IndexError, KeyError):
        return False