import datetime
import threading
from threading import Timer
from typing import Dict, Any, List
import psycopg2
from psycopg2.extras import RealDictCursor
from utils.helpers import format_cart
from .base_handler import BaseHandler

class PaymentHandler(BaseHandler):
    """Handles payment processing and order completion with dual verification and subaccount splitting."""
    
    def __init__(self, config, session_manager, data_manager, whatsapp_service, payment_service, location_service):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
        self.payment_service = payment_service
        self.location_service = location_service
        self.subaccount_code = getattr(config, 'SUBACCOUNT_CODE', None)  # e.g., 'SUB_XXXXXXXX'
        self.subaccount_percentage = getattr(config, 'SUBACCOUNT_PERCENTAGE', 30)  # Default 30%
        
        # Dictionary to track payment monitoring timers
        self.payment_timers = {}
        self.logger.info(f"PaymentHandler initialized with subaccount {self.subaccount_code}, split percentage {self.subaccount_percentage}%")
    
    def handle_payment_processing_state(self, state, message, session_id):
        """Handle payment processing state - entry point from order handler."""
        self.logger.info(f"Handling payment processing for session {session_id}, message: {message}")
        
        if message == "initiate_payment":
            return self.create_payment_link(state, session_id)
        else:
            # Handle other messages during payment processing
            return self.whatsapp_service.create_text_message(
                session_id,
                "🔄 Processing your payment request. Please wait..."
            )
    
    def create_payment_link(self, state, session_id):
        """Create payment link for an existing order with subaccount splitting and automatic monitoring."""
        try:
            self.logger.info(f"Creating payment link for session {session_id}")
            
            # Validate cart
            if not state.get("cart"):
                self.logger.warning(f"Cannot create payment - cart is empty for session {session_id}")
                state["current_state"] = "greeting"
                state["current_handler"] = "greeting_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "Your cart appears to be empty. Let's start fresh. How can I help you today?"
                )
            
            # Retrieve existing order ID from state (set by OrderHandler)
            order_id = state.get("order_id")
            if not order_id:
                self.logger.error(f"No order_id found in state for session {session_id}")
                state["current_state"] = "order_summary"
                state["current_handler"] = "order_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "⚠️ No order found. Please try checking out again."
                )
            
            # Fetch order data from database to get total_amount
            order_data = self.data_manager.get_order_by_id(order_id)
            if not order_data:
                self.logger.error(f"Order {order_id} not found in database for session {session_id}")
                state["current_state"] = "order_summary"
                state["current_handler"] = "order_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "⚠️ Order not found. Please try checking out again."
                )
            
            total_amount_ngn = order_data.get("total_amount", 0)
            if total_amount_ngn <= 0:
                self.logger.warning(f"Invalid total amount {total_amount_ngn} for session {session_id}")
                state["current_state"] = "order_summary"
                state["current_handler"] = "order_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "⚠️ Invalid order total. Please check your cart and try again."
                )
            
            # Generate payment reference
            payment_reference = f"PAY-{order_id}"
            state["payment_reference"] = payment_reference
            
            # Convert total_amount to kobo for Paystack
            total_amount_kobo = int(total_amount_ngn * 100)  # Assuming database stores amount in NGN
            
            # Update order with payment reference, payment method, and subaccount split
            payment_data = {
                "payment_reference": payment_reference,
                "payment_method_type": "paystack",
                "subaccount_split": {
                    "subaccount_code": self.subaccount_code,
                    "percentage": self.subaccount_percentage
                } if self.subaccount_code else None
            }
            success = self.data_manager.update_order_status(order_id, "pending_payment", payment_data)
            if not success:
                self.logger.error(f"Failed to update order {order_id} to pending_payment status for session {session_id}")
                state["current_state"] = "order_summary"
                state["current_handler"] = "order_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "⚠️ Error accessing order. Please try checking out again."
                )
            
            # Create Paystack payment link with subaccount
            customer_email = self.payment_service.generate_customer_email(
                state.get("phone_number", session_id), 
                state.get("user_name", "Guest")
            )
            
            payment_url = self.payment_service.create_payment_link(
                amount=total_amount_kobo,
                email=customer_email,
                reference=payment_reference,
                customer_name=state.get("user_name", "Guest"),
                customer_phone=state.get("phone_number", session_id),
                metadata={
                    "order_id": order_id,
                    "delivery_address": state.get("address", "Not provided")
                },
                subaccount_code=self.subaccount_code,
                split_percentage=self.subaccount_percentage
            )
            
            if payment_url:
                # Start automatic payment monitoring
                self.start_payment_monitoring(session_id, payment_reference, order_id)
                
                state["current_state"] = "awaiting_payment"
                state["current_handler"] = "payment_handler"
                self.session_manager.update_session_state(session_id, state)
                
                self.logger.info(f"Payment link created successfully for order {order_id} with subaccount {self.subaccount_code}")
                
                # Fetch order items from database for display
                order_items = self._get_order_items_from_db(order_id)
                formatted_items = self._format_order_items(order_items)
                
                return self.whatsapp_service.create_text_message(
                    session_id,
                    f"🛒 *Order Created Successfully!*\n\n"
                    f"📋 *Order ID:* {order_id}\n"
                    f"💰 *Total:* ₦{total_amount_ngn:,}\n"
                    f"🛒 *Items:* {formatted_items}\n\n"
                    f"💳 *Complete Payment:*\n{payment_url}\n\n"
                    f"✅ We'll automatically confirm your order once payment is received!\n"
                    f"💬 You can also send 'paid' after payment to check status immediately.\n\n"
                    f"⏰ Payment link expires in 15 minutes."
                )
            else:
                self.logger.error(f"Failed to generate payment link for order {order_id}")
                state["current_state"] = "order_summary"
                state["current_handler"] = "order_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "⚠️ Failed to generate payment link. Please try again."
                )
                
        except Exception as e:
            self.logger.error(f"Error creating payment link for session {session_id}: {e}", exc_info=True)
            state["current_state"] = "order_summary"
            state["current_handler"] = "order_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_text_message(
                session_id,
                "⚠️ Error processing payment. Please try again or contact support."
            )
    
    def _get_order_items_from_db(self, order_id: str) -> List[Dict]:
        """Fetch order items from whatsapp_order_details table."""
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT item_name, quantity, unit_price, subtotal
                        FROM whatsapp_order_details
                        WHERE order_id = %s
                    """
                    cur.execute(query, (order_id,))
                    items = cur.fetchall()
                    return [dict(item) for item in items]
        except psycopg2.Error as e:
            self.logger.error(f"Database error while fetching order items for order {order_id}: {e}", exc_info=True)
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error while fetching order items for order {order_id}: {e}", exc_info=True)
            return []
    
    def _format_order_items(self, items: List[Dict]) -> str:
        """Format order items for display, assuming database amounts are in NGN."""
        if not items:
            return "No items found."
        formatted = "\n"
        for item in items:
            item_name = item.get("item_name", "Unknown Item")
            quantity = item.get("quantity", 0)
            unit_price = item.get("unit_price", 0.0)  # Already in NGN
            subtotal = item.get("subtotal", 0.0)      # Already in NGN
            formatted += f"- {item_name} (x{quantity}): ₦{int(subtotal):,}\n"
        return formatted
    
    def start_payment_monitoring(self, session_id, payment_reference, order_id):
        """Start monitoring payment status every minute for up to 15 minutes."""
        self.logger.info(f"Starting payment monitoring for order {order_id}, reference {payment_reference}")
        
        def check_payment_status(attempt=1, max_attempts=15):
            """Check payment status and handle accordingly."""
            try:
                payment_status, payment_data = self.payment_service.verify_payment_detailed(payment_reference)
                
                if payment_status:  # payment_status is a boolean
                    # Payment successful - notify user and update order
                    self.logger.info(f"Payment verified for order {order_id} on attempt {attempt}")
                    self.handle_successful_auto_payment(session_id, order_id, payment_reference)
                    
                    # Stop monitoring - payment successful
                    if session_id in self.payment_timers:
                        self.payment_timers[session_id].cancel()
                        del self.payment_timers[session_id]
                    return
                
                # Payment not yet successful
                self.logger.info(f"Payment not yet verified for order {order_id}, attempt {attempt}/{max_attempts}")
                
                # Send reminder after 5 minutes (5 attempts)
                if attempt == 5:
                    self.send_payment_reminder(session_id, order_id, payment_reference)
                
                # Continue monitoring if we haven't reached max attempts
                if attempt < max_attempts:
                    # Schedule next check in 1 minute (60 seconds)
                    timer = Timer(60, lambda: check_payment_status(attempt + 1, max_attempts))
                    self.payment_timers[session_id] = timer
                    timer.start()
                else:
                    # Max attempts reached - payment expired
                    self.logger.info(f"Payment monitoring expired for order {order_id} after {max_attempts} attempts")
                    self.handle_payment_timeout(session_id, order_id, payment_reference)
                    
                    # Clean up timer
                    if session_id in self.payment_timers:
                        del self.payment_timers[session_id]
                        
            except Exception as e:
                self.logger.error(f"Error in payment monitoring for order {order_id}: {e}")
                # Continue monitoring despite error
                if attempt < max_attempts:
                    timer = Timer(60, lambda: check_payment_status(attempt + 1, max_attempts))
                    self.payment_timers[session_id] = timer
                    timer.start()
        
        # Start the first check immediately
        check_payment_status()
    
    def handle_successful_auto_payment(self, session_id, order_id, payment_reference):
        """Handle successful payment detected automatically."""
        try:
            # Get detailed payment data
            payment_verified, payment_data = self.payment_service.verify_payment_detailed(payment_reference)
            
            if not payment_verified:
                self.logger.warning(f"handle_successful_auto_payment called but payment not verified for {payment_reference}")
                return
            
            # Update order status
            order_data = self.data_manager.get_order_by_payment_reference(payment_reference)
            if order_data:
                success = self.data_manager.update_order_status(
                    order_id,
                    "confirmed",
                    {
                        "payment_reference": payment_reference,
                        "payment_method_type": payment_data.get("payment_method_type", "paystack"),
                        "subaccount_split": {
                            "subaccount_code": self.subaccount_code,
                            "percentage": self.subaccount_percentage
                        } if self.subaccount_code else None
                    }
                )
                if not success:
                    self.logger.error(f"Failed to update order {order_id} to confirmed status for session {session_id}")
                    return
            else:
                self.logger.error(f"Order data not found for payment reference {payment_reference} during auto-payment handling.")
                return  # Exit if no order data
            
            # Update session state
            state = self.session_manager.get_session_state(session_id)
            state["current_state"] = "order_confirmation"
            state["current_handler"] = "payment_handler"
            state["cart"] = {}  # Clear cart
            self.session_manager.update_session_state(session_id, state)
            
            # Track order conversion for lead tracking
            try:
                if hasattr(self, 'lead_tracking_handler') and self.lead_tracking_handler:
                    self.lead_tracking_handler.track_order_conversion(session_id, order_id, order_data["total_amount"])
                else:
                    self.logger.debug("Lead tracking handler not available for order conversion tracking")
            except Exception as e:
                self.logger.error(f"Error tracking order conversion: {e}")
            
            # Extend session for paid user (24 hours)
            try:
                self.session_manager.extend_session_for_paid_user(session_id, order_id, hours=24)
                self.logger.info(f"Extended session for paid user {session_id} for 24 hours")
            except Exception as e:
                self.logger.error(f"Error extending paid user session: {e}")
            
            # Initialize order status
            try:
                if hasattr(self, 'order_tracking_handler') and self.order_tracking_handler:
                    self.order_tracking_handler.update_order_status(
                        order_id, 
                        "received", 
                        "Your order has been received and is being processed."
                    )
            except Exception as e:
                self.logger.error(f"Error initializing order status: {e}")
            
            # Generate maps info
            maps_info = self._generate_maps_info(state)
            
            # Fetch order items from database
            order_items = self._get_order_items_from_db(order_id)
            formatted_items = self._format_order_items(order_items)
            
            # Send automatic success message
            success_message = (
                f"🎉 *Payment Automatically Confirmed!*\n\n"
                f"📋 *Order ID:* {order_id}\n"
                f"💰 *Amount Paid:* ₦{order_data.get('total_amount', 0):,}\n"
                f"🛒 *Items:* {formatted_items}\n"
                f"🚚 *Delivery to:* {state.get('address', 'Not provided')}{maps_info}\n\n"
                f"✅ Your order has been received and is being processed!\n"
                f"📱 We'll contact you shortly for delivery updates.\n\n"
                f"🙏 Thank you for choosing us! 😊"
            )
            
            self.whatsapp_service.create_text_message(session_id, success_message)
            self.logger.info(f"Sent automatic payment confirmation for order {order_id} to {session_id}")
            
            # Initiate feedback collection after a brief delay
            self._initiate_feedback_collection(state, session_id, order_id)
            
        except Exception as e:
            self.logger.error(f"Error handling successful auto payment for order {order_id}: {e}")
    
    def send_payment_reminder(self, session_id, order_id, payment_reference):
        """Send payment reminder after 5 minutes."""
        try:
            state = self.session_manager.get_session_state(session_id)
            
            # Fetch order data from database
            order_data = self.data_manager.get_order_by_payment_reference(payment_reference)
            if not order_data:
                self.logger.error(f"Order data not found for reminder for order {order_id}.")
                return
            
            total_amount = order_data["total_amount"]  # Already in NGN
            customer_email = self.payment_service.generate_customer_email(
                state.get("phone_number", session_id), 
                state.get("user_name", "Guest")
            )
            
            payment_url = self.payment_service.create_payment_link(
                amount=int(total_amount * 100),  # Convert to kobo for Paystack
                email=customer_email,
                reference=payment_reference,  # Use same reference
                customer_name=state.get("user_name", "Guest"),
                customer_phone=state.get("phone_number", session_id),
                metadata={
                    "order_id": order_id,
                    "delivery_address": state.get("address", "Not provided"),
                    "reminder": True
                },
                subaccount_code=self.subaccount_code,
                split_percentage=self.subaccount_percentage
            )
            
            if payment_url:
                # Fetch order items from database
                order_items = self._get_order_items_from_db(order_id)
                formatted_items = self._format_order_items(order_items)
                
                reminder_message = (
                    f"⏰ *Payment Reminder*\n\n"
                    f"We notice your payment for Order #{order_id} hasn't been completed yet.\n\n"
                    f"💰 *Total Amount:* ₦{total_amount:,}\n"
                    f"🛒 *Items:* {formatted_items}\n\n"
                    f"💳 *Complete Payment:*\n{payment_url}\n\n"
                    f"🔄 We're still monitoring for your payment automatically.\n"
                    f"💬 You can also send 'paid' after payment to check immediately.\n\n"
                    f"❌ Reply 'cancel' to cancel this order."
                )
                
                self.whatsapp_service.create_text_message(session_id, reminder_message)
                self.logger.info(f"Payment reminder sent for order {order_id}")
            else:
                self.logger.warning(f"Could not generate new payment link for reminder for order {order_id}.")
            
        except Exception as e:
            self.logger.error(f"Error sending payment reminder for order {order_id}: {e}")
    
    def handle_payment_timeout(self, session_id, order_id, payment_reference):
        """Handle payment timeout after 15 minutes."""
        try:
            # Update order status to expired
            success = self.data_manager.update_order_status(order_id, "expired", {})
            if not success:
                self.logger.error(f"Failed to update order {order_id} to expired status for session {session_id}")
            
            # Update session state
            state = self.session_manager.get_session_state(session_id)
            state["cart"] = {}  # Clear cart
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            
            # Fetch order items from database
            order_items = self._get_order_items_from_db(order_id)
            formatted_items = self._format_order_items(order_items)
            
            # Send timeout message
            timeout_message = (
                f"⏰ *Payment Expired*\n\n"
                f"Your payment for Order #{order_id} has expired after 15 minutes.\n\n"
                f"🛒 *Items:* {formatted_items}\n"
                f"❌ The order has been automatically cancelled.\n"
                f"🛒 You can place a new order anytime by sending any message.\n\n"
                f"💬 Need help? Just ask!"
            )
            
            buttons = [
                {"type": "reply", "reply": {"id": "order", "title": "🛒 New Order"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
            ]
            
            self.whatsapp_service.create_button_message(session_id, timeout_message, buttons)
            self.logger.info(f"Payment timeout handled for order {order_id}")
            
        except Exception as e:
            self.logger.error(f"Error handling payment timeout for order {order_id}: {e}")
    
    def stop_payment_monitoring(self, session_id):
        """Stop payment monitoring for a session."""
        if session_id in self.payment_timers:
            self.payment_timers[session_id].cancel()
            del self.payment_timers[session_id]
            self.logger.info(f"Payment monitoring stopped for session {session_id}")
    
    def handle_awaiting_payment_state(self, state, message, session_id):
        """Handle awaiting payment state with both manual and auto verification."""
        payment_reference = state.get("payment_reference")
        if not payment_reference:
            state["current_state"] = "order_summary"
            state["current_handler"] = "order_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_text_message(
                session_id,
                "⚠️ No payment reference found. Please try checking out again."
            )
        
        # Handle manual "paid" verification
        if message.lower() == "paid":
            self.logger.info(f"Received 'paid' command for session {session_id}, attempting manual verification for ref: {payment_reference}")
            return self._handle_manual_payment_verification(state, session_id, payment_reference)
        
        # Handle order cancellation
        elif message.lower() in ["cancel", "cancel_order"]:
            return self._handle_payment_cancellation(state, session_id)
        
        # Handle other messages during payment waiting
        else:
            return self._handle_payment_waiting_message(state, session_id, payment_reference)
    
    def _handle_manual_payment_verification(self, state, session_id, payment_reference):
        """Handle manual 'paid' verification."""
        try:
            self.logger.debug(f"Attempting manual payment verification for session {session_id}, reference {payment_reference}")
            payment_verified, payment_data = self.payment_service.verify_payment_detailed(payment_reference)
            order_data = self.data_manager.get_order_by_payment_reference(payment_reference)
            
            if payment_verified and order_data:
                self.logger.info(f"Manual payment verification successful for order {order_data['order_id']}")
                # Stop automatic monitoring since payment is confirmed
                self.stop_payment_monitoring(session_id)
                
                # Update order and session
                success = self.data_manager.update_order_status(
                    order_data["order_id"],
                    "confirmed",
                    {
                        "payment_reference": payment_reference,
                        "payment_method_type": payment_data.get("payment_method_type", "paystack"),
                        "subaccount_split": {
                            "subaccount_code": self.subaccount_code,
                            "percentage": self.subaccount_percentage
                        } if self.subaccount_code else None
                    }
                )
                if not success:
                    self.logger.error(f"Failed to update order {order_data['order_id']} to confirmed status for session {session_id}")
                    return self.whatsapp_service.create_text_message(
                        session_id,
                        "⚠️ Error confirming payment. Please contact support."
                    )
                
                state["current_state"] = "order_confirmation"
                state["current_handler"] = "payment_handler"
                state["cart"] = {}  # Clear cart
                self.session_manager.update_session_state(session_id, state)
                
                # Track order conversion for lead tracking
                try:
                    if hasattr(self, 'lead_tracking_handler') and self.lead_tracking_handler:
                        self.lead_tracking_handler.track_order_conversion(session_id, order_data["order_id"], order_data["total_amount"])
                    else:
                        self.logger.debug("Lead tracking handler not available for order conversion tracking")
                except Exception as e:
                    self.logger.error(f"Error tracking order conversion: {e}")
                
                # Fetch order items from database
                order_items = self._get_order_items_from_db(order_data["order_id"])
                formatted_items = self._format_order_items(order_items)
                
                maps_info = self._generate_maps_info(state)
                
                success_message = (
                    f"🎉 *Payment Confirmed!*\n\n"
                    f"📋 *Order ID:* {order_data['order_id']}\n"
                    f"💰 *Amount Paid:* ₦{order_data.get('total_amount', 0):,}\n"
                    f"🛒 *Items:* {formatted_items}\n"
                    f"🚚 *Delivery to:* {state.get('address', 'Not provided')}{maps_info}\n\n"
                    f"✅ Your order is confirmed and being processed!\n"
                    f"📱 You'll receive delivery updates soon.\n\n"
                    f"🙏 Thank you for your purchase! 😊"
                )
                
                self.whatsapp_service.create_text_message(session_id, success_message)
                
                # Initiate feedback collection
                self._initiate_feedback_collection(state, session_id, order_data['order_id'])
                
                return {"message": "Payment confirmed and feedback initiated"}
                
            elif not payment_verified:
                self.logger.info(f"Manual payment verification failed for reference {payment_reference}. Paystack status: {payment_data.get('status', 'N/A') if payment_data else 'N/A'}")
                
                # Fetch order items from database
                order_items = self._get_order_items_from_db(order_data["order_id"] if order_data else "0")
                formatted_items = self._format_order_items(order_items)
                
                return self.whatsapp_service.create_text_message(
                    session_id,
                    f"⏳ *Payment Not Yet Received*\n\n"
                    f"📋 *Order ID:* {order_data['order_id'] if order_data else 'N/A'}\n"
                    f"🛒 *Items:* {formatted_items}\n"
                    f"💰 *Total:* ₦{order_data['total_amount'] if order_data else 0:,}\n\n"
                    f"💳 Please:\n"
                    f"1️⃣ Complete the payment using the link provided\n"
                    f"2️⃣ Wait a moment for processing\n"
                    f"3️⃣ Try sending 'paid' again\n\n"
                    f"🔄 We're also checking automatically every minute.\n"
                    f"❌ Send 'cancel' to cancel the order."
                )
            else:  # order_data is None
                self.logger.error(f"Order not found for payment reference {payment_reference} during manual verification.")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    f"⚠️ *Order Not Found*\n\n"
                    f"We couldn't find your order. Please try placing a new order.\n\n"
                    f"💬 Contact support if you believe this is an error."
                )
                
        except Exception as e:
            self.logger.error(f"Error in manual payment verification for reference {payment_reference}: {e}", exc_info=True)
            return self.whatsapp_service.create_text_message(
                session_id,
                "⚠️ Error checking payment status. Please try again or contact support."
            )
    
    def _handle_payment_cancellation(self, state, session_id):
        """Handle payment cancellation."""
        try:
            # Stop automatic monitoring
            self.stop_payment_monitoring(session_id)
            
            # Update order status
            if state.get("payment_reference"):
                order_data = self.data_manager.get_order_by_payment_reference(state["payment_reference"])
                if order_data:
                    success = self.data_manager.update_order_status(order_data["order_id"], "cancelled", {})
                    if not success:
                        self.logger.error(f"Failed to update order {order_data['order_id']} to cancelled status for session {session_id}")
                else:
                    self.logger.warning(f"No order found for payment reference {state['payment_reference']} during cancellation.")
            
            # Clear session
            state["cart"] = {}
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            
            buttons = [
                {"type": "reply", "reply": {"id": "order", "title": "🛒 New Order"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
            ]
            
            return self.whatsapp_service.create_button_message(
                session_id,
                f"❌ *Order Cancelled*\n\n"
                f"Your order has been cancelled and payment monitoring stopped.\n\n"
                f"🛒 Ready to place a new order?",
                buttons
            )
            
        except Exception as e:
            self.logger.error(f"Error handling payment cancellation for session {session_id}: {e}", exc_info=True)
            return self.handle_back_to_main(state, session_id)
    
    def _handle_payment_waiting_message(self, state, session_id, payment_reference):
        """Handle other messages while waiting for payment."""
        # Check if payment was already confirmed automatically
        order_data = self.data_manager.get_order_by_payment_reference(payment_reference)
        
        if order_data and order_data.get("status") == "confirmed":
            self.logger.info(f"User sent message while in awaiting_payment, but order {order_data['order_id']} was already confirmed.")
            # Payment was confirmed automatically, redirect to confirmation
            state["current_state"] = "order_confirmation"
            state["current_handler"] = "payment_handler"
            state["cart"] = {}
            self.session_manager.update_session_state(session_id, state)

            # Fetch order items from database
            order_items = self._get_order_items_from_db(order_data["order_id"])
            formatted_items = self._format_order_items(order_items)
            maps_info = self._generate_maps_info(state)
            
            message_text = (
                f"🎉 *Payment Already Confirmed!*\n\n"
                f"📋 *Order ID:* {order_data['order_id']}\n"
                f"🛒 *Items:* {formatted_items}\n"
                f"🚚 *Delivery to:* {state.get('address', 'Not provided')}{maps_info}\n\n"
                f"✅ Your order is confirmed and being processed!"
            )
            return self.whatsapp_service.create_text_message(session_id, message_text)
        else:
            # Still waiting for payment
            self.logger.info(f"User sent message while still awaiting payment for order {state.get('order_id', 'N/A')}.")
            
            # Fetch order items from database
            order_id = state.get("order_id", "0")
            order_items = self._get_order_items_from_db(order_id)
            formatted_items = self._format_order_items(order_items)
            
            return self.whatsapp_service.create_text_message(
                session_id,
                f"🔄 *Payment Monitoring Active*\n\n"
                f"📋 *Order ID:* {state.get('order_id', 'N/A')}\n"
                f"🛒 *Items:* {formatted_items}\n\n"
                f"✅ Once payment is confirmed, you'll receive an automatic confirmation.\n"
                f"💬 Send 'paid' to check status immediately.\n"
                f"❌ Send 'cancel' to cancel this order."
            )
    
    def _generate_maps_info(self, state):
        """Generate maps information for order confirmation."""
        maps_info = ""
        try:
            if state.get("location_coordinates") and self.location_service:
                maps_link = self.location_service.generate_maps_link_from_coordinates(
                    state["location_coordinates"]["latitude"],
                    state["location_coordinates"]["longitude"]
                )
                maps_info = f"\n🗺️ View on Maps: {maps_link}"
            elif state.get("address") and self.location_service and self.location_service.validate_api_key():
                maps_link = self.location_service.generate_maps_link(state["address"])
                maps_info = f"\n🗺️ View on Maps: {maps_link}"
            else:
                self.logger.debug("No location coordinates or valid address/API key to generate maps info.")
        except Exception as e:
            self.logger.error(f"Error generating maps info: {e}", exc_info=True)
        return maps_info
    
    def handle_order_confirmation_state(self, state, message, session_id):
        """Handle order confirmation state."""
        order_id = state.get("order_id")
        order_data = self.data_manager.get_order_by_payment_reference(state.get("payment_reference"))
        
        if order_data and order_data["status"] == "confirmed":
            state["cart"] = {}  # Clear the cart
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            
            # Fetch order items from database
            order_items = self._get_order_items_from_db(order_id)
            formatted_items = self._format_order_items(order_items)
            maps_info = self._generate_maps_info(state)
            
            message_text = (
                f"✅ *Order Processing*\n\n"
                f"📋 *Order ID:* {order_id}\n"
                f"🛒 *Items:* {formatted_items}\n"
                f"🚚 *Delivery to:* {state.get('address', 'Not provided')}{maps_info}\n\n"
                f"🍽️ Your order is confirmed and being prepared!\n"
                f"📱 We'll notify you when it's ready for delivery.\n\n"
                f"🙏 Thank you for choosing us!"
            )
            return self.whatsapp_service.create_text_message(session_id, message_text)
        else:
            self.logger.warning(f"handle_order_confirmation_state called but order {order_id} not found or not confirmed. Status: {order_data.get('status') if order_data else 'N/A'}")
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_text_message(
                session_id,
                "⚠️ Order not found or not confirmed. Please start a new order."
            )
    
    def handle_payment_webhook(self, webhook_data, session_manager, whatsapp_service):
        """Handle Paystack webhook for payment events."""
        try:
            event = webhook_data.get("event")
            if event == "charge.success":
                payment_reference = webhook_data["data"]["reference"]
                self.logger.info(f"Received 'charge.success' webhook for reference: {payment_reference}")
                order_data = self.data_manager.get_order_by_payment_reference(payment_reference)
                
                if order_data:
                    session_id = order_data["phone_number"]
                    
                    # Stop automatic monitoring since webhook confirmed payment
                    self.stop_payment_monitoring(session_id)
                    
                    # Update order status
                    success = self.data_manager.update_order_status(
                        order_data["order_id"],
                        "confirmed",
                        {
                            "payment_reference": payment_reference,
                            "payment_method_type": webhook_data["data"].get("payment_method_type", "paystack"),
                            "subaccount_split": {
                                "subaccount_code": self.subaccount_code,
                                "percentage": self.subaccount_percentage
                            } if self.subaccount_code else None
                        }
                    )
                    if not success:
                        self.logger.error(f"Failed to update order {order_data['order_id']} to confirmed status for webhook")
                        return
                    
                    # Update session
                    state = session_manager.get_session_state(session_id)
                    state["current_state"] = "order_confirmation"
                    state["current_handler"] = "payment_handler"
                    state["cart"] = {}
                    session_manager.update_session_state(session_id, state)

                    # Track order conversion for lead tracking
                    try:
                        if hasattr(self, 'lead_tracking_handler') and self.lead_tracking_handler:
                            self.lead_tracking_handler.track_order_conversion(session_id, order_data["order_id"], order_data["total_amount"])
                        else:
                            self.logger.debug("Lead tracking handler not available for order conversion tracking")
                    except Exception as e:
                        self.logger.error(f"Error tracking order conversion: {e}")

                    # Fetch order items from database
                    order_items = self._get_order_items_from_db(order_data["order_id"])
                    formatted_items = self._format_order_items(order_items)
                    maps_info = self._generate_maps_info(state)

                    message = (
                        f"🎉 *Payment Successful!*\n\n"
                        f"📋 *Order ID:* {order_data['order_id']}\n"
                        f"💰 *Amount:* ₦{order_data['total_amount']:,}\n"
                        f"🛒 *Items:* {formatted_items}\n"
                        f"🚚 *Delivery to:* {order_data['address']}{maps_info}\n\n"
                        f"✅ Thank you for your purchase!\n"
                        f"📱 You'll receive delivery updates soon."
                    )
                    whatsapp_service.create_text_message(session_id, message)
                    self.logger.info(f"Sent webhook payment confirmation for order {order_data['order_id']} to {session_id}")
                    
                    # Initiate feedback collection for webhook payments
                    self._initiate_feedback_collection_webhook(session_id, order_data['order_id'], session_manager)
                else:
                    self.logger.error(f"No order found for payment reference {payment_reference} from webhook.")
            else:
                self.logger.info(f"Ignored webhook event: {event}")
                
        except Exception as e:
            self.logger.error(f"Error handling payment webhook: {e}", exc_info=True)
    
    def cleanup_expired_monitoring(self):
        """Clean up expired payment monitoring timers."""
        try:
            expired_sessions = []
            
            for session_id in list(self.payment_timers.keys()):
                # Check if session is still valid
                state = self.session_manager.get_session_state(session_id)
                if state.get("current_state") != "awaiting_payment":
                    self.logger.info(f"Session {session_id} state changed from awaiting_payment, cleaning up timer.")
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                self.stop_payment_monitoring(session_id)
            
            if expired_sessions:
                self.logger.info(f"Cleaned up {len(expired_sessions)} expired payment monitoring timers")
                
        except Exception as e:
            self.logger.error(f"Error cleaning up payment monitoring: {e}", exc_info=True)
    
    def _initiate_feedback_collection(self, state: Dict, session_id: str, order_id: str) -> None:
        """Initiate feedback collection after successful payment."""
        try:
            if hasattr(self, 'feedback_handler') and self.feedback_handler:
                self.feedback_handler.initiate_feedback_request(state, session_id, order_id)
            else:
                self.logger.debug("FeedbackHandler not available for feedback collection")
        except Exception as e:
            self.logger.error(f"Error initiating feedback collection for order {order_id}: {e}")
    
    def _initiate_feedback_collection_webhook(self, session_id: str, order_id: str, session_manager) -> None:
        """Initiate feedback collection for webhook payments."""
        try:
            if hasattr(self, 'feedback_handler') and self.feedback_handler:
                state = session_manager.get_session_state(session_id)
                self.feedback_handler.initiate_feedback_request(state, session_id, order_id)
            else:
                self.logger.debug("FeedbackHandler not available for webhook feedback collection")
        except Exception as e:
            self.logger.error(f"Error initiating webhook feedback collection for order {order_id}: {e}")