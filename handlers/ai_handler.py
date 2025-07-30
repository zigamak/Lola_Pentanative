import logging
from utils.helpers import format_cart # Assuming format_cart is in utils/helpers.py

logger = logging.getLogger(__name__)

class LocationAddressHandler:
    """
    Handles all location-based address collection functionality for the bot.
    This includes offering options for address input, processing live locations,
    handling Google Maps searches, manual address entry, and using saved addresses.
    """

    def __init__(self, config, whatsapp_service, location_service, data_manager):
        self.config = config
        self.whatsapp_service = whatsapp_service
        self.location_service = location_service # Instance of LocationService
        self.data_manager = data_manager # Instance of DataManager
        logger.info("LocationAddressHandler initialized.")

    def initiate_address_collection(self, state: dict, session_id: str):
        """
        Starts the enhanced address collection process by presenting the user
        with multiple options for providing their delivery address.
        """
        state["current_state"] = "address_collection_menu"
        # The MessageProcessor should be responsible for calling session_manager.update_session_state
        # after this method returns, so we don't call it here.

        buttons = []

        # Always offer live location and manual typing, as they don't depend on Google Maps API key
        buttons.append({
            "type": "reply",
            "reply": {"id": "share_current_location", "title": "📍 Share Current Location"}
        })

        # Conditionally add Google Maps search option based on config and API key validation
        if self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
            buttons.append({
                "type": "reply",
                "reply": {"id": "search_on_maps", "title": "🗺️ Search on Google Maps"}
            })

        buttons.append({
            "type": "reply",
            "reply": {"id": "type_address_manually", "title": "✏️ Type Address Manually"}
        })

        # Add saved address option if a previous address is stored in the session state
        if state.get("address"):
            buttons.append({
                "type": "reply",
                "reply": {"id": "use_saved_address", "title": "🏠 Use Saved Address"}
            })

        saved_address_text = ""
        if state.get("address"):
            saved_address_text = f"\n\n🏠 *Your last used address:* {state['address']}"

        logger.debug(f"Initiating address collection menu for session {session_id}. Current address: {state.get('address')}")
        return self.whatsapp_service.create_button_message(
            session_id,
            f"📍 *How would you like to provide your delivery address?*{saved_address_text}\n\nChoose the most convenient option:",
            buttons
        )

    def handle_address_collection_menu(self, state: dict, message: str, session_id: str):
        """
        Handles the user's selection from the address collection menu.
        Routes to the appropriate sub-handler or re-prompts for valid input.
        """
        logger.debug(f"Handling address collection menu for session {session_id}, message: {message}")
        if message == "share_current_location":
            return self._request_live_location(state, session_id)
        elif message == "search_on_maps":
            # Guard against Maps search if not enabled/configured
            if self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
                return self._initiate_maps_search(state, session_id)
            else:
                logger.warning(f"User {session_id} selected Maps search but it's not enabled or API key is invalid. Redirecting to manual entry.")
                self.whatsapp_service.create_text_message(
                    session_id,
                    "Maps search is currently unavailable. Please type your address manually."
                )
                return self._request_manual_address(state, session_id) # Redirect to manual entry
        elif message == "type_address_manually":
            return self._request_manual_address(state, session_id)
        elif message == "use_saved_address":
            return self._use_saved_address(state, session_id)
        else:
            # Invalid selection, show menu again
            logger.debug(f"Invalid option '{message}' selected in address collection menu for session {session_id}.")
            self.whatsapp_service.create_text_message(session_id, "Please choose a valid option from the menu.")
            return self.initiate_address_collection(state, session_id)

    def _request_live_location(self, state: dict, session_id: str):
        """
        Sends instructions to the user on how to share their live location via WhatsApp.
        Updates the session state to 'awaiting_live_location'.
        """
        state["current_state"] = "awaiting_live_location"
        logger.info(f"Requested live location from session {session_id}.")
        return self.whatsapp_service.create_text_message(
            session_id,
            "📍 *Share Your Current Location*\n\n" +
            "To share your location with me:\n\n" +
            "1️⃣ Tap the *attachment* (📎) button below\n" +
            "2️⃣ Select *'Location'* from the menu\n" +
            "3️⃣ Choose *'Send your current location'*\n\n" +
            "✨ I'll automatically convert your location to a readable address!\n\n" +
            "⏰ *Waiting for your location...*"
        )

    def _initiate_maps_search(self, state: dict, session_id: str):
        """
        Prompts the user to type a search query for Google Maps.
        Updates the session state to 'maps_search_input'.
        """
        state["current_state"] = "maps_search_input"
        logger.info(f"Initiated Google Maps search for session {session_id}.")
        return self.whatsapp_service.create_text_message(
            session_id,
            "🗺️ *Search for Your Address*\n\n" +
            "Type the name of a place, landmark, or address and I'll find it on Google Maps.\n\n" +
            "*Examples:*\n" +
            "• 'Silverbird Cinemas Abuja'\n" +
            "• 'National Stadium Abuja'\n" +
            "• 'Shoprite Jabi'\n" +
            "• 'Plot 123 Gwarinpa Estate'\n" +
            "• 'University of Abuja'\n\n" +
            "What would you like to search for?"
        )

    def _request_manual_address(self, state: dict, session_id: str):
        """
        Prompts the user to manually type their complete delivery address.
        Updates the session state to 'manual_address_entry'.
        """
        state["current_state"] = "manual_address_entry"
        logger.info(f"Requested manual address entry from session {session_id}.")
        return self.whatsapp_service.create_text_message(
            session_id,
            "✏️ *Type Your Address Manually*\n\n" +
            "Please provide your complete delivery address:\n\n" +
            "*Please include:*\n" +
            "• House/Plot number\n" +
            "• Street name\n" +
            "• Area/District\n" +
            "• City/State\n\n" +
            "*Example:* 123 Main Street, Wuse 2, Abuja, FCT"
        )

    def _use_saved_address(self, state: dict, session_id: str):
        """
        Attempts to use the previously saved address from the session state.
        If no address is saved, it redirects back to the address collection menu.
        """
        if not state.get("address"):
            logger.warning(f"User {session_id} tried to use saved address but none found. Redirecting to menu.")
            self.whatsapp_service.create_text_message(session_id, "You don't have a saved address. Please choose another option.")
            return self.initiate_address_collection(state, session_id)

        # Generate maps link if location service is enabled and API key is valid
        maps_info = ""
        if self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
            maps_link = self.location_service.generate_maps_link(state["address"])
            maps_info = f"\n🗺️ *View on Maps:* {maps_link}"

        logger.info(f"User {session_id} chose to use saved address: {state['address']}.")
        return self._proceed_to_order_confirmation(state, session_id, state["address"], maps_info)

    def handle_live_location(self, state: dict, session_id: str, latitude: float, longitude: float, location_name: str = None, location_address: str = None):
        """
        Handles the actual location data received from a WhatsApp 'location' message.
        Attempts to geocode the coordinates to a readable address.
        """
        logger.info(f"Processing live location for {session_id}: Lat={latitude}, Lon={longitude}, Name='{location_name}', Address='{location_address}'")

        if not latitude or not longitude:
            logger.warning(f"Invalid (missing lat/lon) location data received from {session_id}.")
            return self.whatsapp_service.create_text_message(
                session_id,
                "❌ *Invalid location received*\n\nPlease try sharing your location again, or choose a different option from the menu."
            )

        # Try to get readable address from coordinates if not provided by WhatsApp or if it's generic
        readable_address = location_address # WhatsApp often provides a preliminary address string
        
        # If WhatsApp's provided address is missing or too vague, try Google Geocoding
        if (not readable_address or "unknown" in readable_address.lower()) and \
           self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
            geocoded_address = self.location_service.get_address_from_coordinates(latitude, longitude)
            if geocoded_address:
                readable_address = geocoded_address
                logger.info(f"Geocoded coordinates {latitude},{longitude} to address: {readable_address}")
            else:
                logger.warning(f"Could not geocode address from coordinates {latitude},{longitude} for {session_id}.")

        if readable_address:
            # Store the confirmed address and coordinates in the session state
            state["address"] = readable_address
            state["location_coordinates"] = {"latitude": latitude, "longitude": longitude}

            # Save the address to data_manager's user_details for persistence
            self._save_address_to_user_details(state, readable_address, session_id)

            # Prepare confirmation message with location details and maps link
            location_info = self.location_service.format_location_info(latitude, longitude, readable_address)

            buttons = [
                {"type": "reply", "reply": {"id": "confirm_location", "title": "✅ Use This Address"}},
                {"type": "reply", "reply": {"id": "choose_different", "title": "📍 Choose Different Address"}}
            ]

            state["current_state"] = "confirm_detected_location"
            logger.info(f"Live location processed for {session_id}. Asking for confirmation.")
            return self.whatsapp_service.create_button_message(
                session_id,
                f"🎯 *Location Detected!*\n\n{location_info}\n\nIs this the correct address for your delivery?",
                buttons
            )
        else:
            # Fallback when no readable address can be determined (even after geocoding)
            coordinates_text = f"Latitude: {latitude}, Longitude: {longitude}"
            maps_link_info = ""
            if self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
                maps_link = self.location_service.generate_maps_link_from_coordinates(latitude, longitude)
                maps_link_info = f"\n🗺️ *View on Maps:* {maps_link}"

            buttons = [
                {"type": "reply", "reply": {"id": "use_coordinates", "title": "✅ Use These Coordinates"}},
                {"type": "reply", "reply": {"id": "type_address_instead", "title": "✏️ Type Address Instead"}}
            ]

            state["temp_coordinates"] = {"latitude": latitude, "longitude": longitude} # Store temporarily
            state["current_state"] = "confirm_coordinates" # Set state for confirmation of coordinates

            logger.warning(f"Could not determine readable address for {session_id} from {latitude},{longitude}. Asking to confirm coordinates or type manually.")
            return self.whatsapp_service.create_button_message(
                session_id,
                f"📍 *Location Received*\n\n{coordinates_text}{maps_link_info}\n\nI couldn't determine the exact address from your location. Would you like to proceed with just the coordinates, or type your address manually?",
                buttons
            )

    def handle_maps_search_input(self, state: dict, original_message: str, session_id: str):
        """
        Handles the user's text input for a Google Maps search query.
        Attempts to geocode the query and presents results for confirmation.
        """
        search_query = original_message.strip()
        logger.debug(f"Handling Maps search input for {session_id}: '{search_query}'")

        if not search_query:
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please enter a valid search term to find your location."
            )

        # Double-check if Maps features are enabled/configured, though menu should prevent this path
        if not (self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key()):
            logger.error(f"Maps search attempted by {session_id} but Google Maps API is not enabled/configured. This path should be unreachable.")
            state["current_state"] = "manual_address_entry" # Fallback
            return self.whatsapp_service.create_text_message(
                session_id,
                "Maps search is currently unavailable. Please type your complete address manually."
            )

        # Use LocationService to get coordinates from the search query
        coordinates = self.location_service.get_coordinates_from_address(search_query)

        if coordinates:
            latitude, longitude = coordinates
            # Reverse geocode to get a well-formatted address from the found coordinates
            formatted_address = self.location_service.get_address_from_coordinates(latitude, longitude)

            if formatted_address:
                # Store results temporarily for confirmation
                state["temp_address"] = formatted_address
                state["temp_coordinates"] = {"latitude": latitude, "longitude": longitude}
                state["current_state"] = "confirm_maps_result"

                # Prepare confirmation message
                location_info = self.location_service.format_location_info(latitude, longitude, formatted_address)

                buttons = [
                    {"type": "reply", "reply": {"id": "use_maps_result", "title": "✅ Use This Address"}},
                    {"type": "reply", "reply": {"id": "search_again", "title": "🔍 Search Again"}},
                    {"type": "reply", "reply": {"id": "type_manually", "title": "✏️ Type Manually"}}
                ]
                logger.info(f"Maps search found result for '{search_query}' for {session_id}. Asking for confirmation.")
                return self.whatsapp_service.create_button_message(
                    session_id,
                    f"🎯 *Found Location!*\n\n{location_info}\n\nIs this the correct address for your delivery?",
                    buttons
                )
            else:
                logger.warning(f"Maps search found coordinates but no formatted address for '{search_query}' for {session_id}.")
                # Fallback to handle search where coordinates are found but address is not
                return self._handle_maps_search_with_coordinates_only(state, session_id, latitude, longitude, search_query)
        else:
            # Search failed completely
            logger.info(f"Maps search failed for '{search_query}' for {session_id}.")
            return self._handle_search_failure(session_id, search_query)

    def _handle_maps_search_with_coordinates_only(self, state: dict, session_id: str, latitude: float, longitude: float, search_query: str):
        """
        Handles case where Maps search yields coordinates but no readable address.
        Presents user with options to use coordinates or try manual entry.
        """
        coordinates_text = f"Latitude: {latitude}, Longitude: {longitude}"
        maps_link = self.location_service.generate_maps_link_from_coordinates(latitude, longitude)

        buttons = [
            {"type": "reply", "reply": {"id": "use_coordinates", "title": "✅ Use These Coordinates"}},
            {"type": "reply", "reply": {"id": "type_address_instead", "title": "✏️ Type Address Instead"}}
        ]

        state["temp_coordinates"] = {"latitude": latitude, "longitude": longitude}
        state["current_state"] = "confirm_coordinates" # Reuse confirmation state for coordinates

        return self.whatsapp_service.create_button_message(
            session_id,
            f"📍 *Location Found (by Search):*\n\nI found coordinates for '{search_query}' but couldn't get a full address:\n{coordinates_text}\n🗺️ *View on Maps:* {maps_link}\n\nWould you like to proceed with just these coordinates, or type your address manually?",
            buttons
        )

    def _handle_search_failure(self, session_id: str, search_query: str):
        """
        Provides options to the user when a Google Maps search yields no results.
        """
        buttons = [
            {'type': 'reply', 'reply': {'id': 'share_location', 'title': '📍 Share Location'}},
            {'type': 'reply', 'reply': {'id': 'type_address_manually', 'title': '✏️ Type Address'}}
        ]

        return self.whatsapp_service.create_button_message(
            session_id,
            f"🤔 *Couldn't find anything for:* '{search_query}'\n\n" +
            "This might happen if:\n" +
            "• The location is very new or not well-known\n" +
            "• There's a typo in the name\n" +
            "• It's a very local landmark\n\n" +
            "What would you like to do?",
            buttons
        )

    def handle_manual_address_entry(self, state: dict, original_message: str, session_id: str):
        """
        Handles user's input for a manual address entry.
        Performs basic validation and attempts to geocode the address.
        """
        address = original_message.strip()
        logger.debug(f"Handling manual address entry for {session_id}: '{address}'")

        # Basic validation for length and content
        if len(address) < 10 or not any(char.isdigit() for char in address) and not any(char.isalpha() for char in address):
            return self.whatsapp_service.create_text_message(
                session_id,
                "⚠️ *Address seems incomplete or invalid*\n\n" +
                "Please provide a more detailed address including:\n" +
                "• Street name/number\n" +
                "• Area/District\n" +
                "• City/State\n\n" +
                "Example: 123 Main Street, Wuse 2, Abuja, FCT"
            )

        # Attempt to get coordinates if Google Maps API is available and enabled
        location_coordinates = None
        if self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
            coordinates = self.location_service.get_coordinates_from_address(address)
            if coordinates:
                location_coordinates = {"latitude": coordinates[0], "longitude": coordinates[1]}
                logger.info(f"Geocoded manually entered address '{address}' to: {location_coordinates}")
            else:
                logger.warning(f"Could not geocode manually entered address: '{address}' for {session_id}.")

        # Save the address and coordinates (if found) to the session state
        state["address"] = address
        if location_coordinates:
            state["location_coordinates"] = location_coordinates
        else:
            state.pop("location_coordinates", None) # Ensure coordinates are cleared if not found

        # Save to data_manager's user_details for persistence
        self._save_address_to_user_details(state, address, session_id)

        # Generate maps info (only if location service is enabled and API key is valid)
        maps_info = ""
        if self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
            maps_link = self.location_service.generate_maps_link(address)
            maps_info = f"\n🗺️ *View on Maps:* {maps_link}"

        logger.info(f"Manual address '{address}' processed for {session_id}. Proceeding to confirmation.")
        return self._proceed_to_order_confirmation(state, session_id, address, maps_info)

    def handle_confirm_detected_location(self, state: dict, message: str, session_id: str):
        """
        Handles user's confirmation of a location detected from live share or geocoding.
        """
        logger.debug(f"Handling confirm detected location for {session_id}, message: {message}")
        if message == "confirm_location":
            # Address and coordinates should already be in state from handle_live_location
            # Save to data_manager's user_details for persistence
            self._save_address_to_user_details(state, state["address"], session_id)

            maps_info = ""
            if state.get("location_coordinates") and state.get("address") and \
               self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
                coords = state["location_coordinates"]
                location_info_text = self.location_service.format_location_info(
                    coords["latitude"], coords["longitude"], state["address"]
                )
                maps_info = f"\n{location_info_text}" # This already includes the map link if available

            logger.info(f"User {session_id} confirmed detected location: {state.get('address')}.")
            return self._proceed_to_order_confirmation(state, session_id, state["address"], maps_info)

        elif message == "choose_different":
            # User wants to pick a different method, clear current temp address info
            state.pop("location_coordinates", None)
            state.pop("address", None) # Clear address if it was just set temporarily
            logger.info(f"User {session_id} chose different address method.")
            return self.initiate_address_collection(state, session_id) # Go back to the main address menu

        else:
            logger.debug(f"Invalid option '{message}' for confirm detected location for session {session_id}.")
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please choose one of the options above."
            )

    def handle_confirm_maps_result(self, state: dict, message: str, session_id: str):
        """
        Handles user's confirmation of a location found via Google Maps search.
        """
        logger.debug(f"Handling confirm Maps result for {session_id}, message: {message}")
        if message == "use_maps_result":
            # Use the found address and coordinates stored in temp_
            if not state.get("temp_address") or not state.get("temp_coordinates"):
                logger.error(f"Missing temp address/coordinates for {session_id} during maps result confirmation.")
                self.whatsapp_service.create_text_message(session_id, "Something went wrong. Please try finding your address again.")
                return self._initiate_maps_search(state, session_id) # Redirect to search

            state["address"] = state["temp_address"]
            state["location_coordinates"] = state["temp_coordinates"]

            # Save to data_manager's user_details for persistence
            self._save_address_to_user_details(state, state["address"], session_id)

            # Clean up temporary data
            state.pop("temp_address", None)
            state.pop("temp_coordinates", None)

            # Prepare confirmation message
            coords = state["location_coordinates"]
            location_info = self.location_service.format_location_info(
                coords["latitude"], coords["longitude"], state["address"]
            )
            logger.info(f"User {session_id} confirmed Maps search result: {state['address']}.")
            return self._proceed_to_order_confirmation(state, session_id, state["address"], f"\n{location_info}")

        elif message == "search_again":
            # Clear temporary data before initiating a new search
            state.pop("temp_address", None)
            state.pop("temp_coordinates", None)
            logger.info(f"User {session_id} chose to search Maps again.")
            return self._initiate_maps_search(state, session_id)

        elif message == "type_manually":
            # Clear temporary data
            state.pop("temp_address", None)
            state.pop("temp_coordinates", None)
            logger.info(f"User {session_id} chose to type address manually from Maps result.")
            return self._request_manual_address(state, session_id)

        else:
            logger.debug(f"Invalid option '{message}' for confirm maps result for session {session_id}.")
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please choose one of the options above."
            )

    def handle_confirm_coordinates(self, state: dict, message: str, session_id: str):
        """
        Handles user's confirmation of coordinates when a readable address
        could not be determined from live location or maps search.
        """
        logger.debug(f"Handling confirm coordinates for {session_id}, message: {message}")
        if message == "use_coordinates":
            if not state.get("temp_coordinates"):
                logger.error(f"Missing temp coordinates for {session_id} during coordinates confirmation.")
                self.whatsapp_service.create_text_message(session_id, "Something went wrong. Please try providing your location again.")
                return self.initiate_address_collection(state, session_id) # Redirect to start

            coords = state["temp_coordinates"]
            # Create a fallback address string using just coordinates
            address_fallback = f"Location: {coords['latitude']}, {coords['longitude']}"

            state["address"] = address_fallback # Store the fallback address
            state["location_coordinates"] = coords # Store the coordinates

            # Save to data_manager's user_details for persistence
            self._save_address_to_user_details(state, address_fallback, session_id)

            # Clean up temporary data
            state.pop("temp_coordinates", None)

            # Generate maps link info based on coordinates
            maps_link_info = ""
            if self.config.ENABLE_LOCATION_FEATURES and self.location_service.validate_api_key():
                maps_link = self.location_service.generate_maps_link_from_coordinates(
                    coords["latitude"], coords["longitude"]
                )
                maps_link_info = f"\n🗺️ *View on Maps:* {maps_link}"

            logger.info(f"User {session_id} confirmed using coordinates: {address_fallback}.")
            return self._proceed_to_order_confirmation(state, session_id, address_fallback, maps_link_info)

        elif message == "type_address_instead":
            # Clean up temporary data
            state.pop("temp_coordinates", None)
            logger.info(f"User {session_id} chose to type address instead of using coordinates.")
            return self._request_manual_address(state, session_id)

        else:
            logger.debug(f"Invalid option '{message}' for confirm coordinates for session {session_id}.")
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please choose one of the options above."
            )

    def handle_awaiting_live_location_timeout(self, state: dict, original_message: str, session_id: str):
        """
        Handles situations where the user types a message while the bot is
        expecting a live location share. It prompts them to share location
        correctly or choose a different address input method.
        """
        # Only respond if the user actually typed a non-empty message
        if original_message and original_message.strip():
            logger.info(f"User {session_id} typed '{original_message}' while awaiting live location.")
            buttons = [
                {"type": "reply", "reply": {"id": "share_current_location", "title": "📍 Try Share Again"}},
                {"type": "reply", "reply": {"id": "type_address_manually", "title": "✏️ Type Address Instead"}},
                {"type": "reply", "reply": {"id": "back_to_menu", "title": "⬅️ Back to Options"}}
            ]

            return self.whatsapp_service.create_button_message(
                session_id,
                "⏰ *Still waiting for your location...*\n\n" +
                "I noticed you typed a message. To get the most accurate address, please share your live location using the attachment (📎) button.\n\n" +
                "Or would you prefer a different option?",
                buttons
            )
        # If no message was typed (e.g., just a webhook ping), return None
        # This allows MessageProcessor to route it differently or ignore it.
        return None

    def _save_address_to_user_details(self, state: dict, address: str, session_id: str):
        """
        Helper method to save the determined address to the data_manager's
        user_details for long-term persistence across sessions, preserving existing name.
        """
        logger.debug(f"Saving address '{address}' for {session_id} to user details.")
        user_data = {
            "name": state.get("user_name", "Guest"),
            "phone_number": session_id,
            "address": address,
            "user_perferred_name": state.get("user_name", "Guest"),
            "address2": "",
            "address3": ""
        }
        try:
            self.data_manager.save_user_details(session_id, user_data)
            logger.info(f"Address '{address}' saved for {session_id}.")
        except Exception as e:
            logger.error(f"Failed to save user details for {session_id}: {e}")

    def _proceed_to_order_confirmation(self, state: dict, session_id: str, address: str, maps_info: str = ""):
        """
        Transitions the user to the order confirmation state with the selected address.
        Displays the confirmed address, order summary, and final confirmation buttons.
        """
        # Set the next state
        state["current_state"] = "confirm_order"
        # The MessageProcessor will handle the persistence of this state change after this method returns.

        # Crucial check: Ensure the cart is not empty before proceeding to order confirmation.
        if not state.get("cart"):
            logger.warning(f"Attempted to proceed to order confirmation with empty cart for {session_id}.")
            self.whatsapp_service.create_text_message(
                session_id,
                "Your cart is empty. Please add items to your cart before confirming an order."
            )
            # Redirect to menu or a start state for the user to add items
            state["current_state"] = "greeting" # Redirect to greeting/main menu
            # Signal MessageProcessor to redirect to menu_handler if it has such a mechanism.
            return {"redirect": "menu_handler"} # Assuming MessageProcessor can handle this redirect

        buttons = [
            {"type": "reply", "reply": {"id": "confirm_order_final", "title": "✅ Confirm Order"}},
            {"type": "reply", "reply": {"id": "cancel_checkout", "title": "❌ Cancel"}}
        ]
        
        cart_summary = format_cart(state['cart']) # Use the helper function to format cart details

        logger.info(f"Proceeding to order confirmation for {session_id} with address: {address}.")
        return self.whatsapp_service.create_button_message(
            session_id,
            f"✅ *Address Confirmed!*\n\n" +
            f"📍 *Delivery Address:* {address}{maps_info}\n\n" +
            f"📦 *Order Summary:*\n{cart_summary}\n\n" +
            "Ready to place your order?",
            buttons
        )

    def get_state_handlers(self) -> dict:
        """
        Returns a dictionary mapping state names to their corresponding handler methods
        within this class. Used by MessageProcessor for routing.
        """
        return {
            "address_collection_menu": self.handle_address_collection_menu,
            "awaiting_live_location": self.handle_awaiting_live_location_timeout, # This handles text input during awaiting live location
            "maps_search_input": self.handle_maps_search_input,
            "manual_address_entry": self.handle_manual_address_entry,
            "confirm_detected_location": self.handle_confirm_detected_location,
            "confirm_maps_result": self.handle_confirm_maps_result,
            "confirm_coordinates": self.handle_confirm_coordinates
        }