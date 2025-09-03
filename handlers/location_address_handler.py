import logging
from .base_handler import BaseHandler
from utils.helpers import format_cart

logger = logging.getLogger(__name__)

class LocationAddressHandler(BaseHandler):
    """
    Handles location-based address collection for the bot, including live location,
    manual address entry, and preset locations.
    """

    def __init__(self, config, session_manager, data_manager, whatsapp_service, location_service):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
        self.location_service = location_service
        logger.debug("LocationAddressHandler initialized with phone_number_id: %s", config.WHATSAPP_PHONE_NUMBER_ID)

    def initiate_address_collection(self, state: dict, session_id: str):
        """
        Starts address collection with options tailored to context. Shows preset locations
        when called from confirm_order state, otherwise includes live location and manual entry.
        """
        state["current_state"] = "address_collection_menu"
        state["current_handler"] = "location_handler"
        
        # Check if we're coming from order confirmation (address update)
        from_confirm_order = state.get("from_confirm_order", False) or state.get("from_confirm_details", False)

        if from_confirm_order:
            buttons = [
                {"type": "reply", "reply": {"id": "preset_palmpay_salvation", "title": "Palmpay Salvation"}},
                {"type": "reply", "reply": {"id": "preset_howson_wright", "title": "Howson Wright"}},
                {"type": "reply", "reply": {"id": "enter_your_address", "title": "Enter Your Address"}}
            ]
            message = "📍 *Select or Enter Delivery Address*\n\nPlease choose a preset location or enter your own address:"
        else:
            buttons = [
                {"type": "reply", "reply": {"id": "share_current_location", "title": "📍 Share Location"}},
                {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Type Address"}}
            ]
            # Only add saved address option if there's actually a saved address
            if state.get("address"):
                buttons.append({"type": "reply", "reply": {"id": "use_saved_address", "title": "🏠 Saved Address"}})
            
            saved_address_text = f"\n\n🏠 *Last address:* {state['address']}" if state.get("address") else ""
            message = f"📍 *Provide delivery address*{saved_address_text}\n\nPlease select an option below:"

        # Update session state before returning
        self.session_manager.update_session_state(session_id, state)
        
        logger.debug("Initiating address collection for session %s, from_confirm_order: %s", session_id, from_confirm_order)
        return self.whatsapp_service.create_button_message(session_id, message, buttons)

    def handle_address_collection_menu(self, state: dict, message: str, session_id: str):
        """
        Handles user's selection from the address collection menu.
        """
        logger.debug("Handling address collection menu for session %s, message: %s", session_id, message)
        
        if message == "update_address":
            logger.info("Received update_address redirect from order handler for session %s", session_id)
            return self.initiate_address_collection(state, session_id)
        
        if message == "preset_palmpay_salvation":
            address = "Palmpay Salvation"
            coordinates = self.location_service.get_coordinates_from_address(address) if self.config.ENABLE_LOCATION_FEATURES else None
            latitude, longitude = coordinates if coordinates else (None, None)
            map_link = self.location_service.generate_maps_link(address) if self.config.ENABLE_LOCATION_FEATURES else ""
            
            state["address"] = address
            state["latitude"] = latitude
            state["longitude"] = longitude
            state["map_link"] = map_link
            self._save_address_to_user_details(state, address, latitude, longitude, map_link, session_id)
            
            maps_info = f"\n🗺️ *View on Maps:* {map_link}" if map_link else ""
            logger.info("Selected preset address 'Palmpay Salvation' for session %s", session_id)
            return self._proceed_to_order_confirmation(state, session_id, address, maps_info)
        
        elif message == "preset_howson_wright":
            address = "Howson Wright"
            coordinates = self.location_service.get_coordinates_from_address(address) if self.config.ENABLE_LOCATION_FEATURES else None
            latitude, longitude = coordinates if coordinates else (None, None)
            map_link = self.location_service.generate_maps_link(address) if self.config.ENABLE_LOCATION_FEATURES else ""
            
            state["address"] = address
            state["latitude"] = latitude
            state["longitude"] = longitude
            state["map_link"] = map_link
            self._save_address_to_user_details(state, address, latitude, longitude, map_link, session_id)
            
            maps_info = f"\n🗺️ *View on Maps:* {map_link}" if map_link else ""
            logger.info("Selected preset address 'Howson Wright' for session %s", session_id)
            return self._proceed_to_order_confirmation(state, session_id, address, maps_info)
        
        elif message == "enter_your_address":
            logger.info("User chose to enter their own address for session %s", session_id)
            return self._show_address_entry_submenu(state, session_id)
        
        elif message == "share_current_location":
            return self._request_live_location(state, session_id)
        
        elif message == "type_address_manually":
            return self._request_manual_address(state, session_id)
        
        elif message == "use_saved_address":
            return self._use_saved_address(state, session_id)
        
        else:
            logger.debug("Invalid option '%s' for session %s", message, session_id)
            # Rebuild buttons based on current context
            from_confirm_order = state.get("from_confirm_order", False) or state.get("from_confirm_details", False)
            
            if from_confirm_order:
                buttons = [
                    {"type": "reply", "reply": {"id": "preset_palmpay_salvation", "title": "Palmpay Salvation"}},
                    {"type": "reply", "reply": {"id": "preset_howson_wright", "title": "Howson Wright"}},
                    {"type": "reply", "reply": {"id": "enter_your_address", "title": "Enter Your Address"}}
                ]
            else:
                buttons = [
                    {"type": "reply", "reply": {"id": "share_current_location", "title": "📍 Share Location"}},
                    {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Type Address"}}
                ]
                if state.get("address"):
                    buttons.append({"type": "reply", "reply": {"id": "use_saved_address", "title": "🏠 Saved Address"}})
            
            return self.whatsapp_service.create_button_message(
                session_id,
                f"❌ *Invalid option: '{message}'*\n\nPlease select an option below:",
                buttons
            )

    def _show_address_entry_submenu(self, state: dict, session_id: str):
        """
        Shows submenu for live location or manual address entry when 'Enter your address' is selected.
        """
        state["current_state"] = "address_entry_submenu"
        state["current_handler"] = "location_handler"
        self.session_manager.update_session_state(session_id, state)
        logger.info("Showing address entry submenu for session %s", session_id)
        
        buttons = [
            {"type": "reply", "reply": {"id": "share_current_location", "title": "📍 Share Location"}},
            {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Type Address"}}
        ]
        
        return self.whatsapp_service.create_button_message(
            session_id,
            "📍 *Enter Your Delivery Address*\n\nPlease choose how you'd like to provide your address:",
            buttons
        )

    def handle_address_entry_submenu(self, state: dict, message: str, session_id: str):
        """
        Handles selections from the address entry submenu.
        """
        logger.debug("Handling address entry submenu for session %s, message: %s", session_id, message)
        
        if message == "share_current_location":
            return self._request_live_location(state, session_id)
        elif message == "type_address_manually":
            return self._request_manual_address(state, session_id)
        else:
            logger.debug("Invalid option '%s' in address entry submenu for session %s", message, session_id)
            buttons = [
                {"type": "reply", "reply": {"id": "share_current_location", "title": "📍 Share Location"}},
                {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Type Address"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"❌ *Invalid option: '{message}'*\n\nPlease choose how you'd like to provide your address:",
                buttons
            )

    def _request_live_location(self, state: dict, session_id: str):
        """
        Prompts user to share live location via WhatsApp.
        """
        state["current_state"] = "awaiting_live_location"
        state["current_handler"] = "location_handler"
        self.session_manager.update_session_state(session_id, state)
        logger.info("Requested live location for session %s", session_id)
        return self.whatsapp_service.create_text_message(
            session_id,
            "📍 *Share Your Location*\n\n" +
            "1️⃣ Tap *attachment* (📎) button\n" +
            "2️⃣ Select *'Location'*\n" +
            "3️⃣ Choose *'Send current location'*\n\n" +
            "✨ I'll convert it to an address!\n" +
            "⏰ *Waiting for your location...*"
        )

    def _request_manual_address(self, state: dict, session_id: str):
        """
        Prompts user to manually type their delivery address.
        """
        state["current_state"] = "manual_address_input"
        state["current_handler"] = "location_handler"
        self.session_manager.update_session_state(session_id, state)
        logger.info("Requested manual address for session %s", session_id)
        return self.whatsapp_service.create_text_message(
            session_id,
            "✏️ *Type Address*\n\n" +
            "Provide complete address:\n" +
            "• House/Plot number\n" +
            "• Street name\n" +
            "• Area/District\n" +
            "• City/State\n\n" +
            "*Example:* 123 Main St, Wuse 2, Abuja"
        )

    def _use_saved_address(self, state: dict, session_id: str):
        """
        Uses previously saved address from session state.
        """
        if not state.get("address"):
            logger.warning("No saved address for session %s", session_id)
            return self.initiate_address_collection(state, session_id)

        maps_info = f"\n🗺️ *View on Maps:* {state['map_link']}" if state.get("map_link") else ""
        logger.info("Using saved address for session %s: %s", session_id, state["address"])
        return self._proceed_to_order_confirmation(state, session_id, state["address"], maps_info)

    def handle_live_location(self, state: dict, session_id: str, latitude: float, longitude: float, location_name: str = None, location_address: str = None):
        """
        Processes live location data from WhatsApp.
        """
        logger.info("Processing live location for %s: Lat=%s, Lon=%s, Name='%s', Address='%s'", session_id, latitude, longitude, location_name, location_address)

        if not latitude or not longitude:
            logger.warning("Invalid location data for session %s", session_id)
            state["current_state"] = "address_collection_menu"
            state["current_handler"] = "location_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_button_message(
                session_id,
                "❌ *Invalid location*\n\nPlease select an option below:",
                [
                    {"type": "reply", "reply": {"id": "share_current_location", "title": "📍 Try Share Again"}},
                    {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Type Address"}}
                ]
            )

        readable_address = location_address
        map_link = ""
        
        # Better address handling
        if (not readable_address or readable_address == "unknown" or len(readable_address.strip()) == 0) and self.config.ENABLE_LOCATION_FEATURES:
            try:
                geocoded_address = self.location_service.get_address_from_coordinates(latitude, longitude)
                if geocoded_address:
                    readable_address = geocoded_address
                    map_link = self.location_service.generate_maps_link(readable_address)
                    logger.info("Geocoded coordinates %s,%s to address: %s", latitude, longitude, readable_address)
                else:
                    logger.warning("Could not geocode coordinates %s,%s for %s", latitude, longitude, session_id)
                    map_link = self.location_service.generate_maps_link_from_coordinates(latitude, longitude)
            except Exception as e:
                logger.error("Error geocoding coordinates for %s: %s", session_id, e)
                map_link = self.location_service.generate_maps_link_from_coordinates(latitude, longitude) if self.config.ENABLE_LOCATION_FEATURES else ""

        if readable_address and readable_address != "unknown":
            state["address"] = readable_address
            state["latitude"] = latitude
            state["longitude"] = longitude
            state["map_link"] = map_link
            state["current_state"] = "confirm_detected_location"
            state["current_handler"] = "location_handler"
            self._save_address_to_user_details(state, readable_address, latitude, longitude, map_link, session_id)

            location_info = self.location_service.format_location_info(latitude, longitude, readable_address)
            buttons = [
                {"type": "reply", "reply": {"id": "confirm_location", "title": "✅ Use Address"}},
                {"type": "reply", "reply": {"id": "choose_different", "title": "📍 Choose Another"}}
            ]

            self.session_manager.update_session_state(session_id, state)
            logger.info("Live location processed for %s. Awaiting confirmation.", session_id)
            return self.whatsapp_service.create_button_message(
                session_id,
                f"🎯 *Location Detected!*\n\n{location_info}\n\nPlease select an option below:",
                buttons
            )
        else:
            coordinates_text = f"Latitude: {latitude}, Longitude: {longitude}"
            map_link = self.location_service.generate_maps_link_from_coordinates(latitude, longitude) if self.config.ENABLE_LOCATION_FEATURES else ""
            maps_link_info = f"\n🗺️ *View on Maps:* {map_link}" if map_link else ""

            buttons = [
                {"type": "reply", "reply": {"id": "use_coordinates", "title": "✅ Use Coordinates"}},
                {"type": "reply", "reply": {"id": "type_address_instead", "title": "✏️ Type Address"}}
            ]

            state["temp_coordinates"] = {"latitude": latitude, "longitude": longitude}
            state["map_link"] = map_link
            state["current_state"] = "confirm_coordinates"
            state["current_handler"] = "location_handler"
            self.session_manager.update_session_state(session_id, state)
            logger.warning("No readable address for %s from %s,%s. Awaiting coordinates confirmation.", session_id, latitude, longitude)
            return self.whatsapp_service.create_button_message(
                session_id,
                f"📍 *Location Received*\n\n{coordinates_text}{maps_link_info}\n\nPlease select an option below:",
                buttons
            )

    def handle_manual_address_input(self, state: dict, original_message: str, session_id: str):
        """
        Handles manual address input with validation and geocoding.
        """
        address = original_message.strip()
        logger.debug("Handling manual address for %s: '%s'", session_id, address)

        # Better validation logic
        if len(address) < 5 or not any(char.isalpha() for char in address):
            state["current_state"] = "manual_address_input"
            state["current_handler"] = "location_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_button_message(
                session_id,
                "⚠️ *Invalid address*\n\nPlease include:\n" +
                "• Street name/number\n• Area/District\n• City/State\n\n" +
                "Example: 123 Main St, Wuse 2, Abuja\n\nPlease select an option below:",
                [
                    {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Try Again"}},
                    {"type": "reply", "reply": {"id": "share_current_location", "title": "📍 Share Location"}}
                ]
            )

        location_coordinates = None
        map_link = ""
        if self.config.ENABLE_LOCATION_FEATURES:
            try:
                coordinates = self.location_service.get_coordinates_from_address(address)
                if coordinates:
                    latitude, longitude = coordinates
                    location_coordinates = {"latitude": latitude, "longitude": longitude}
                    map_link = self.location_service.generate_maps_link(address)
                    logger.info("Geocoded address '%s' to: %s", address, location_coordinates)
                else:
                    logger.warning("Could not geocode address '%s' for %s", address, session_id)
            except Exception as e:
                logger.error("Error geocoding address '%s' for %s: %s", address, session_id, e)

        # Update state properly
        state["address"] = address
        state["latitude"] = location_coordinates.get("latitude") if location_coordinates else None
        state["longitude"] = location_coordinates.get("longitude") if location_coordinates else None
        state["map_link"] = map_link
        
        self._save_address_to_user_details(state, address, 
                                         location_coordinates.get("latitude") if location_coordinates else None,
                                         location_coordinates.get("longitude") if location_coordinates else None,
                                         map_link, session_id)

        logger.info("Manual address '%s' processed for %s", address, session_id)
        maps_info = f"\n🗺️ *View on Maps:* {map_link}" if map_link else ""
        return self._proceed_to_order_confirmation(state, session_id, address, maps_info)

    def handle_confirm_detected_location(self, state: dict, message: str, session_id: str):
        """
        Handles confirmation of detected location.
        """
        logger.debug("Handling confirm detected location for %s, message: %s", session_id, message)
        if message == "confirm_location":
            self._save_address_to_user_details(state, state["address"], 
                                            state.get("latitude"),
                                            state.get("longitude"),
                                            state.get("map_link", ""), session_id)
            maps_info = f"\n{self.location_service.format_location_info(state['latitude'], state['longitude'], state['address'])}" if state.get("latitude") and state.get("longitude") and state.get("address") else ""
            logger.info("Confirmed location for %s: %s", session_id, state.get("address"))
            return self._proceed_to_order_confirmation(state, session_id, state["address"], maps_info)

        elif message == "choose_different":
            state.pop("latitude", None)
            state.pop("longitude", None)
            state.pop("address", None)
            state.pop("map_link", None)
            state["current_state"] = "address_collection_menu"
            state["current_handler"] = "location_handler"
            self.session_manager.update_session_state(session_id, state)
            logger.info("User %s chose different address method", session_id)
            return self.initiate_address_collection(state, session_id)

        else:
            logger.debug("Invalid option '%s' for %s", message, session_id)
            location_info = self.location_service.format_location_info(
                state.get("latitude"),
                state.get("longitude"),
                state.get("address")
            ) if state.get("latitude") and state.get("longitude") and state.get("address") else "Location data unavailable."
            return self.whatsapp_service.create_button_message(
                session_id,
                f"❌ *Invalid option: '{message}'*\n\n{location_info}\n\nPlease select an option below:",
                [
                    {"type": "reply", "reply": {"id": "confirm_location", "title": "✅ Use Address"}},
                    {"type": "reply", "reply": {"id": "choose_different", "title": "📍 Choose Another"}}
                ]
            )

    def handle_confirm_coordinates(self, state: dict, message: str, session_id: str):
        """
        Handles confirmation of coordinates when no readable address is found.
        """
        logger.debug("Handling confirm coordinates for %s, message: %s", session_id, message)
        if message == "use_coordinates":
            if not state.get("temp_coordinates"):
                logger.error("Missing temp coordinates for %s", session_id)
                return self.initiate_address_collection(state, session_id)

            coords = state["temp_coordinates"]
            address_fallback = f"Location: {coords['latitude']}, {coords['longitude']}"
            state["address"] = address_fallback
            state["latitude"] = coords["latitude"]
            state["longitude"] = coords["longitude"]
            state["map_link"] = state.get("map_link", "")
            self._save_address_to_user_details(state, address_fallback, coords["latitude"], coords["longitude"], state["map_link"], session_id)
            state.pop("temp_coordinates", None)
            self.session_manager.update_session_state(session_id, state)

            maps_link_info = f"\n🗺️ *View on Maps:* {state['map_link']}" if state.get("map_link") else ""
            logger.info("Confirmed coordinates for %s: %s", session_id, address_fallback)
            return self._proceed_to_order_confirmation(state, session_id, address_fallback, maps_link_info)

        elif message == "type_address_instead":
            state.pop("temp_coordinates", None)
            state.pop("map_link", None)
            state["current_state"] = "manual_address_input"
            state["current_handler"] = "location_handler"
            self.session_manager.update_session_state(session_id, state)
            logger.info("User %s chose to type address instead", session_id)
            return self._request_manual_address(state, session_id)

        else:
            logger.debug("Invalid option '%s' for %s", message, session_id)
            coordinates_text = f"Latitude: {state['temp_coordinates']['latitude']}, Longitude: {state['temp_coordinates']['longitude']}" if state.get("temp_coordinates") else "Coordinates unavailable."
            maps_link_info = f"\n🗺️ *View on Maps:* {state['map_link']}" if state.get("map_link") else ""
            return self.whatsapp_service.create_button_message(
                session_id,
                f"❌ *Invalid option: '{message}'*\n\n{coordinates_text}{maps_link_info}\n\nPlease select an option below:",
                [
                    {"type": "reply", "reply": {"id": "use_coordinates", "title": "✅ Use Coordinates"}},
                    {"type": "reply", "reply": {"id": "type_address_instead", "title": "✏️ Type Address"}}
                ]
            )

    def handle_awaiting_live_location_timeout(self, state: dict, original_message: str, session_id: str):
        """
        Handles text input while awaiting live location.
        """
        if original_message and original_message.strip():
            logger.info("User %s typed '%s' while awaiting live location", session_id, original_message)
            
            stripped_message = original_message.strip()
            if len(stripped_message) >= 5 and any(char.isalpha() for char in stripped_message):
                logger.info("Treating typed message as manual address input for %s", session_id)
                return self.handle_manual_address_input(state, original_message, session_id)
            
            buttons = [
                {"type": "reply", "reply": {"id": "share_current_location", "title": "📍 Try Share Again"}},
                {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Type Address"}},
                {"type": "reply", "reply": {"id": "back_to_menu", "title": "⬅️ Back to Menu"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"⏰ *Still waiting for location...*\n\nYou typed: '{original_message}'\n\nTo use this as your address, click 'Type Address'. Otherwise, please select an option below:",
                buttons
            )
        return None

    def _save_address_to_user_details(self, state: dict, address: str, latitude: float, longitude: float, map_link: str, session_id: str):
        """
        Saves address, latitude, longitude, and map_link to data_manager's user_details.
        """
        logger.debug("Saving address '%s' with lat=%s, lon=%s, map_link='%s' for %s", address, latitude, longitude, map_link, session_id)
        user_data = {
            "name": state.get("user_name", "Guest"),
            "phone_number": session_id,
            "address": address,
            "user_perferred_name": state.get("user_name", "Guest"),
            "address2": "",
            "address3": "",
            "latitude": latitude,
            "longitude": longitude,
            "map_link": map_link
        }
        try:
            self.data_manager.save_user_details(session_id, user_data)
            state["address"] = address
            state["latitude"] = latitude
            state["longitude"] = longitude
            state["map_link"] = map_link
            self.session_manager.update_session_state(session_id, state)
            logger.info("Address and coordinates saved for %s", session_id)
        except Exception as e:
            logger.error("Failed to save address for %s: %s", session_id, e, exc_info=True)

    def _proceed_to_order_confirmation(self, state: dict, session_id: str, address: str, maps_info: str = ""):
        """
        FIXED: Properly handles transitions back to order confirmation.
        """
        # Check if we're coming from order confirmation (address update scenario)
        if state.get("from_confirm_order", False) or state.get("from_confirm_details", False):
            logger.info("Redirecting back to order confirmation after address update for session %s", session_id)
            
            # Save address to user details
            user_data = {
                "name": state.get("user_name", "Guest"),
                "phone_number": session_id,
                "address": address,
                "user_perferred_name": state.get("user_name", "Guest"),
                "address2": "",
                "address3": "",
                "latitude": state.get("latitude"),
                "longitude": state.get("longitude"),
                "map_link": state.get("map_link", "")
            }
            try:
                self.data_manager.save_user_details(session_id, user_data)
                logger.info("Address saved to user details for session %s", session_id)
            except Exception as e:
                logger.error("Failed to save address to user details for %s: %s", session_id, e)
            
            # Update state to go back to order confirmation
            state["current_state"] = "confirm_order"
            state["current_handler"] = "order_handler"
            state["address"] = address
            
            # Clean up flags
            state.pop("from_confirm_order", None)
            state.pop("from_confirm_details", None)
            
            self.session_manager.update_session_state(session_id, state)
            
            # Return redirect to order handler with confirmation
            return {
                "redirect": "order_handler",
                "redirect_message": "show_order_confirmation_after_address_update"
            }

        # For new orders (not address updates), check if cart exists
        if not state.get("cart"):
            logger.warning("Empty cart for session %s, redirecting to greeting", session_id)
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            return {
                "redirect": "greeting_handler",
                "redirect_message": "handle_back_to_main",
                "additional_message": "Your cart is empty. Please add items before confirming an order."
            }

        # For new orders with cart, proceed to order confirmation
        state["current_state"] = "confirm_order"
        state["current_handler"] = "order_handler"
        self.session_manager.update_session_state(session_id, state)
        
        return {
            "redirect": "order_handler",
            "redirect_message": "show_order_confirmation"
        }

    def get_state_handlers(self) -> dict:
        """
        Returns a dictionary mapping state names to handler methods.
        """
        return {
            "address_collection_menu": self.handle_address_collection_menu,
            "address_entry_submenu": self.handle_address_entry_submenu,
            "awaiting_live_location": self.handle_awaiting_live_location_timeout,
            "manual_address_input": self.handle_manual_address_input,
            "confirm_detected_location": self.handle_confirm_detected_location,
            "confirm_coordinates": self.handle_confirm_coordinates
        }