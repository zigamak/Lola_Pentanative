from utils.helpers import truncate_title
from .base_handler import BaseHandler

class MenuHandler(BaseHandler):
    """Handles menu navigation and item selection."""
    
    def handle_menu_state(self, state, message, original_message, session_id):
        """Handle menu state."""
        self.logger.info(f"MenuHandler: Received message '{message}' (original: '{original_message}') in menu state for session {session_id}")
        
        # Handle redirect message from GreetingHandler
        if message == "show_menu":
            self.logger.info(f"Showing menu categories for session {session_id}")
            return self.show_menu_categories(session_id)
        
        # Handle category selection
        category_map = {category.lower(): category for category in self.data_manager.menu_data.keys()}
        
        if message in category_map:
            selected_category = category_map[message]
            state["selected_category"] = selected_category
            state["current_state"] = "category_selected"
            state["current_handler"] = "menu_handler"
            self.session_manager.update_session_state(session_id, state)
            
            self.logger.info(f"Category '{selected_category}' selected for session {session_id}")
            
            items_data = self.data_manager.menu_data[selected_category]
            
            # Handle both dict and list formats for menu items
            if isinstance(items_data, dict):
                rows = [
                    {"id": item, "title": truncate_title(f"{item} (₦{price:,})")} 
                    for item, price in items_data.items()
                ]
            elif isinstance(items_data, list):
                rows = [
                    {"id": item_dict.get("name", "Unknown"), "title": truncate_title(f"{item_dict.get('name', 'Unknown')} (₦{item_dict.get('price', 0):,})")} 
                    for item_dict in items_data if isinstance(item_dict, dict)
                ]
            else:
                self.logger.error(f"Unexpected menu data format for category '{selected_category}': {type(items_data)}")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "Sorry, there's an issue with this category. Please try another category or contact support."
                )
            
            if not rows:
                return self.whatsapp_service.create_text_message(
                    session_id,
                    f"Sorry, no items available in {selected_category} right now. Please try another category."
                )
            
            sections = [{"title": f"{selected_category} Items", "rows": rows}]
            
            return self.whatsapp_service.create_list_message(
                session_id,
                f"🍽️ *{selected_category}*\n\nSelect an item to add to your cart:",
                "Select Item",
                sections
            )
            
        elif message == "back" or message == "menu":
            return self.handle_back_to_main(state, session_id)
        else:
            valid_categories = ", ".join(self.data_manager.menu_data.keys())
            return self.whatsapp_service.create_text_message(
                session_id,
                f"❌ Invalid selection: '{original_message}'\n\nPlease select from these categories:\n{valid_categories}\n\nOr type 'back' to return to main menu."
            )
    
    def show_menu_categories(self, session_id):
        """Show menu categories as a list."""
        try:
            if not self.data_manager.menu_data:
                self.logger.warning(f"Menu data is empty for session {session_id}")
                return self.whatsapp_service.create_text_message(
                    session_id, 
                    "Sorry, the menu is currently unavailable. Please try again later."
                )
            
            categories = list(self.data_manager.menu_data.keys())
            self.logger.info(f"Available categories: {categories}")
            
            rows = [{"id": category.lower(), "title": category} for category in categories]
            sections = [{"title": "Menu Categories", "rows": rows}]
            
            return self.whatsapp_service.create_list_message(
                session_id, 
                "🍽️ *Our Menu*\n\nChoose a category to browse items:", 
                "Categories", 
                sections
            )
            
        except Exception as e:
            self.logger.error(f"Error showing menu categories for session {session_id}: {e}", exc_info=True)
            return self.whatsapp_service.create_text_message(
                session_id,
                "Sorry, there was an error loading the menu. Please try again or contact support."
            )
    
    def handle_category_selected_state(self, state, message, original_message, session_id):
        """Handle category selected state."""
        self.logger.info(f"MenuHandler: Handling item selection '{original_message}' for session {session_id}")
        
        selected_category = state.get("selected_category")
        if not selected_category:
            self.logger.error(f"No selected category found in state for session {session_id}")
            state["current_state"] = "menu"
            state["current_handler"] = "menu_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.show_menu_categories(session_id)
        
        category_items = self.data_manager.menu_data.get(selected_category, {})
        
        # Handle both dict and list formats
        item_found = False
        item_price = 0
        
        if isinstance(category_items, dict):
            if original_message in category_items:
                item_found = True
                item_price = category_items[original_message]
        elif isinstance(category_items, list):
            for item_dict in category_items:
                if isinstance(item_dict, dict) and item_dict.get("name") == original_message:
                    item_found = True
                    item_price = item_dict.get("price", 0)
                    break
        
        if item_found:
            state["selected_item"] = original_message
            state["current_state"] = "quantity"  # Changed from "get_quantity" to match OrderHandler
            state["current_handler"] = "order_handler"
            self.session_manager.update_session_state(session_id, state)
            
            self.logger.info(f"Item '{original_message}' selected for session {session_id}, redirecting to order handler")
            
            return self.whatsapp_service.create_text_message(
                session_id,
                f"🛒 *{original_message}*\nPrice: ₦{item_price:,}\n\nHow many would you like to order?\n\nPlease enter a number (e.g., 1, 2, 3...):"
            )
            
        elif message == "back" or message == "menu":
            state["current_state"] = "menu"
            state["current_handler"] = "menu_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.show_menu_categories(session_id)
        else:
            # Show available items for the selected category
            available_items = []
            if isinstance(category_items, dict):
                available_items = list(category_items.keys())
            elif isinstance(category_items, list):
                available_items = [item.get("name", "Unknown") for item in category_items if isinstance(item, dict)]
            
            valid_items = ", ".join(available_items) if available_items else "No items available"
            
            return self.whatsapp_service.create_text_message(
                session_id,
                f"❌ Invalid item: '{original_message}'\n\n📋 Available items in {selected_category}:\n{valid_items}\n\nPlease select a valid item or type 'back' to choose a different category."
            )