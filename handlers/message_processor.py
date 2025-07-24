import logging
from utils.helpers import format_cart
from handlers.greeting_handler import GreetingHandler
from handlers.enquiry_handler import EnquiryHandler
from handlers.faq_handler import FAQHandler
from handlers.complaint_handler import ComplaintHandler
from handlers.menu_handler import MenuHandler
from handlers.order_handler import OrderHandler
from handlers.payment_handler import PaymentHandler
from handlers.location_address_handler import LocationAddressHandler
from handlers.lead_tracking_handler import LeadTrackingHandler
from handlers.ai_handler import AIHandler
from handlers.feedback_handler import FeedbackHandler
from services.lead_tracker import LeadTracker

logger = logging.getLogger(__name__)

class MessageProcessor:
    """Main message processor with lead tracking, AI integration, and feedback collection."""

    def __init__(self, config, session_manager, data_manager, whatsapp_service, payment_service, location_service):
        self.config = config
        self.session_manager = session_manager
        self.data_manager = data_manager
        self.whatsapp_service = whatsapp_service
        self.payment_service = payment_service
        self.location_service = location_service

        # Initialize lead tracking first
        self.lead_tracker = LeadTracker(config)
        self.lead_tracking_handler = LeadTrackingHandler(
            config, session_manager, data_manager, whatsapp_service, self.lead_tracker
        )

        # Initialize all handlers with lead tracking where needed
        self.greeting_handler = GreetingHandler(config, session_manager, data_manager, whatsapp_service)
        self.enquiry_handler = EnquiryHandler(config, session_manager, data_manager, whatsapp_service)
        self.faq_handler = FAQHandler(config, session_manager, data_manager, whatsapp_service)
        self.complaint_handler = ComplaintHandler(config, session_manager, data_manager, whatsapp_service)
        self.menu_handler = MenuHandler(config, session_manager, data_manager, whatsapp_service)
        
        # Initialize feedback handler
        self.feedback_handler = FeedbackHandler(config, session_manager, data_manager, whatsapp_service)
        
        # Initialize order handler with lead tracking
        self.order_handler = OrderHandler(
            config, session_manager, data_manager, whatsapp_service, 
            payment_service, location_service, lead_tracking_handler=self.lead_tracking_handler
        )
        
        # Initialize payment handler
        self.payment_handler = PaymentHandler(
            config, session_manager, data_manager, whatsapp_service, 
            payment_service, location_service
        )
        # Set lead tracking handler reference for payment handler
        self.payment_handler.lead_tracking_handler = self.lead_tracking_handler
        # Set feedback handler reference for payment handler
        self.payment_handler.feedback_handler = self.feedback_handler
        
        self.location_handler = LocationAddressHandler(
            config, whatsapp_service, location_service, data_manager
        )
        self.ai_handler = AIHandler(config, session_manager, data_manager, whatsapp_service)

        logger.info("MessageProcessor initialized with lead tracking, AI support, and feedback collection.")

    def process_message(self, message_data, session_id, user_name):
        """Main method to process incoming messages with lead tracking."""

        # Retrieve the session state. IMPORTANT: This method now handles timeout checking and session resetting.
        # If the session has timed out, get_session_state will return a freshly reset state.
        state = self.session_manager.get_session_state(session_id)

        # Determine if it's a 'new interaction' for lead tracking based on the state.
        # If the state is 'start' and user_name hasn't been recorded yet, it's a new interaction.
        is_new_interaction = state["current_state"] == "start" and not state.get("user_name")
        self.lead_tracking_handler.track_user_interaction(session_id, user_name, is_new_interaction)

        # We keep update_session_activity here to ensure activity is recorded *after*
        # the session state is retrieved and potentially used by handlers, even if
        # get_session_state already updates it. This ensures the very latest interaction counts.
        self.session_manager.update_session_activity(session_id)

        # Handle different message types
        if isinstance(message_data, dict):
            if message_data.get("type") == "location":
                return self._handle_location_message(message_data, state, session_id, user_name)
            else:
                message = message_data.get("text", "")
        else:
            message = message_data

        original_message = message
        message = message.strip().lower() if message else ""

        # Update user info in the session state
        self._update_user_info(state, session_id, user_name)
        # IMPORTANT: After _update_user_info modifies the 'state' dictionary,
        # you MUST save it back to the session manager.
        self.session_manager.update_session_state(session_id, state)

        # Route to appropriate handler
        response = self._route_to_handler(state, message, original_message, session_id, user_name)

        # Track cart activity after processing (if cart has items)
        if state.get("cart"):
            self.lead_tracking_handler.track_cart_activity(session_id, user_name, state["cart"])

        return response

    def track_order_completion(self, session_id, order_id, order_value):
        """Track order completion for conversion analytics."""
        self.lead_tracking_handler.track_order_conversion(session_id, order_id, order_value)

    def initiate_post_payment_feedback(self, session_id, order_id):
        """Initiate feedback collection after successful payment."""
        try:
            state = self.session_manager.get_session_state(session_id)
            return self.feedback_handler.initiate_feedback_request(state, session_id, order_id)
        except Exception as e:
            logger.error(f"Error initiating feedback for order {order_id}: {e}", exc_info=True)
            return None

    def get_lead_analytics(self):
        """Get lead tracking analytics."""
        return self.lead_tracking_handler.get_analytics_summary()

    def get_abandoned_carts(self, hours_ago=24):
        """Get abandoned carts for remarketing."""
        return self.lead_tracking_handler.get_abandoned_carts_for_remarketing(hours_ago)

    def get_feedback_analytics(self):
        """Get feedback analytics summary."""
        return self.feedback_handler.get_feedback_analytics()

    def _update_user_info(self, state, session_id, user_name):
        """Update user information in session state."""
        # Only set user_name if it's currently None in state and a user_name is provided
        if user_name and not state.get("user_name"):
            state["user_name"] = user_name

        # Ensure user_name is always set, even if not provided by the platform (default to "Guest")
        if not state.get("user_name"):
            state["user_name"] = "Guest"

        state["phone_number"] = session_id

        # Load address if not set in session state and it exists in data_manager
        if not state.get("address"):
            retrieved_address = self.data_manager.get_address_from_order_details(session_id)
            if retrieved_address:
                state["address"] = retrieved_address
                # If an address was loaded, ensure it's also in data_manager.user_details
                # for future reference, and save data_manager details.
                if session_id not in self.data_manager.user_details:
                    self.data_manager.user_details[session_id] = {
                        "name": state["user_name"],
                        "address": state["address"]
                    }
                    self.data_manager.save_user_details()

    def _route_to_handler(self, state, message, original_message, session_id, user_name):
        """Route messages to appropriate handlers based on current_handler and current_state."""
        
        current_handler_name = state.get("current_handler", "greeting_handler")
        current_state = state.get("current_state", "start")
        
        # Ensure user_name is in state for handlers that need it
        if "user_name" not in state:
            state["user_name"] = user_name or "Guest"

        response = None

        try:
            # Route based on the determined current handler and state
            if current_handler_name == "greeting_handler":
                if current_state == "start":
                    # Initial entry point for new or reset sessions
                    response = self.greeting_handler.generate_initial_greeting(state, session_id, user_name)
                elif current_state == "collect_preferred_name":
                    response = self.greeting_handler.handle_collect_preferred_name_state(state, message, session_id)
                elif current_state == "collect_delivery_address":
                    response = self.greeting_handler.handle_collect_delivery_address_state(state, message, session_id)
                elif current_state == "others_menu_selection": # Assuming this is handled by greeting_handler
                    response = self.greeting_handler.handle_others_menu_selection_state(state, message, session_id)
                elif current_state == "greeting":
                    # This is the main menu state
                    response = self.greeting_handler.handle_greeting_state(state, message, original_message, session_id)
                else:
                    logger.warning(f"Unhandled greeting_handler state '{current_state}' for session {session_id}. Resetting to greeting.")
                    response = self.greeting_handler.handle_back_to_main(state, session_id, "I'm sorry, I didn't quite understand that. Let's get back to the main menu.")
            
            elif current_handler_name == "ai_handler":
                # AIHandler handles its own states within its scope
                if current_state == "ai_menu_selection":
                    response = self.ai_handler.handle_ai_menu_state(state, message, original_message, session_id)
                elif current_state == "lola_chat":
                    response = self.ai_handler.handle_lola_chat_state(state, message, original_message, session_id)
                elif current_state == "ai_bulk_order":
                    response = self.ai_handler.handle_ai_bulk_order_state(state, message, original_message, session_id)
                elif current_state == "ai_order_confirmation":
                    response = self.ai_handler.handle_ai_order_confirmation_state(state, message, original_message, session_id)
                elif current_state == "ai_order_clarification":
                    response = self.ai_handler.handle_ai_order_clarification_state(state, message, original_message, session_id)
                else:
                    # Fallback for unexpected AI handler states
                    logger.warning(f"Unhandled AI state '{current_state}' for session {session_id}. Resetting to AI menu.")
                    state["current_state"] = "ai_menu_selection"
                    self.session_manager.update_session_state(session_id, state)
                    response = self.ai_handler.handle_ai_menu_state(state, "initial_entry", original_message, session_id)
            
            elif current_handler_name == "enquiry_handler":
                if current_state == "enquiry_menu":
                    response = self.enquiry_handler.handle_enquiry_menu_state(state, message, session_id)
                elif current_state == "enquiry":
                    response = self.enquiry_handler.handle_enquiry_state(state, original_message, session_id)
                else:
                    logger.warning(f"Unhandled enquiry_handler state '{current_state}' for session {session_id}")
                    response = self.enquiry_handler.handle_back_to_main(state, session_id) # Or a more specific error/reset
            
            elif current_handler_name == "faq_handler":
                if current_state == "faq_categories":
                    response = self.faq_handler.handle_faq_categories_state(state, message, session_id)
                elif current_state == "faq_questions":
                    response = self.faq_handler.handle_faq_questions_state(state, message, session_id)
                else:
                    logger.warning(f"Unhandled faq_handler state '{current_state}' for session {session_id}")
                    response = self.faq_handler.handle_back_to_main(state, session_id) # Or a more specific error/reset
            
            elif current_handler_name == "complaint_handler":
                if current_state == "complain":
                    response = self.complaint_handler.handle_complaint_state(state, original_message, session_id)
                else:
                    logger.warning(f"Unhandled complaint_handler state '{current_state}' for session {session_id}")
                    response = self.complaint_handler.handle_back_to_main(state, session_id) # Or a more specific error/reset
            
            elif current_handler_name == "menu_handler":
                if current_state == "menu":
                    response = self.menu_handler.handle_menu_state(state, message, original_message, session_id)
                elif current_state == "category_selected":
                    response = self.menu_handler.handle_category_selected_state(state, message, original_message, session_id)
                else:
                    logger.warning(f"Unhandled menu_handler state '{current_state}' for session {session_id}")
                    response = self.menu_handler.handle_back_to_main(state, session_id) # Or a more specific error/reset
            
            elif current_handler_name == "order_handler":
                if current_state in ["quantity", "get_quantity"]:
                    response = self.order_handler.handle_quantity_state(state, message, session_id)
                elif current_state == "order_summary":
                    response = self.order_handler.handle_order_summary_state(state, message, session_id)
                elif current_state == "remove_item_selection":
                    response = self.order_handler.handle_remove_item_selection_state(state, message, session_id)
                elif current_state == "confirm_details":
                    response = self.order_handler.handle_confirm_details_state(state, message, session_id)
                elif current_state == "get_new_name_address":
                    response = self.order_handler.handle_get_new_name_address_state(state, message, session_id)
                elif current_state == "confirm_order":
                    response = self.order_handler.handle_confirm_order_state(state, message, session_id)
                elif current_state == "payment_pending":
                    response = self.order_handler.handle_payment_pending_state(state, message, session_id)
                else:
                    logger.warning(f"Unhandled order_handler state '{current_state}' for session {session_id}")
                    response = self.order_handler.handle_back_to_main(state, session_id) # Or a more specific error/reset
            
            elif current_handler_name == "payment_handler":
                if current_state == "payment_processing":
                    response = self.payment_handler.handle_payment_processing_state(state, message, session_id)
                elif current_state == "awaiting_payment":
                    response = self.payment_handler.handle_awaiting_payment_state(state, message, session_id)
                elif current_state == "order_confirmation":
                    response = self.payment_handler.handle_order_confirmation_state(state, message, session_id)
                else:
                    logger.warning(f"Unhandled payment_handler state '{current_state}' for session {session_id}")
                    # Fallback to payment processing or main menu
                    response = self.payment_handler.handle_back_to_main(state, session_id, "There was an issue with payment. Please try again or choose another option.")
            
            elif current_handler_name == "feedback_handler":
                if current_state == "feedback_rating":
                    response = self.feedback_handler.handle_feedback_rating_state(state, message, session_id)
                elif current_state == "feedback_comment":
                    response = self.feedback_handler.handle_feedback_comment_state(state, message, session_id)
                else:
                    logger.warning(f"Unhandled feedback_handler state '{current_state}' for session {session_id}")
                    # Fallback to greeting
                    response = self.feedback_handler.handle_back_to_main(state, session_id)
            
            elif current_handler_name == "location_handler":
                response = self._handle_location_states(state, message, original_message, session_id)
            
            # Handle global 'menu' command if not already in greeting handler
            if message == "menu" and current_handler_name != "greeting_handler":
                # This ensures "menu" always brings you back to the main menu.
                return self.greeting_handler.handle_back_to_main(state, session_id)

            # --- Handle Redirects ---
            if isinstance(response, dict) and response.get("redirect"):
                redirect_target_handler_name = response["redirect"]
                # The redirecting handler should have already updated state["current_handler"]
                # and state["current_state"] and persisted it.
                # So we just need to ensure the correct handler is invoked recursively.
                
                # Pass the original message to the redirected handler if needed, or a specific redirect_message
                redirect_message_for_target = response.get("redirect_message", message)

                logger.info(f"Redirecting session {session_id} to handler '{redirect_target_handler_name}' with message '{redirect_message_for_target}'.")
                
                # Re-call _route_to_handler with the updated state and appropriate message
                # The recursive call will now pick up the new handler and state.
                return self._route_to_handler(state, redirect_message_for_target, original_message, session_id, user_name)

            # If no specific state handler produced a response (response is None),
            # or if the current_handler_name is unexpected after all specific routes.
            if response is None:
                logger.warning(f"No specific handler or state match for handler '{current_handler_name}', state '{current_state}', message '{message}' for session {session_id}. Resetting to greeting.")
                # Default to greeting if nothing else handles it or state is unexpected.
                state["current_state"] = "greeting"
                state["current_handler"] = "greeting_handler"
                self.session_manager.update_session_state(session_id, state)
                
                # Send a generic "didn't understand" message and then the main menu
                self.whatsapp_service.create_text_message(session_id, "I'm sorry, I didn't quite understand that. Let's get back to the main menu.")
                response = self.greeting_handler.send_main_menu(session_id, state.get("user_name", "Guest"), "Please choose from the options below:")

            return response

        except Exception as e:
            logger.error(f"Error in message routing for handler '{current_handler_name}', state '{current_state}' for session {session_id}: {e}", exc_info=True)
            # On error, reset the session state to 'greeting' to avoid being stuck
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_text_message(
                session_id,
                "⚠️ Something went wrong. Let's start fresh. Please try again."
            )

    def _handle_location_states(self, state, message, original_message, session_id):
        """Handle location-related states."""
        current_state = state["current_state"]

        if current_state == "address_collection_menu":
            return self.location_handler.handle_address_collection_menu(state, message, session_id)
        elif current_state == "awaiting_live_location":
            # Pass the message (which is text here, but the actual location data is handled in _handle_location_message)
            return self.location_handler.handle_awaiting_live_location_timeout(state, original_message, session_id)
        elif current_state == "maps_search_input":
            return self.location_handler.handle_maps_search_input(state, original_message, session_id)
        elif current_state == "manual_address_entry":
            return self.location_handler.handle_manual_address_entry(state, original_message, session_id)
        elif current_state == "confirm_detected_location":
            return self.location_handler.handle_confirm_detected_location(state, message, session_id)
        elif current_state == "confirm_maps_result":
            return self.location_handler.handle_confirm_maps_result(state, message, session_id)
        elif current_state == "confirm_coordinates":
            return self.location_handler.handle_confirm_coordinates(state, message, session_id)
        else:
            logger.warning(f"Received message in unexpected location state '{current_state}' for session {session_id}. Attempting legacy handling.")
            return self._handle_legacy_location_states(state, original_message, session_id)

    def _handle_legacy_location_states(self, state, original_message, session_id):
        """Handle legacy location states for backward compatibility."""
        if original_message.strip():
            state["address"] = original_message.strip()
            self.data_manager.user_details.setdefault(state["phone_number"], {})
            self.data_manager.user_details[state["phone_number"]]["name"] = state.get("user_name", "Guest")
            self.data_manager.user_details[state["phone_number"]]["address"] = state["address"]
            self.data_manager.save_user_details()

            state["current_state"] = "confirm_order"
            state["current_handler"] = "order_handler"
            self.session_manager.update_session_state(session_id, state)

            return self.order_handler._show_order_confirmation(state, session_id)
        else:
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please provide a valid delivery address."
            )

    def _handle_location_message(self, message_data, state, session_id, user_name):
        """Handle incoming location messages (WhatsApp 'location' type)."""
        latitude = message_data.get("latitude")
        longitude = message_data.get("longitude")
        location_name = message_data.get("name")
        location_address = message_data.get("address")

        if not latitude or not longitude:
            return self.whatsapp_service.create_text_message(
                session_id,
                "❌ Invalid location data received. Please try sharing your location again."
            )

        # Route actual location data to the location handler
        # Ensure we check the handler *and* specific location states
        if state["current_handler"] == "location_handler" and \
           state["current_state"] in ["awaiting_live_location", "address_collection_menu", "manual_address_entry", "maps_search_input"]:
            return self.location_handler.handle_live_location(
                state, session_id, latitude, longitude, location_name, location_address
            )
        # If the user sends location but the bot isn't expecting it in a location specific state
        else:
            location_info = self.location_service.format_location_info(latitude, longitude, location_address) if self.location_service else f"📍 {latitude}, {longitude}"
            return self.whatsapp_service.create_text_message(
                session_id,
                f"📍 Location received!\n{location_info}\n\nTo use this as your delivery address, please go through the order process or select 'Delivery Address' from the main menu."
            )

    def handle_payment_webhook(self, webhook_data):
        """Handle Paystack webhook for payment events."""
        return self.payment_handler.handle_payment_webhook(
            webhook_data,
            self.session_manager,
            self.whatsapp_service
        )

    def cleanup_expired_resources(self):
        """Clean up expired sessions and payment monitoring."""
        try:
            self.session_manager.cleanup_expired_sessions()
            self.payment_handler.cleanup_expired_monitoring()
            logger.info("Resource cleanup completed.")
        except Exception as e:
            logger.error(f"Error in resource cleanup: {e}", exc_info=True)