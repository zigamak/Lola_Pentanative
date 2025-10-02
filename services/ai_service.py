import logging
import json
import re
from typing import Dict, List, Any
from dataclasses import dataclass
from openai import AzureOpenAI
from openai import APIConnectionError, RateLimitError, OpenAIError

logger = logging.getLogger(__name__)

# --- Data Model for Order Items ---
@dataclass
class OrderItem:
    item_id: str
    name: str
    quantity: int
    variations: Dict[str, str]
    price: float

class AIService:
    """
    Handles AI-powered interactions, including chatbot responses, order parsing, and name parsing,
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
            self.ai_enabled = hasattr(config, 'is_ai_enabled') and config.is_ai_enabled() or bool(self.azure_api_key and self.azure_endpoint)

        self.azure_client = None
        if self.ai_enabled and self.azure_api_key and self.azure_endpoint:
            try:
                self.azure_client = AzureOpenAI(
                    api_key=self.azure_api_key,
                    api_version=self.api_version,
                    azure_endpoint=self.azure_endpoint
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

        system_prompt = """You are Lola, a friendly AI assistant for Ganador Express, a popular Nigerian fast food restaurant. 

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

    def parse_order_with_llm(self, user_message: str) -> Dict[str, Any]:
        """
        Parses a user's bulk order request using the LLM and returns structured JSON.

        Args:
            user_message (str): The user's message containing the order.

        Returns:
            Dict[str, Any]: A dictionary containing parsed order details.
        """
        if not self.ai_enabled or not self.azure_client:
            return {
                "success": False, 
                "error": "AI order processing is currently unavailable. Please use the regular menu.",
                "items": [],
                "packs": 1,
                "grouping": "",
                "special_instructions": "",
                "order_total": 0.0,
                "unrecognized_items": []
            }
        
        menu_context = self._create_menu_context()
        
        system_prompt = f"""You are Lola, a WhatsApp customer-service bot for Ganador Express. Your job is to parse customer food orders from conversational or ambiguous language into a structured JSON format, including modifications to existing orders.

Available menu items:
{menu_context}

SMART ORDERING RULES:
1. DEFAULT BEHAVIOR:
   - If user says "1 Jollof rice and 1 fried rice" = 1 portion each, 1 pack total (DEFAULT)
   - Default packs = 1 (not "unspecified")
   - Default food_share_pattern = use exact pattern from menu for each item
   - If no portions specified, assume 1 portion per item
   - If a number is specified before multiple items without individual counts (e.g., "3 Jollof rice and Fried rice"), assume the number applies to each item (3 Jollof and 3 Fried rice).

2. PACK LOGIC:
   - If user specifies packs (e.g., "in 3 packs"), use that number for packs
   - Treat terms like "packs," "plates," "servings," or "people" (e.g., "for 3 people") as equivalent to specifying the number of packs
   - If user says "separate packs" or similar, packs = number of different items
   - If user says "for X people" without specific pack assignments, replicate the entire order across X packs (e.g., "3 Moi Moi, 2 Jollof and Beef for 3 people" means 3 packs, each with 3 Moi Moi, 2 Jollof, 1 Beef)
   - If user explicitly assigns items to specific packs (e.g., "for pack 1: ..., for pack 2: ..."), use the grouped format with packs equal to the highest pack number mentioned or inferred
   - Pack calculation: for grouped orders, total portions are as specified per pack; for flat, portions can be distributed across packs

3. PORTION UNDERSTANDING:
   - "2 portions of Jollof rice" = exactly 2 portions
   - "Jollof rice" (no number) = 1 portion (default)
   - "2 Jollof rice" = 2 portions
   - Only mark as "unspecified" if genuinely ambiguous

4. MODIFICATION HANDLING:
   - If user says "add 2 Jollof rice," include these as new items or add to existing item portions
   - If user says "remove Jollof rice," include the item in the output with 0 portions to indicate removal
   - If user says "change to 3 packs," update the packs count
   - For ambiguous modifications, mark items as needing clarification

5. SMART INTERPRETATION:
   - Be generous with matching (e.g., "burger" matches menu items)
   - Understand Nigerian food terms and variations
   - Handle multiple ways of saying the same thing
   - Use the EXACT food_share_pattern from the menu data for each item
   - Be smart about ambiguous phrases: if a number precedes a list of items, apply it to all unless otherwise specified

6. OUTPUT FORMAT (for non-specific pack assignments or non-replicated orders):
{{
    "success": true,
    "items": [
        {{
            "name": "exact menu item name",
            "portions": number (default 1, never "unspecified" unless truly ambiguous, 0 for removals),
            "item_id": "menu item id",
            "price": price_per_item (float),
            "total_price": portions * price (float),
            "variations": {{}},
            "food_share_pattern": "use exact pattern from menu (Combo/Portion)"
        }}
    ],
    "packs": number (default 1, never "unspecified"),
    "grouping": "Description of packing preference",
    "special_instructions": "Any special requests",
    "order_total": total_price_of_all_items (float),
    "unrecognized_items": [
        {{
            "input": "user input not found",
            "message": "why not recognized"
        }}
    ]
}}

ALTERNATIVE OUTPUT FORMAT (use ONLY if user specifies items for specific packs or "for X people" implies replication):
{{
    "success": true,
    "pack_groups": [
        {{
            "pack": 1,
            "items": [
                {{
                    "name": "exact menu item name",
                    "portions": number for this pack,
                    "item_id": "menu item id",
                    "price": price_per_item (float),
                    "total_price": portions * price (float),
                    "variations": {{}},
                    "food_share_pattern": "use exact pattern from menu (Combo/Portion)"
                }}
            ]
        }},
        // ... more packs
    ],
    "packs": number (count of pack_groups),
    "grouping": "Description of packing preference",
    "special_instructions": "Any special requests",
    "order_total": sum of all item total_prices (float),
    "unrecognized_items": [
        {{
            "input": "user input not found",
            "message": "why not recognized"
        }}
    ]
}}

EXAMPLES:
- "1 Jollof rice and 1 fried rice" → flat, 1 portion each, 1 pack total, use menu's food_share_pattern
- "2 Jollof rice in 2 packs" → flat, 2 portions Jollof, 2 packs (1 portion per pack)
- "Jollof rice and chicken" → flat, 1 portion each, 1 pack, use exact food_share_pattern
- "3 Jollof rice for 3 people" → flat, 3 portions Jollof, 3 packs
- "2 Fried rice in 3 plates" → flat, 2 portions Fried rice, 3 packs
- "Chicken for 3 servings" → flat, 1 portion Chicken, 3 packs
- "Add 1 Chicken, remove Jollof rice, change to 2 packs" → flat, 1 portion Chicken, 0 portions Jollof rice, 2 packs
- "3 portions of Jollof rice and Fried rice for pack 1, Yam and egg for pack 2, 3 portions of Jollof rice and Fried rice for pack 3" → grouped, 3 Jollof and 3 Fried for pack 1, 1 Yam and 1 Egg for pack 2, 3 Jollof and 3 Fried for pack 3, packs=3
- "3 Moi Moi, 2 Jollof and Beef for 3 people" → grouped, 3 packs, each with 3 Moi Moi, 2 Jollof, 1 Beef

CRITICAL: Only use "unspecified" if the order is genuinely unclear. Default to sensible assumptions.
Always use the EXACT food_share_pattern from the menu data - don't default all items to "Combo".
Use the grouped format when packs are explicitly assigned or when "for X people" implies replication; otherwise, use flat.
"""

        try:
            response = self.azure_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Parse this order: {user_message}"}
                ],
                max_tokens=800,
                temperature=0.2
            )
            
            ai_response_content = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', ai_response_content, re.DOTALL)
            if json_match:
                parsed_json = json.loads(json_match.group())
                
                # Ensure defaults are set properly
                parsed_json.setdefault("unrecognized_items", [])
                parsed_json["order_total"] = float(parsed_json.get("order_total", 0.0))
                parsed_json.setdefault("grouping", "")
                parsed_json.setdefault("special_instructions", "")
                
                if "pack_groups" in parsed_json:
                    parsed_json.setdefault("packs", len(parsed_json["pack_groups"]))
                    # Recalculate totals for grouped
                    total = 0.0
                    for group in parsed_json["pack_groups"]:
                        for item in group.get("items", []):
                            if "portions" not in item or item["portions"] == "unspecified":
                                item["portions"] = 1
                            if item.get("portions") != 0:
                                item["total_price"] = float(item.get("price", 0.0)) * float(item["portions"])
                            else:
                                item["total_price"] = 0.0
                            total += item["total_price"]
                    parsed_json["order_total"] = total
                else:
                    parsed_json.setdefault("items", [])
                    parsed_json.setdefault("packs", 1)
                    # Apply defaults for flat
                    for item in parsed_json.get("items", []):
                        if item.get("portions") == "unspecified" or not item.get("portions"):
                            item["portions"] = 1
                        if item.get("portions") != 0:
                            item["total_price"] = float(item.get("price", 0.0)) * float(item["portions"])
                        else:
                            item["total_price"] = 0.0
                    # Recalculate order total
                    parsed_json["order_total"] = sum(
                        float(item.get("total_price", 0.0)) 
                        for item in parsed_json.get("items", []) if item.get("portions") != 0
                    )
                
                return parsed_json
            else:
                logger.error(f"No JSON found in AI response: {ai_response_content}")
                return {
                    "success": False,
                    "error": "Could not parse AI response (no JSON found)",
                    "items": [],
                    "packs": 1,
                    "grouping": "",
                    "special_instructions": "",
                    "order_total": 0.0,
                    "unrecognized_items": []
                }
        
        except json.JSONDecodeError as jde:
            logger.error(f"JSON decoding error from LLM response: {jde} - Response: {ai_response_content}")
            return {
                "success": False,
                "error": "Invalid AI response format",
                "items": [],
                "packs": 1,
                "grouping": "",
                "special_instructions": "",
                "order_total": 0.0,
                "unrecognized_items": []
            }
        except (APIConnectionError, RateLimitError, OpenAIError) as e:
            logger.error(f"Azure OpenAI API error parsing order: {e}", exc_info=True)
            return {
                "success": False,
                "error": "AI processing temporarily unavailable. Please try again.",
                "items": [],
                "packs": 1,
                "grouping": "",
                "special_instructions": "",
                "order_total": 0.0,
                "unrecognized_items": []
            }
        except Exception as e:
            logger.error(f"Unexpected error parsing order with LLM: {e}", exc_info=True)
            return {
                "success": False,
                "error": "AI processing error",
                "items": [],
                "packs": 1,
                "grouping": "",
                "special_instructions": "",
                "order_total": 0.0,
                "unrecognized_items": []
            }
    
    def parse_user_name(self, user_message: str) -> Dict[str, Any]:
        """
        Parses a user's input to extract their preferred name using the LLM.

        Args:
            user_message (str): The user's message containing the name.

        Returns:
            Dict[str, Any]: A dictionary with the parsed name or error details.
        """
        if not self.ai_enabled or not self.azure_client:
            return {
                "success": False,
                "error": "AI name parsing is currently unavailable.",
                "name": ""
            }

        system_prompt = """You are Lola, a WhatsApp customer-service bot for Ganador Express. Your task is to extract the preferred name from a user's message. The name might be provided in conversational formats like "you can call me Sam," "my name is Ziga," or "call me John." Return a JSON object with the extracted name.

Output format:
{
    "success": true,
    "name": "extracted name",
    "error": "" (or error message if applicable)
}

Examples:
- "you can call me Sam" → {"success": true, "name": "Sam", "error": ""}
- "my name is Ziga" → {"success": true, "name": "Ziga", "error": ""}
- "call me John" → {"success": true, "name": "John", "error": ""}
- "no name here" → {"success": false, "name": "", "error": "No name found in the input"}
"""

        try:
            response = self.azure_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract the name from this message: {user_message}"}
                ],
                max_tokens=100,
                temperature=0.2
            )
            ai_response_content = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', ai_response_content, re.DOTALL)
            if json_match:
                parsed_json = json.loads(json_match.group())
                parsed_json.setdefault("success", False)
                parsed_json.setdefault("name", "")
                parsed_json.setdefault("error", "")
                return parsed_json
            else:
                logger.error(f"No JSON found in AI response for name parsing: {ai_response_content}")
                return {"success": False, "name": "", "error": "Could not parse AI response"}
        except json.JSONDecodeError as jde:
            logger.error(f"JSON decoding error in name parsing: {jde} - Response: {ai_response_content}")
            return {"success": False, "name": "", "error": "Invalid AI response format"}
        except (APIConnectionError, RateLimitError, OpenAIError) as e:
            logger.error(f"Azure OpenAI API error in name parsing: {e}")
            return {"success": False, "name": "", "error": "AI processing temporarily unavailable"}
        except Exception as e:
            logger.error(f"Unexpected error in name parsing: {e}")
            return {"success": False, "name": "", "error": "AI processing error"}

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
            for item_dict in items:
                if isinstance(item_dict, dict):
                    name = item_dict.get('name', 'Unknown')
                    price = float(item_dict.get('price', 0.0))
                    item_id = item_dict.get('id', '')
                    food_share_pattern = item_dict.get('food_share_pattern', 'Combo')
                    context += f"- {name} (ID: {item_id}, Price: ₦{price:,.2f}, Pattern: {food_share_pattern})\n"
        return context