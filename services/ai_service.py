import logging
import json
import re
import os
from typing import Dict, List, Any
from dataclasses import dataclass
from openai import AzureOpenAI
from openai import APIConnectionError, RateLimitError, OpenAIError

logger = logging.getLogger(__name__)

@dataclass
class OrderItem:
    item_id: str
    name: str
    quantity: int
    variations: Dict[str, str]
    price: float

class AIService:
    """
    Handles AI-powered interactions, including chatbot responses and order parsing,
    by interfacing with the Azure OpenAI API.
    """

    def __init__(self, config, data_manager):
        """
        Initializes the AIService with configuration and data manager.

        Args:
            config: A configuration object or dictionary containing Azure OpenAI settings.
            data_manager: An instance of DataManager to access menu data.
        """
        self.data_manager = data_manager

        if isinstance(config, dict):
            self.azure_api_key = config.get("azure_api_key")
            self.azure_endpoint = config.get("azure_endpoint")
            self.deployment_name = config.get("azure_deployment_name", "gpt-35-turbo")
            self.api_version = config.get("api_version", "2024-02-15")
            self.ai_enabled = bool(self.azure_api_key)
        else:
            self.azure_api_key = getattr(config, 'AZURE_API_KEY', None)
            self.azure_endpoint = getattr(config, 'AZURE_ENDPOINT', None)
            self.deployment_name = getattr(config, 'AZURE_DEPLOYMENT_NAME', "gpt-35-turbo")
            self.api_version = getattr(config, 'AZURE_API_VERSION', "2024-02-15")
            
            if hasattr(config, 'is_ai_enabled'):
                self.ai_enabled = config.is_ai_enabled()
            else:
                self.ai_enabled = bool(self.azure_api_key and self.azure_endpoint)

        self.azure_client = None
        if self.ai_enabled and self.azure_api_key and self.azure_endpoint:
            try:
                self.azure_client = AzureOpenAI(
                    api_key=self.azure_api_key,
                    api_version=self.api_version,
                    azure_endpoint=self.azure_endpoint,
                )
                logger.info("Azure OpenAI client initialized successfully in AIService.")
            except Exception as e:
                logger.error(f"Failed to initialize Azure OpenAI client in AIService: {e}", exc_info=True)
                self.ai_enabled = False
        else:
            logger.warning("AI features disabled in AIService - missing Azure OpenAI configuration or client initialization failed.")
            self.ai_enabled = False

    def generate_lola_response(self, user_message: str) -> str:
        """
        Generates an AI response for the Lola chatbot using Azure OpenAI.

        Args:
            user_message (str): The message from the user.

        Returns:
            str: The AI-generated response.
        """
        if not self.ai_enabled or not self.azure_client:
            return "🤖 Sorry, I'm currently offline. Please try the regular menu options!"
            
        system_prompt = """You are Lola, a friendly AI assistant for Chicken Republic, a popular Nigerian fast food restaurant. 

Your personality:
- Warm, friendly, and helpful
- Use Nigerian expressions occasionally (like "How far?", "No wahala", etc.)
- Be enthusiastic about food
- Keep responses conversational but informative

You can help with:
- Menu recommendations
- Nutritional information
- Order suggestions
- General questions about food
- Cooking tips

Keep responses concise (max 200 words) and engaging. If asked about ordering, remind users they can use the regular menu or AI bulk order feature.
"""

        try:
            response = self.azure_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=300,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content.strip()
            
            ai_response += "\n\n_Type 'menu' to return to main menu_ 🤖"
            
            return ai_response
        
        except (APIConnectionError, RateLimitError, OpenAIError) as e:
            logger.error(f"Azure OpenAI API error in Lola response generation: {e}", exc_info=True)
            return "🤖 Sorry, I'm having trouble connecting to my brain right now. Please try again!"
        except Exception as e:
            logger.error(f"Unexpected error generating Lola response: {e}", exc_info=True)
            return "Sorry, I'm having trouble right now. Please try again! 🤖"

    def parse_order_with_llm(self, user_message: str, previous_order: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Parses a user's bulk order request using the LLM and returns structured JSON.

        Args:
            user_message (str): The user's message containing the order.
            previous_order (Dict[str, Any], optional): The previous order to be modified. Defaults to None.

        Returns:
            Dict[str, Any]: A dictionary containing parsed order details,
                             recognized, ambiguous, and unrecognized items.
        """
        if not self.ai_enabled or not self.azure_client:
            return {
                "success": False, 
                "error": "AI order processing is currently unavailable. Please use the regular menu."
            }
        
        menu_context = self._create_menu_context()
        
        # Craft the system prompt to handle modifications if a previous order is provided
        if previous_order:
            previous_order_str = json.dumps(previous_order, indent=2)
            system_prompt = f"""You are an order parsing assistant for Chicken Republic. Your task is to update a customer's existing order based on their new request.

Current menu items:
{menu_context}

The customer's current order is:
{previous_order_str}

The user's new message is a request to modify this order. You need to combine the previous order with the new request. If the user adds a new item, add it to the recognized_items list. If they ask to remove or change an item's quantity, update the recognized_items list accordingly.

After processing the modification, return a new JSON response with the same structure as below. Ensure all prices are numbers (float or int). Recalculate the order_total. If an item has variations, try to capture them. If a quantity is not specified, assume 1.
{{
    "success": true/false,
    "recognized_items": [
        {{
            "item_id": "menu_item_id_from_context",
            "name": "item name",
            "quantity": number,
            "variations": {{}},
            "price": price_per_item,
            "total_price": quantity * price
        }}
    ],
    "ambiguous_items": [
        {{
            "input": "user input for ambiguous item",
            "clarification_needed": "what needs clarification (e.g., Which 'burger' did you mean?)",
            "possible_matches": ["Full Item Name 1", "Full Item Name 2", "Full Item Name 3"],
            "quantity": number_if_known
        }}
    ],
    "unrecognized_items": [
        {{
            "input": "user input for unrecognized item",
            "message": "explanation why not found"
        }}
    ],
    "order_total": total_price_of_recognized_items,
    "error": "error message if any"
}}

If an item mentioned by the user is not found, or is ambiguous, populate the respective lists. Do not include items that have been removed.
"""
        else:
            system_prompt = f"""You are an order parsing assistant for Chicken Republic. 
            
Available menu items:
{menu_context}

Parse the user's order and return a JSON response with this structure. Ensure all prices are numbers (float or int). If an item has variations, try to capture them. If a quantity is not specified, assume 1.
{{
    "success": true/false,
    "recognized_items": [
        {{
            "item_id": "menu_item_id_from_context",
            "name": "item name",
            "quantity": number,
            "variations": {{}},
            "price": price_per_item,
            "total_price": quantity * price
        }}
    ],
    "ambiguous_items": [
        {{
            "input": "user input for ambiguous item",
            "clarification_needed": "what needs clarification (e.g., Which 'burger' did you mean?)",
            "possible_matches": ["Full Item Name 1", "Full Item Name 2", "Full Item Name 3"],
            "quantity": number_if_known
        }}
    ],
    "unrecognized_items": [
        {{
            "input": "user input for unrecognized item",
            "message": "explanation why not found"
        }}
    ],
    "order_total": total_price_of_recognized_items,
    "error": "error message if any"
}}

If an item mentioned by the user is not found, or is ambiguous, populate the respective lists.
Be generous with matching - if user says "burger" and you have "Chief Burger", that's a match.
For quantities without specification, assume 1.
"""

        try:
            response = self.azure_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Parse this order: {user_message}"}
                ],
                max_tokens=800,
                temperature=0.3,
            )
            
            ai_response_content = response.choices[0].message.content.strip()
            
            json_match = re.search(r'\{.*\}', ai_response_content, re.DOTALL)
            if json_match:
                parsed_json = json.loads(json_match.group())
                
                if not isinstance(parsed_json.get("recognized_items"), list):
                    parsed_json["recognized_items"] = []
                if not isinstance(parsed_json.get("ambiguous_items"), list):
                    parsed_json["ambiguous_items"] = []
                if not isinstance(parsed_json.get("unrecognized_items"), list):
                    parsed_json["unrecognized_items"] = []
                parsed_json["order_total"] = float(parsed_json.get("order_total", 0.0))
                return parsed_json
            else:
                logger.error(f"No JSON found in AI response: {ai_response_content}")
                return {"success": False, "error": "Could not parse AI response (no JSON found)", "recognized_items": [], "ambiguous_items": [], "unrecognized_items": [], "order_total": 0.0}
            
        except json.JSONDecodeError as jde:
            logger.error(f"JSON decoding error from LLM response: {jde} - Response: {ai_response_content}")
            return {"success": False, "error": "Invalid AI response format", "recognized_items": [], "ambiguous_items": [], "unrecognized_items": [], "order_total": 0.0}
        except (APIConnectionError, RateLimitError, OpenAIError) as e:
            logger.error(f"Azure OpenAI API error parsing order: {e}", exc_info=True)
            return {"success": False, "error": "AI processing temporarily unavailable. Please try again.", "recognized_items": [], "ambiguous_items": [], "unrecognized_items": [], "order_total": 0.0}
        except Exception as e:
            logger.error(f"Unexpected error parsing order with LLM: {e}", exc_info=True)
            return {"success": False, "error": "AI processing error", "recognized_items": [], "ambiguous_items": [], "unrecognized_items": [], "order_total": 0.0}
    
    def _create_menu_context(self) -> str:
        """
        Creates a formatted string representation of the menu data for AI context.
        """
        if not self.data_manager.menu_data:
            logger.warning("Menu data not available in DataManager for AI context.")
            return "Menu data not available."
        
        context = ""
        for category, items in self.data_manager.menu_data.items():
            context += f"\n*{category.upper()}*:\n"
            if isinstance(items, dict):
                for item_name, price in items.items():
                    context += f"- {item_name}: ₦{price:,}\n"
            elif isinstance(items, list):
                for item_dict in items:
                    if isinstance(item_dict, dict):
                        name = item_dict.get('name', 'Unknown')
                        price = item_dict.get('price', 0)
                        item_id = item_dict.get('id', '')
                        context += f"- {name} (ID: {item_id}): ₦{price:,}\n"
        return context