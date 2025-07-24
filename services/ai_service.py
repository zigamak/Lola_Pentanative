import logging
import json
import re
import os # Import os to potentially check for env vars, or advise removing them
from typing import Dict, List, Any
from dataclasses import dataclass
from openai import AzureOpenAI
from openai import APIConnectionError, RateLimitError, OpenAIError

# Import httpx if you *intend* to use custom proxy configurations.
# For simply avoiding the 'proxies' error when it's undesired, you don't need to import httpx.
# import httpx 

logger = logging.getLogger(__name__)

# --- Data Model for Order Items (could be shared or defined here) ---
@dataclass
class OrderItem:
    item_id: str
    name: str
    quantity: int
    variations: Dict[str, str]
    price: float

# --- AI Service Class ---
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

        # Determine if config is a dictionary or an object with attributes
        # Prioritize checking if it's a dictionary; otherwise, assume it's a Config object
        if isinstance(config, dict):
            # If it's a dictionary, use .get() method
            self.azure_api_key = config.get("azure_api_key")
            self.azure_endpoint = config.get("azure_endpoint")
            self.deployment_name = config.get("azure_deployment_name", "gpt-35-turbo")
            self.api_version = config.get("api_version", "2024-02-15")
            self.ai_enabled = bool(self.azure_api_key)
        else:
            # Assume it's a Config object or similar, access attributes directly
            # Using getattr for robust access in case an attribute is unexpectedly missing
            self.azure_api_key = getattr(config, 'AZURE_API_KEY', None)
            self.azure_endpoint = getattr(config, 'AZURE_ENDPOINT', None)
            self.deployment_name = getattr(config, 'AZURE_DEPLOYMENT_NAME', "gpt-35-turbo")
            self.api_version = getattr(config, 'AZURE_API_VERSION', "2024-02-15")
            
            # Check if is_ai_enabled method exists before calling
            if hasattr(config, 'is_ai_enabled'):
                self.ai_enabled = config.is_ai_enabled()
            else:
                self.ai_enabled = bool(self.azure_api_key and self.azure_endpoint)


        # Initialize Azure OpenAI client only if AI is enabled and properly configured
        self.azure_client = None
        if self.ai_enabled and self.azure_api_key and self.azure_endpoint:
            try:
                # IMPORTANT for openai==1.x.x:
                # The 'proxies' argument is NOT accepted directly by AzureOpenAI client.
                # If you encounter "TypeError: Client.__init__() got an unexpected keyword argument 'proxies'",
                # it's likely due to HTTP_PROXY/HTTPS_PROXY environment variables being set.
                #
                # SOLUTION:
                # 1. ENSURE no HTTP_PROXY or HTTPS_PROXY environment variables are set in your Render deployment.
                #    This is the most common cause of the error when you don't explicitly configure proxies.
                # 2. If you *do* need a proxy, you must configure it via an httpx.Client and pass it
                #    using the `http_client` argument to AzureOpenAI. Example below (commented out).
                #
                # Example of explicit proxy configuration (uncomment if needed):
                # proxy_url = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
                # custom_httpx_client = None
                # if proxy_url:
                #     try:
                #         custom_httpx_client = httpx.Client(
                #             proxies={
                #                 "http://": proxy_url,
                #                 "https://": proxy_url,
                #             }
                #         )
                #         logger.info(f"Using custom httpx client with proxy: {proxy_url}")
                #     except Exception as http_e:
                #         logger.error(f"Failed to configure httpx client with proxy: {http_e}")
                #         custom_httpx_client = None # Fallback to no custom client
                
                self.azure_client = AzureOpenAI(
                    api_key=self.azure_api_key,
                    api_version=self.api_version,
                    azure_endpoint=self.azure_endpoint,
                    # http_client=custom_httpx_client # Pass custom client if configured
                )
                logger.info("Azure OpenAI client initialized successfully in AIService.")
            except Exception as e:
                # This is the exact error point from your traceback.
                # The cause is likely implicit proxy settings the library picks up
                # which are incompatible with this version's constructor.
                logger.error(f"Failed to initialize Azure OpenAI client in AIService: {e}", exc_info=True)
                self.ai_enabled = False # Disable AI if client initialization fails
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
            
            # Add signature and menu option
            ai_response += "\n\n_Type 'menu' to return to main menu_ 🤖"
            
            return ai_response
        
        except (APIConnectionError, RateLimitError, OpenAIError) as e:
            logger.error(f"Azure OpenAI API error in Lola response generation: {e}", exc_info=True)
            return "🤖 Sorry, I'm having trouble connecting to my brain right now. Please try again!"
        except Exception as e:
            logger.error(f"Unexpected error generating Lola response: {e}", exc_info=True)
            return "Sorry, I'm having trouble right now. Please try again! 🤖"

    def parse_order_with_llm(self, user_message: str) -> Dict[str, Any]:
        """
        Parses a user's bulk order request using the LLM and returns structured JSON.

        Args:
            user_message (str): The user's message containing the order.

        Returns:
            Dict[str, Any]: A dictionary containing parsed order details,
                            recognized, ambiguous, and unrecognized items.
        """
        if not self.ai_enabled or not self.azure_client:
            return {
                "success": False, 
                "error": "AI order processing is currently unavailable. Please use the regular menu."
            }
        
        # Create menu context for the AI using the most up-to-date data
        menu_context = self._create_menu_context()
        
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
            "quantity": number_if_known # Quantity if specified by user for ambiguous item
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
                # response_format={"type": "json_object"} # Use this if your Azure deployment supports it and you want stricter JSON output
            )
            
            ai_response_content = response.choices[0].message.content.strip()
            
            # Extract JSON from response (robustly handle potential markdown/text around JSON)
            json_match = re.search(r'\{.*\}', ai_response_content, re.DOTALL)
            if json_match:
                parsed_json = json.loads(json_match.group())
                # Ensure lists are always present and of the correct type, even if LLM returns null
                if not isinstance(parsed_json.get("recognized_items"), list):
                    parsed_json["recognized_items"] = []
                if not isinstance(parsed_json.get("ambiguous_items"), list):
                    parsed_json["ambiguous_items"] = []
                if not isinstance(parsed_json.get("unrecognized_items"), list):
                    parsed_json["unrecognized_items"] = []
                # Ensure order_total is a float
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
        # Iterate through categories and items to build the menu context
        for category, items in self.data_manager.menu_data.items():
            context += f"\n*{category.upper()}*:\n"
            if isinstance(items, dict): # Assuming menu_data is {category: {item_name: price}}
                for item_name, price in items.items():
                    context += f"- {item_name}: ₦{price:,}\n"
            elif isinstance(items, list): # Fallback for list structure, if items are [{name:.., price:..}]
                for item_dict in items:
                    if isinstance(item_dict, dict):
                        name = item_dict.get('name', 'Unknown')
                        price = item_dict.get('price', 0)
                        item_id = item_dict.get('id', '') # Include item_id if available to help LLM match
                        context += f"- {name} (ID: {item_id}): ₦{price:,}\n"
        return context