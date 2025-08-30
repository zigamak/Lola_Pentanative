import logging
from .base_handler import BaseHandler
from utils.helpers import format_cart

logger = logging.getLogger(__name__)

class LocationAddressHandler(BaseHandler):
    """
    Handles location-based address collection for the bot, including live location,
    Google Maps searches, manual address entry, and saved addresses.
    """

    def __init__(self, config, session_manager, data_manager, whatsapp_service, location_service):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
        self.location_service = location_service
        logger.debug("LocationAddressHandler initialized with phone_number_id: %s", config.WHATSAPP_PHONE_NUMBER_ID)

    def initiate_address_collection(self, state: dict, session_id: str):
        """
        Starts address collection with options tailored to context. Limits to live location
        and manual entry when called from confirm_order state.
        """
        state["current_state"] = "address_collection_menu"
        from_confirm_order = state.get("from_confirm_order", False)

        buttons = [
            {"type": "reply", "reply": {"id": "share_current_location", "title": "📍 Share Location"}},  # 15 chars
            {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Type Address"}}    # 13 chars
        ]

        if not from_confirm_order:
            if self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
                buttons.append({
                    "type": "reply",
                    "reply": {"id": "search_on_maps", "title": "🗺️ Search Maps"}  # 13 chars
                })
            if state.get("address"):
                buttons.append({
                    "type": "reply",
                    "reply": {"id": "use_saved_address", "title": "🏠 Saved Address"}  # 14 chars
                })

        # Validate button titles
        for button in buttons:
            title = button["reply"]["title"]
            if len(title) > 20:
                logger.error("Button title exceeds 20 chars: %s", title)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "Error: Invalid button configuration. Please try again or contact support."
                )

        saved_address_text = f"\n\n🏠 *Last address:* {state['address']}" if state.get("address") and not from_confirm_order else ""
        message = f"📍 *Provide delivery address*{saved_address_text}\n\nPlease select an option below:"
        logger.debug("Initiating address collection for session %s, from_confirm_order: %s, buttons: %s", session_id, from_confirm_order, buttons)
        return self.whatsapp_service.create_button_message(session_id, message, buttons)

    def handle_address_collection_menu(self, state: dict, message: str, session_id: str):
        """
        Handles user's selection from the address collection menu.
        """
        logger.debug("Handling address collection menu for session %s, message: %s", session_id, message)
        
        # Handle the case where user comes from order handler with "update_address"
        if message == "update_address":
            logger.info("Received update_address redirect from order handler for session %s", session_id)
            # Show the address collection menu instead of processing as invalid option
            return self.initiate_address_collection(state, session_id)
        
        # Handle normal address collection menu options
        if message == "share_current_location":
            return self._request_live_location(state, session_id)
        elif message == "search_on_maps":
            if self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
                return self._initiate_maps_search(state, session_id)
            logger.warning("Maps search selected but not enabled for session %s", session_id)
            return self._request_manual_address(state, session_id)
        elif message == "type_address_manually":
            return self._request_manual_address(state, session_id)
        elif message == "use_saved_address":
            return self._use_saved_address(state, session_id)
        elif message == "back_to_menu":
            # Handle back to menu option when coming from awaiting live location
            return self.initiate_address_collection(state, session_id)
        elif message == "share_location":
            # Alternative way to trigger location sharing
            return self._request_live_location(state, session_id)
        else:
            logger.debug("Invalid option '%s' for session %s", message, session_id)
            buttons = [
                {"type": "reply", "reply": {"id": "share_current_location", "title": "📍 Share Location"}},  # 15 chars
                {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Type Address"}}    # 13 chars
            ]
            if not state.get("from_confirm_order", False):
                if self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
                    buttons.append({"type": "reply", "reply": {"id": "search_on_maps", "title": "🗺️ Search Maps"}})
                if state.get("address"):
                    buttons.append({"type": "reply", "reply": {"id": "use_saved_address", "title": "🏠 Saved Address"}})
            
            return self.whatsapp_service.create_button_message(
                session_id,
                f"❌ *Invalid option: '{message}'*\n\nPlease select an option below:",
                buttons
            )
    def _request_live_location(self, state: dict, session_id: str):
        """
        Prompts user to share live location via WhatsApp.
        """
        state["current_state"] = "awaiting_live_location"
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

    def _initiate_maps_search(self, state: dict, session_id: str):
        """
        Prompts user to type a search query for Google Maps.
        """
        state["current_state"] = "maps_search_input"
        self.session_manager.update_session_state(session_id, state)
        logger.info("Initiated Maps search for session %s", session_id)
        return self.whatsapp_service.create_text_message(
            session_id,
            "🗺️ *Search Address*\n\n" +
            "Type a place, landmark, or address.\n\n" +
            "*Examples:*\n" +
            "• Silverbird Cinemas Abuja\n" +
            "• Plot 123 Gwarinpa Estate\n" +
            "• University of Abuja\n\n" +
            "What’s your location?"
        )

    def _request_manual_address(self, state: dict, session_id: str):
        """
        Prompts user to manually type their delivery address.
        """
        state["current_state"] = "manual_address_input"
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

        maps_info = ""
        if self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key() and state.get("map_link"):
            maps_info = f"\n🗺️ *View on Maps:* {state['map_link']}"

        logger.info("Using saved address for session %s: %s", session_id, state["address"])
        return self._proceed_to_order_confirmation(state, session_id, state["address"], maps_info)

    def handle_live_location(self, state: dict, session_id: str, latitude: float, longitude: float, location_name: str = None, location_address: str = None):
        """
        Processes live location data from WhatsApp.
        """
        logger.info("Processing live location for %s: Lat=%s, Lon=%s, Name='%s', Address='%s'", session_id, latitude, longitude, location_name, location_address)

        if not latitude or not longitude:
            logger.warning("Invalid location data for session %s", session_id)
            return self.whatsapp_service.create_text_message(
                session_id,
                "❌ *Invalid location*\n\nPlease select an option below:",
                [
                    {"type": "reply", "reply": {"id": "share_current_location", "title": "📍 Try Share Again"}},  # 16 chars
                    {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Type Address"}}    # 13 chars
                ]
            )

        readable_address = location_address
        map_link = ""
        if (not readable_address or "unknown" in readable_address.lower()) and \
           self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
            geocoded_address = self.location_service.get_address_from_coordinates(latitude, longitude)
            if geocoded_address:
                readable_address = geocoded_address
                map_link = self.location_service.generate_maps_link(readable_address)
                logger.info("Geocoded coordinates %s,%s to address: %s", latitude, longitude, readable_address)
            else:
                logger.warning("Could not geocode coordinates %s,%s for %s", session_id)
                map_link = self.location_service.generate_maps_link_from_coordinates(latitude, longitude)

        if readable_address:
            state["address"] = readable_address
            state["latitude"] = latitude
            state["longitude"] = longitude
            state["map_link"] = map_link if map_link else self.location_service.generate_maps_link(readable_address)
            self._save_address_to_user_details(state, readable_address, latitude, longitude, map_link, session_id)

            location_info = self.location_service.format_location_info(latitude, longitude, readable_address)
            buttons = [
                {"type": "reply", "reply": {"id": "confirm_location", "title": "✅ Use Address"}},  # 12 chars
                {"type": "reply", "reply": {"id": "choose_different", "title": "📍 Choose Another"}}  # 15 chars
            ]

            state["current_state"] = "confirm_detected_location"
            self.session_manager.update_session_state(session_id, state)
            logger.info("Live location processed for %s. Awaiting confirmation.", session_id)
            return self.whatsapp_service.create_button_message(
                session_id,
                f"🎯 *Location Detected!*\n\n{location_info}\n\nPlease select an option below:",
                buttons
            )
        else:
            coordinates_text = f"Latitude: {latitude}, Longitude: {longitude}"
            maps_link_info = ""
            if self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
                map_link = self.location_service.generate_maps_link_from_coordinates(latitude, longitude)
                maps_link_info = f"\n🗺️ *View on Maps:* {map_link}"

            buttons = [
                {"type": "reply", "reply": {"id": "use_coordinates", "title": "✅ Use Coordinates"}},  # 16 chars
                {"type": "reply", "reply": {"id": "type_address_instead", "title": "✏️ Type Address"}}  # 13 chars
            ]

            state["temp_coordinates"] = {"latitude": latitude, "longitude": longitude}
            state["map_link"] = map_link
            state["current_state"] = "confirm_coordinates"
            self.session_manager.update_session_state(session_id, state)
            logger.warning("No readable address for %s from %s,%s. Awaiting coordinates confirmation.", session_id, latitude, longitude)
            return self.whatsapp_service.create_button_message(
                session_id,
                f"📍 *Location Received*\n\n{coordinates_text}{maps_link_info}\n\nPlease select an option below:",
                buttons
            )

    def handle_maps_search_input(self, state: dict, original_message: str, session_id: str):
        """
        Handles user's Google Maps search query input.
        """
        search_query = original_message.strip()
        logger.debug("Handling Maps search for %s: '%s'", session_id, search_query)

        if not search_query:
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please enter a valid search term.\n\nPlease select an option below:",
                [
                    {"type": "reply", "reply": {"id": "search_on_maps", "title": "🔍 Search Again"}},  # 14 chars
                    {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Type Address"}}  # 13 chars
                ]
            )

        if not (self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key()):
            logger.error("Maps search attempted by %s but API not enabled.", session_id)
            state["current_state"] = "manual_address_input"
            self.session_manager.update_session_state(session_id, state)
            return self._request_manual_address(state, session_id)

        coordinates = self.location_service.get_coordinates_from_address(search_query)
        if coordinates:
            latitude, longitude = coordinates
            formatted_address = self.location_service.get_address_from_coordinates(latitude, longitude)
            map_link = self.location_service.generate_maps_link(formatted_address or search_query)

            if formatted_address:
                state["temp_address"] = formatted_address
                state["temp_coordinates"] = {"latitude": latitude, "longitude": longitude}
                state["map_link"] = map_link
                state["current_state"] = "confirm_maps_result"
                self.session_manager.update_session_state(session_id, state)

                location_info = self.location_service.format_location_info(latitude, longitude, formatted_address)
                buttons = [
                    {"type": "reply", "reply": {"id": "use_maps_result", "title": "✅ Use Address"}},  # 12 chars
                    {"type": "reply", "reply": {"id": "search_again", "title": "🔍 Search Again"}},  # 14 chars
                    {"type": "reply", "reply": {"id": "type_manually", "title": "✏️ Type Address"}}  # 13 chars
                ]
                logger.info("Maps search found result for '%s' for %s.", search_query, session_id)
                return self.whatsapp_service.create_button_message(
                    session_id,
                    f"🎯 *Found Location!*\n\n{location_info}\n\nPlease select an option below:",
                    buttons
                )
            else:
                logger.warning("Maps search found coordinates but no address for '%s' for %s.", search_query, session_id)
                return self._handle_maps_search_with_coordinates_only(state, session_id, latitude, longitude, search_query)
        else:
            logger.info("Maps search failed for '%s' for %s.", search_query, session_id)
            return self._handle_search_failure(session_id, search_query)

    def _handle_maps_search_with_coordinates_only(self, state: dict, session_id: str, latitude: float, longitude: float, search_query: str):
        """
        Handles Maps search yielding coordinates but no readable address.
        """
        coordinates_text = f"Latitude: {latitude}, Longitude: {longitude}"
        map_link = self.location_service.generate_maps_link_from_coordinates(latitude, longitude)

        buttons = [
            {"type": "reply", "reply": {"id": "use_coordinates", "title": "✅ Use Coordinates"}},  # 16 chars
            {"type": "reply", "reply": {"id": "type_address_instead", "title": "✏️ Type Address"}}  # 13 chars
        ]

        state["temp_coordinates"] = {"latitude": latitude, "longitude": longitude}
        state["map_link"] = map_link
        state["current_state"] = "confirm_coordinates"
        self.session_manager.update_session_state(session_id, state)
        return self.whatsapp_service.create_button_message(
            session_id,
            f"📍 *Location Found:*\n\nFound for '{search_query}':\n{coordinates_text}\n🗺️ *View on Maps:* {map_link}\n\nPlease select an option below:",
            buttons
        )

    def _handle_search_failure(self, session_id: str, search_query: str):
        """
        Handles failed Google Maps search.
        """
        buttons = [
            {"type": "reply", "reply": {"id": "share_location", "title": "📍 Share Location"}},  # 15 chars
            {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Type Address"}}  # 13 chars
        ]

        return self.whatsapp_service.create_button_message(
            session_id,
            f"🤔 *Couldn't find: '{search_query}'*\n\nPossible issues:\n" +
            "• New or unknown location\n• Typo in name\n• Local landmark\n\nPlease select an option below:",
            buttons
        )

    def handle_manual_address_input(self, state: dict, original_message: str, session_id: str):
        """
        Handles manual address input with validation and geocoding.
        """
        address = original_message.strip()
        logger.debug("Handling manual address for %s: '%s'", session_id, address)

        if len(address) < 10 or (not any(char.isdigit() for char in address) and not any(char.isalpha() for char in address)):
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

        # Process and save the address
        location_coordinates = None
        map_link = ""
        if self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
            coordinates = self.location_service.get_coordinates_from_address(address)
            if coordinates:
                latitude, longitude = coordinates
                location_coordinates = {"latitude": latitude, "longitude": longitude}
                map_link = self.location_service.generate_maps_link(address)
                logger.info("Geocoded address '%s' to: %s", address, location_coordinates)
                
                # Update state with coordinates
                state["latitude"] = latitude
                state["longitude"] = longitude
            else:
                logger.warning("Could not geocode address '%s' for %s", address, session_id)

        # Save to user details and update state
        self._save_address_to_user_details(state, address, 
                                        location_coordinates.get("latitude") if location_coordinates else None,
                                        location_coordinates.get("longitude") if location_coordinates else None,
                                        map_link, session_id)

        logger.info("Manual address '%s' processed for %s", address, session_id)
        
        # Return to order confirmation
        maps_info = f"\n🗺️ *View on Maps:* {map_link}" if map_link else ""
        return self._proceed_to_order_confirmation(state, session_id, address, maps_info)

    def handle_confirm_detected_location(self, state: dict, message: str,

 session_id: str):
        """
        Handles confirmation of detected location.
        """
        logger.debug("Handling confirm detected location for %s, message: %s", session_id, message)
        if message == "confirm_location":
            self._save_address_to_user_details(state, state["address"], 
                                            state["location_coordinates"]["latitude"] if state.get("location_coordinates") else None,
                                            state["location_coordinates"]["longitude"] if state.get("location_coordinates") else None,
                                            state.get("map_link", ""), session_id)
            maps_info = ""
            if state.get("location_coordinates") and state.get("address") and \
               self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
                coords = state["location_coordinates"]
                maps_info = f"\n{self.location_service.format_location_info(coords['latitude'], coords['longitude'], state['address'])}"

            logger.info("Confirmed location for %s: %s", session_id, state.get("address"))
            return self._proceed_to_order_confirmation(state, session_id, state["address"], maps_info)

        elif message == "choose_different":
            state.pop("location_coordinates", None)
            state.pop("address", None)
            state.pop("map_link", None)
            self.session_manager.update_session_state(session_id, state)
            logger.info("User %s chose different address method", session_id)
            return self.initiate_address_collection(state, session_id)

        else:
            logger.debug("Invalid option '%s' for %s", message, session_id)
            location_info = self.location_service.format_location_info(
                state["location_coordinates"]["latitude"],
                state["location_coordinates"]["longitude"],
                state["address"]
            ) if state.get("location_coordinates") and state.get("address") else "Location data unavailable."
            return self.whatsapp_service.create_button_message(
                session_id,
                f"❌ *Invalid option: '{message}'*\n\n{location_info}\n\nPlease select an option below:",
                [
                    {"type": "reply", "reply": {"id": "confirm_location", "title": "✅ Use Address"}},  # 12 chars
                    {"type": "reply", "reply": {"id": "choose_different", "title": "📍 Choose Another"}}  # 15 chars
                ]
            )

    def handle_confirm_maps_result(self, state: dict, message: str, session_id: str):
        """
        Handles confirmation of Google Maps search result.
        """
        logger.debug("Handling confirm Maps result for %s, message: %s", session_id, message)
        if message == "use_maps_result":
            if not state.get("temp_address") or not state.get("temp_coordinates"):
                logger.error("Missing temp address/coordinates for %s", session_id)
                return self._initiate_maps_search(state, session_id)

            state["address"] = state["temp_address"]
            state["latitude"] = state["temp_coordinates"]["latitude"]
            state["longitude"] = state["temp_coordinates"]["longitude"]
            state["map_link"] = state.get("map_link", "")
            self._save_address_to_user_details(state, state["address"], 
                                            state["temp_coordinates"]["latitude"],
                                            state["temp_coordinates"]["longitude"],
                                            state["map_link"], session_id)

            coords = state["temp_coordinates"]
            maps_info = self.location_service.format_location_info(coords["latitude"], coords["longitude"], state["address"])
            state.pop("temp_address", None)
            state.pop("temp_coordinates", None)
            self.session_manager.update_session_state(session_id, state)

            logger.info("Confirmed Maps result for %s: %s", session_id, state["address"])
            return self._proceed_to_order_confirmation(state, session_id, state["address"], f"\n{maps_info}")

        elif message == "search_again":
            state.pop("temp_address", None)
            state.pop("temp_coordinates", None)
            state.pop("map_link", None)
            self.session_manager.update_session_state(session_id, state)
            logger.info("User %s chose to search Maps again", session_id)
            return self._initiate_maps_search(state, session_id)

        elif message == "type_manually":
            state.pop("temp_address", None)
            state.pop("temp_coordinates", None)
            state.pop("map_link", None)
            self.session_manager.update_session_state(session_id, state)
            logger.info("User %s chose to type address manually", session_id)
            return self._request_manual_address(state, session_id)

        else:
            logger.debug("Invalid option '%s' for %s", message, session_id)
            location_info = self.location_service.format_location_info(
                state["temp_coordinates"]["latitude"],
                state["temp_coordinates"]["longitude"],
                state["temp_address"]
            ) if state.get("temp_coordinates") and state.get("temp_address") else "Location data unavailable."
            return self.whatsapp_service.create_button_message(
                session_id,
                f"❌ *Invalid option: '{message}'*\n\n{location_info}\n\nPlease select an option below:",
                [
                    {"type": "reply", "reply": {"id": "use_maps_result", "title": "✅ Use Address"}},  # 12 chars
                    {"type": "reply", "reply": {"id": "search_again", "title": "🔍 Search Again"}},  # 14 chars
                    {"type": "reply", "reply": {"id": "type_manually", "title": "✏️ Type Address"}}  # 13 chars
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
                    {"type": "reply", "reply": {"id": "use_coordinates", "title": "✅ Use Coordinates"}},  # 16 chars
                    {"type": "reply", "reply": {"id": "type_address_instead", "title": "✏️ Type Address"}}  # 13 chars
                ]
            )

    def handle_awaiting_live_location_timeout(self, state: dict, original_message: str, session_id: str):
        """
        Handles text input while awaiting live location.
        """
        if original_message and original_message.strip():
            logger.info("User %s typed '%s' while awaiting live location", session_id, original_message)
            buttons = [
                {"type": "reply", "reply": {"id": "share_current_location", "title": "📍 Try Share Again"}},  # 16 chars
                {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Type Address"}},    # 13 chars
                {"type": "reply", "reply": {"id": "back_to_menu", "title": "⬅️ Back to Menu"}}          # 14 chars
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"⏰ *Waiting for location...*\n\nYou typed '{original_message}'.\n\nPlease select an option below:",
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
            # Update state to ensure persistence
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
        Transitions to order confirmation, redirecting to OrderHandler if from confirm_order.
        """
        if state.get("from_confirm_order", False):
            logger.info("Redirecting to OrderHandler for session %s after address update", session_id)
            
            # Update state with the new address information
            state["address"] = address
            state["map_link"] = maps_info.replace("\n🗺️ *View on Maps:* ", "") if maps_info and "🗺️ *View on Maps:* " in maps_info else ""
            
            # Save to user details for persistence
            user_data = {
                "name": state.get("user_name", "Guest"),
                "phone_number": session_id,
                "address": address,
                "user_perferred_name": state.get("user_name", "Guest"),
                "address2": "",
                "address3": "",
                "latitude": state.get("latitude"),
                "longitude": state.get("longitude"),
                "map_link": state["map_link"]
            }
            try:
                self.data_manager.save_user_details(session_id, user_data)
                logger.info("Address saved to user details for session %s", session_id)
            except Exception as e:
                logger.error("Failed to save address to user details for %s: %s", session_id, e)
            
            # Prepare for return to order handler
            state["current_state"] = "confirm_order"
            state["current_handler"] = "order_handler"
            state.pop("from_confirm_order", None)  # Remove the flag to prevent loops
            self.session_manager.update_session_state(session_id, state)
            
            # Create confirmation message with updated address
            cart_summary = format_cart(state.get("cart", {}))
            total_amount = sum(
                item_data.get("total_price", item_data.get("quantity", 1) * item_data.get("price", 0.0))
                for item_data in state.get("cart", {}).values()
            )
            user_name = state.get("user_name", "Guest")
            phone_number = state.get("phone_number", session_id)
            latitude = state.get("latitude")
            longitude = state.get("longitude")
            map_link = state.get("map_link", "")
            
            confirmation_message = (
                f"✅ *Address Updated Successfully!*\n\n"
                f"🛒 *Order Confirmation*\n\n"
                f"📦 *Items Ordered:*\n{cart_summary}\n\n"
                f"📍 *Delivery Details:*\n"
                f"👤 Name: {user_name}\n"
                f"📱 Phone: {phone_number}\n"
                f"🏠 Address: {address}\n"
                f"🌍 Coordinates: {'Lat: ' + str(latitude) + ', Lon: ' + str(longitude) if latitude and longitude else 'Not set'}\n"

                f"📝 Note: {state.get('order_note', 'None')}\n"
                f"\n💰 *Total Amount: ₦{total_amount:,.2f}*\n\n"
                f"Please review and select an option below:"
            )
            
            buttons = [
                {"type": "reply", "reply": {"id": "final_confirm", "title": "✅ Confirm & Pay"}},  # 14 chars
                {"type": "reply", "reply": {"id": "update_address", "title": "📍 Update Address"}},  # 15 chars
                {"type": "reply", "reply": {"id": "add_note", "title": "📝 Add Note"}},  # 11 chars
                
            ]
            
            return {
                "redirect": "order_handler",
                "redirect_message": "handle_confirm_order_state",
                "additional_message": confirmation_message,
                "buttons": buttons
            }

        # Handle non-confirm_order cases (regular address collection flow)
        if not state.get("cart"):
            logger.warning("Empty cart for session %s", session_id)
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            return {
                "redirect": "menu_handler",
                "redirect_message": "handle_menu_selection",
                "additional_message": "Your cart is empty. Please add items before confirming an order."
            }

        # Regular flow - show order confirmation via OrderHandler
        state["current_state"] = "confirm_order"
        state["current_handler"] = "order_handler"
        self.session_manager.update_session_state(session_id, state)
        
        # Create confirmation message for regular flow
        cart_summary = format_cart(state.get("cart", {}))
        total_amount = sum(
            item_data.get("total_price", item_data.get("quantity", 1) * item_data.get("price", 0.0))
            for item_data in state.get("cart", {}).values()
        )
        user_name = state.get("user_name", "Guest")
        phone_number = state.get("phone_number", session_id)
        latitude = state.get("latitude")
        longitude = state.get("longitude")
        map_link = state.get("map_link", "")
        
        confirmation_message = (
            f"✅ *Address Confirmed!*\n\n"
            f"🛒 *Order Confirmation*\n\n"
            f"📦 *Items Ordered:*\n{cart_summary}\n\n"
            f"📍 *Delivery Details:*\n"
            f"👤 Name: {user_name}\n"
            f"📱 Phone: {phone_number}\n"
            f"🏠 Address: {address}\n"
            f"🌍 Coordinates: {'Lat: ' + str(latitude) + ', Lon: ' + str(longitude) if latitude and longitude else 'Not set'}\n"
            f"🗺️ Map Link: {map_link or 'Not set'}\n"
            f"📝 Note: {state.get('order_note', 'None')}\n"
            f"\n💰 *Total Amount: ₦{total_amount:,.2f}*\n\n"
            f"Please review and select an option below:"
        )
        
        buttons = [
            {"type": "reply", "reply": {"id": "final_confirm", "title": "✅ Confirm & Pay"}},  # 14 chars
            {"type": "reply", "reply": {"id": "update_address", "title": "📍 Update Address"}},  # 15 chars
            {"type": "reply", "reply": {"id": "add_note", "title": "📝 Add Note"}},  # 11 chars
            {"type": "reply", "reply": {"id": "cancel_order", "title": "❌ Cancel Order"}}  # 14 chars
        ]
        
        return {
            "redirect": "order_handler",
            "redirect_message": "handle_confirm_order_state",
            "additional_message": confirmation_message,
            "buttons": buttons
        }

    def get_state_handlers(self) -> dict:
        """
        Returns a dictionary mapping state names to handler methods.
        """     
        return {
            "address_collection_menu": self.handle_address_collection_menu,
            "awaiting_live_location": self.handle_awaiting_live_location_timeout,
            "maps_search_input": self.handle_maps_search_input,
            "manual_address_input": self.handle_manual_address_input,
            "confirm_detected_location": self.handle_confirm_detected_location,
            "confirm_maps_result": self.handle_confirm_maps_result,
            "confirm_coordinates": self.handle_confirm_coordinates
        }