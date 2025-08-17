import logging
from uuid import uuid4
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

    def __init__(self, config, session_manager, data_manager, whatsapp_service, payment_service, location_service, product_sync_handler=None):
        self.config = config
        self.session_manager = session_manager
        self.data_manager = data_manager
        self.whatsapp_service = whatsapp_service
        self.payment_service = payment_service
        self.location_service = location_service

        # Initialize lead tracking handler
        self.lead_tracking_handler = LeadTrackingHandler(
            config, session_manager, data_manager, whatsapp_service
        )

        # Initialize greeting handler first, as it's needed by feedback handler
        self.greeting_handler = GreetingHandler(config, session_manager, data_manager, whatsapp_service)

        # Initialize feedback handler with greeting_handler
        self.feedback_handler = FeedbackHandler(
            config, session_manager, data_manager, whatsapp_service, self.greeting_handler
        )

        # Initialize other handlers
        self.enquiry_handler = EnquiryHandler(config, session_manager, data_manager, whatsapp_service)
        self.faq_handler = FAQHandler(config, session_manager, data_manager, whatsapp_service)
        self.complaint_handler = ComplaintHandler(config, session_manager, data_manager, whatsapp_service)
        self.menu_handler = MenuHandler(config, session_manager, data_manager, whatsapp_service)
        
        # Initialize order handler with lead tracking
        self.order_handler = OrderHandler(
            config, session_manager, data_manager, whatsapp_service, 
            payment_service, location_service, lead_tracking_handler=self.lead_tracking_handler
        )
        
        # Initialize payment handler with feedback and product sync handlers
        self.payment_handler = PaymentHandler(
            config, session_manager, data_manager, whatsapp_service, 
            payment_service, location_service, 
            feedback_handler=self.feedback_handler,
            product_sync_handler=product_sync_handler
        )
        # Set lead tracking handler reference for payment handler
        self.payment_handler.lead_tracking_handler = self.lead_tracking_handler
        
        self.location_handler = LocationAddressHandler(
            config, whatsapp_service, location_service, data_manager
        )
        self.ai_handler = AIHandler(config, session_manager, data_manager, whatsapp_service)

        logger.info("MessageProcessor initialized with lead tracking, AI support, and feedback collection.")

    def process_message(self, message_data, session_id, user_name):
        """Main method to process incoming messages with lead tracking."""
        try:
            # Retrieve session state (handles timeout checking and resetting)
            state = self.session_manager.get_session_state(session_id)

            # Track new interaction for lead tracking
            is_new_interaction = state["current_state"] == "start" and not state.get("user_name")
            self.lead_tracking_handler.track_user_interaction(session_id, user_name, is_new_interaction)

            # Update session activity
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

            # Update user info in session state
            self._update_user_info(state, session_id, user_name)
            self.session_manager.update_session_state(session_id, state)

            # Route to appropriate handler
            response = self._route_to_handler(state, message, original_message, session_id, user_name)

            # Track cart activity if applicable
            if state.get("cart"):
                self.lead_tracking_handler.track_cart_activity(session_id, user_name, state["cart"])

            return response

        except Exception as e:
            logger.error(f"Session {session_id}: Error processing message: {e}", exc_info=True)
            state = self.session_manager.get_session_state(session_id)
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_text_message(
                session_id,
                "⚠️ Something went wrong. Let's start fresh. Please try again."
            )

    def track_order_completion(self, session_id, order_id, order_value):
        """Track order completion for conversion analytics."""
        self.lead_tracking_handler.track_order_conversion(session_id, order_id, order_value)

    def initiate_post_payment_feedback(self, session_id, order_id):
        """Initiate feedback collection after successful payment."""
        try:
            state = self.session_manager.get_session_state(session_id)
            return self.payment_handler._initiate_feedback_collection(state, session_id, order_id)
        except Exception as e:
            logger.error(f"Session {session_id}: Error initiating feedback for order {order_id}: {e}", exc_info=True)
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
        if user_name and not state.get("user_name"):
            state["user_name"] = user_name
        if not state.get("user_name"):
            state["user_name"] = "Guest"
        state["phone_number"] = session_id

        if not state.get("address"):
            retrieved_address = self.data_manager.get_address_from_order_details(session_id)
            if retrieved_address:
                state["address"] = retrieved_address
                if session_id not in self.data_manager.user_details:
                    self.data_manager.user_details[session_id] = {
                        "name": state["user_name"],
                        "address": state["address"]
                    }
                    self.data_manager.save_user_details(session_id, self.data_manager.user_details[session_id])

    def _route_to_handler(self, state, message, original_message, session_id, user_name):
        """Route messages to appropriate handlers based on current_handler and current_state."""
        current_handler_name = state.get("current_handler", "greeting_handler")
        current_state = state.get("current_state", "start")
        
        if "user_name" not in state:
            state["user_name"] = user_name or "Guest"

        response = None

        try:
            # Add a global escape command to handle messages like "menu" or "start"
            if message in ["menu", "back", "start", "hello"]:
                logger.info(f"Session {session_id}: Global escape keyword '{message}' detected. Resetting to greeting.")
                # This will reset the state and send the main menu
                return self.greeting_handler.handle_back_to_main(state, session_id, "Let's start fresh. What can I do for you?")
            
            # Handle redirect messages explicitly
            if message in ["show_enquiry_menu", "show_faq_categories", "start_track_order"]:
                return self._handle_redirect_message(state, message, original_message, session_id, user_name)

            # Route based on current handler and state
            if current_handler_name == "greeting_handler":
                if current_state == "start":
                    response = self.greeting_handler.generate_initial_greeting(state, session_id, user_name)
                elif current_state == "collect_preferred_name":
                    response = self.greeting_handler.handle_collect_preferred_name_state(state, message, session_id)
                elif current_state == "collect_delivery_address":
                    response = self.greeting_handler.handle_collect_delivery_address_state(state, message, session_id)
                elif current_state == "greeting":
                    response = self.greeting_handler.handle_greeting_state(state, message, original_message, session_id)
                else:
                    logger.warning(f"Session {session_id}: Unhandled greeting_handler state '{current_state}'. Resetting to greeting.")
                    response = self.greeting_handler.handle_back_to_main(state, session_id, "I'm sorry, I didn't understand that. Let's return to the main menu.")
            
            elif current_handler_name == "ai_handler":
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
                    logger.warning(f"Session {session_id}: Unhandled AI state '{current_state}'. Resetting to AI menu.")
                    state["current_state"] = "ai_menu_selection"
                    self.session_manager.update_session_state(session_id, state)
                    response = self.ai_handler.handle_ai_menu_state(state, "initial_entry", original_message, session_id)
            
            elif current_handler_name == "enquiry_handler":
                if current_state == "enquiry_menu":
                    response = self.enquiry_handler.handle_enquiry_menu_state(state, message, session_id)
                elif current_state == "enquiry":
                    response = self.enquiry_handler.handle_enquiry_state(state, original_message, session_id)
                else:
                    logger.warning(f"Session {session_id}: Unhandled enquiry_handler state '{current_state}'.")
                    response = self.enquiry_handler.handle_back_to_main(state, session_id)
            
            elif current_handler_name == "faq_handler":
                if current_state == "faq_categories":
                    response = self.faq_handler.handle_faq_categories_state(state, message, session_id)
                elif current_state == "faq_questions":
                    response = self.faq_handler.handle_faq_questions_state(state, message, session_id)
                else:
                    logger.warning(f"Session {session_id}: Unhandled faq_handler state '{current_state}'.")
                    response = self.faq_handler.handle_back_to_main(state, session_id)
            
            elif current_handler_name == "complaint_handler":
                if current_state == "complain":
                    response = self.complaint_handler.handle_complaint_state(state, original_message, session_id)
                else:
                    logger.warning(f"Session {session_id}: Unhandled complaint_handler state '{current_state}'.")
                    response = self.complaint_handler.handle_back_to_main(state, session_id)
            
            elif current_handler_name == "menu_handler":
                if current_state == "menu":
                    response = self.menu_handler.handle_menu_state(state, message, original_message, session_id)
                elif current_state == "category_selected":
                    response = self.menu_handler.handle_category_selected_state(state, message, original_message, session_id)
                else:
                    logger.warning(f"Session {session_id}: Unhandled menu_handler state '{current_state}'.")
                    response = self.menu_handler.handle_back_to_main(state, session_id)
            
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
                elif current_state == "prompt_add_note":
                    response = self.order_handler.handle_prompt_add_note_state(state, message, session_id)
                elif current_state == "add_note":
                    response = self.order_handler.handle_add_note_state(state, message, session_id)
                elif current_state == "payment_pending":
                    response = self.order_handler.handle_payment_pending_state(state, message, session_id)
                else:
                    logger.warning(f"Session {session_id}: Unhandled order_handler state '{current_state}'.")
                    response = self.order_handler.handle_back_to_main(state, session_id)
            
            elif current_handler_name == "payment_handler":
                if current_state == "payment_processing":
                    response = self.payment_handler.handle_payment_processing_state(state, message, session_id)
                elif current_state == "awaiting_payment":
                    response = self.payment_handler.handle_awaiting_payment_state(state, message, session_id)
                elif current_state == "order_confirmation":
                    response = self.payment_handler.handle_order_confirmation_state(state, session_id)
                elif current_state == "feedback_rating":
                    response = self.payment_handler.handle_feedback_response(state, message, session_id)
                else:
                    logger.warning(f"Session {session_id}: Unhandled payment_handler state '{current_state}'.")
                    response = self.payment_handler.handle_back_to_main(state, session_id, "There was an issue with payment. Please try again or choose another option.")
            
            elif current_handler_name == "feedback_handler":
                if current_state == "feedback_rating":
                    response = self.feedback_handler.handle_feedback_rating_state(state, message, session_id)
                elif current_state == "feedback_completed":
                    response = self.feedback_handler.handle_feedback_completed_state(state, message, session_id)
                else:
                    logger.warning(f"Session {session_id}: Unhandled feedback_handler state '{current_state}'.")
                    response = self.feedback_handler.handle_back_to_main(state, session_id)
            
            elif current_handler_name == "location_handler":
                response = self._handle_location_states(state, message, original_message, session_id)
            
            # Handle global 'menu' command - This is now redundant due to the new global escape.
            # I am keeping it for now to avoid breaking other parts of your code.
            if message == "menu" and current_handler_name != "greeting_handler":
                return self.greeting_handler.handle_back_to_main(state, session_id)

            # Handle redirects
            if isinstance(response, dict) and response.get("redirect"):
                redirect_target_handler_name = response["redirect"]
                redirect_message_for_target = response.get("redirect_message", message)
                logger.info(f"Session {session_id}: Redirecting to handler '{redirect_target_handler_name}' with message '{redirect_message_for_target}'.")
                state["current_handler"] = redirect_target_handler_name
                self.session_manager.update_session_state(session_id, state)
                return self._route_to_handler(state, redirect_message_for_target, original_message, session_id, user_name)

            # Fallback for no response
            if response is None:
                logger.warning(f"Session {session_id}: No handler response for handler '{current_handler_name}', state '{current_state}', message '{message}'. Resetting to greeting.")
                state["current_state"] = "greeting"
                state["current_handler"] = "greeting_handler"
                self.session_manager.update_session_state(session_id, state)
                response = self.greeting_handler.generate_initial_greeting(state, session_id, user_name)

            return response

        except Exception as e:
            logger.error(f"Session {session_id}: Error in message routing for handler '{current_handler_name}', state '{current_state}': {e}", exc_info=True)
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_text_message(
                session_id,
                "⚠️ Something went wrong. Let's start fresh. Please try again."
            )

    def _handle_redirect_message(self, state, message, original_message, session_id, user_name):
        """Handle specific redirect messages by calling appropriate handler methods."""
        if message == "show_enquiry_menu":
            return self.enquiry_handler.show_enquiry_menu(state, session_id)
        elif message == "show_faq_categories":
            state["current_state"] = "faq_categories"
            state["current_handler"] = "faq_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.faq_handler.handle_faq_categories_state(state, "initial_entry", session_id)
        elif message == "start_track_order":
            state["current_state"] = "track_order"
            state["current_handler"] = "track_order_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.track_order_handler.handle_track_order_state(state, message, session_id)
        else:
            logger.warning(f"Session {session_id}: Unhandled redirect message '{message}'. Resetting to greeting.")
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.greeting_handler.generate_initial_greeting(state, session_id, user_name)

    def _handle_location_states(self, state, message, original_message, session_id):
        """Handle location-related states."""
        current_state = state["current_state"]

        if current_state == "address_collection_menu":
            return self.location_handler.handle_address_collection_menu(state, message, session_id)
        elif current_state == "awaiting_live_location":
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
            logger.warning(f"Session {session_id}: Unexpected location state '{current_state}'. Attempting legacy handling.")
            return self._handle_legacy_location_states(state, original_message, session_id)

    def _handle_legacy_location_states(self, state, original_message, session_id):
        """Handle legacy location states for backward compatibility."""
        if original_message.strip():
            state["address"] = original_message.strip()
            self.data_manager.user_details.setdefault(state["phone_number"], {})
            self.data_manager.user_details[state["phone_number"]]["name"] = state.get("user_name", "Guest")
            self.data_manager.user_details[state["phone_number"]]["address"] = state["address"]
            self.data_manager.save_user_details(state["phone_number"], self.data_manager.user_details[state["phone_number"]])

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

        if state["current_handler"] == "location_handler" and \
           state["current_state"] in ["awaiting_live_location", "address_collection_menu", "manual_address_entry", "maps_search_input"]:
            return self.location_handler.handle_live_location(
                state, session_id, latitude, longitude, location_name, location_address
            )
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