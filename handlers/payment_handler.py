import logging
import sys
import io
from threading import Timer
from typing import Dict, Any, List
from .base_handler import BaseHandler

# Configure logging with UTF-8 encoding
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
if sys.platform.startswith('win'):
    handler.stream = io.TextIOWrapper(handler.stream.buffer, encoding='utf-8', errors='replace')
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

class PaymentHandler(BaseHandler):
    """Handles payment processing and order completion with dual verification and subaccount splitting."""
    
    def __init__(self, config, session_manager, data_manager, whatsapp_service, payment_service, location_service, feedback_handler=None):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
        self.payment_service = payment_service
        self.location_service = location_service
        self.feedback_handler = feedback_handler
        self.subaccount_code = getattr(config, 'SUBACCOUNT_CODE', None)
        self.subaccount_percentage = getattr(config, 'SUBACCOUNT_PERCENTAGE', 30)
        self.delivery_fee = 1000
        self.service_charge_percentage = 2.5
        self.merchant_phone_number = getattr(config, 'MERCHANT_PHONE_NUMBER', None)
        self.payment_timers = {}
        if not self.feedback_handler:
            self.logger.warning("FeedbackHandler not provided, feedback collection will be skipped")
        if not self.merchant_phone_number:
            self.logger.warning("MERCHANT_PHONE_NUMBER not configured, merchant notifications will be skipped")
        self.logger.info(f"PaymentHandler initialized with subaccount {self.subaccount_code}, split percentage {self.subaccount_percentage}%, delivery fee ₦{self.delivery_fee}, service charge {self.service_charge_percentage}%, merchant phone {self.merchant_phone_number}")
    
    def handle_payment_processing_state(self, state, message, session_id):
        """Handle payment processing state - entry point from order handler."""
        self.logger.info(f"Handling payment processing for session {session_id}, message: {message}")
        
        if message == "initiate_payment":
            return self.create_payment_link(state, session_id)
        else:
            return self.whatsapp_service.create_text_message(
                session_id,
                "🔄 Processing your payment request. Please wait..."
            )
    
    def create_payment_link(self, state, session_id):
        """Create payment link for an existing order with subaccount splitting, delivery fee, service charge, and automatic monitoring."""
        try:
            self.logger.info(f"Creating payment link for session {session_id}")
            
            if not state.get("cart"):
                self.logger.warning(f"Cannot create payment - cart is empty for session {session_id}")
                state["current_state"] = "greeting"
                state["current_handler"] = "greeting_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "Your cart appears to be empty. Let's start fresh. How can I help you today?"
                )
            
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
            
            subtotal = order_data.get("total_amount", 0)
            if subtotal <= 0:
                self.logger.warning(f"Invalid subtotal amount {subtotal} for session {session_id}")
                state["current_state"] = "order_summary"
                state["current_handler"] = "order_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "⚠️ Invalid order total. Please check your cart and try again."
                )
            
            service_charge = subtotal * (self.service_charge_percentage / 100)
            total_amount_ngn = subtotal + self.delivery_fee + service_charge
            
            payment_reference = f"PAY-{order_id}"
            state["payment_reference"] = payment_reference
            
            total_amount_kobo = int(total_amount_ngn * 100)
            
            payment_data = {
                "payment_reference": payment_reference,
                "payment_method_type": "paystack",
                "delivery_fee": self.delivery_fee,
                "service_charge": service_charge,
                "phone_number": state.get("phone_number", session_id),
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
                    "delivery_address": state.get("address", "Not provided"),
                    "delivery_fee": self.delivery_fee,
                    "service_charge": service_charge,
                    "phone_number": state.get("phone_number", session_id)
                },
                subaccount_code=self.subaccount_code,
                split_percentage=self.subaccount_percentage
            )
            
            if payment_url:
                self.start_payment_monitoring(session_id, payment_reference, order_id)
                
                state["current_state"] = "awaiting_payment"
                state["current_handler"] = "payment_handler"
                self.session_manager.update_session_state(session_id, state)
                
                self.logger.info(f"Payment link created successfully for order {order_id} with subaccount {self.subaccount_code}")
                
                order_items = self.data_manager.get_order_items(order_id)
                formatted_items = self._format_order_items(order_items)
                
                return self.whatsapp_service.create_text_message(
                    session_id,
                    f"🛒 *Order Created Successfully!*\n\n"
                    f"📋 *Order ID:* {order_id}\n"
                    f"💰 *Subtotal:* ₦{subtotal:,}\n"
                    f"🚚 *Delivery Fee:* ₦{self.delivery_fee:,}\n"
                    f"💸 *Service Charge (2.5%):* ₦{service_charge:,.2f}\n"
                    f"💰 *Total:* ₦{total_amount_ngn:,.2f}\n"
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
        """Fetch order items from whatsapp_order_details table using DataManager."""
        return self.data_manager.get_order_items(order_id)
    
    def _format_order_items(self, items: List[Dict], for_template: bool = False) -> str:
        """Format order items for display, assuming database amounts are in NGN."""
        if not items:
            return "No items found."
        formatted = []
        for item in items:
            item_name = item.get("item_name", "Unknown Item")
            quantity = item.get("quantity", 0)
            unit_price = item.get("unit_price", 0.0)
            subtotal = item.get("subtotal", 0.0)
            item_str = f"{item_name} (x{quantity}): ₦{int(subtotal):,}"
            formatted.append(item_str)
        
        if for_template:
            return " | ".join(formatted)
        return "\n".join(f"- {item}" for item in formatted)
    
    def _send_payment_success_message(self, session_id: str, order_id: str, total_amount: float, items: List[Dict], delivery_address: str, maps_info: str = ""):
        """Send payment success message to customer and notify merchant using Meta API template."""
        try:
            # Customer notification (unchanged)
            order_data = self.data_manager.get_order_by_id(order_id)
            service_charge = order_data.get("service_charge", 0) if order_data else 0
            formatted_items = self._format_order_items(items, for_template=False)
            customer_message = (
                f"✅ *Payment Successful!*\n\n"
                f"📋 *Order ID:* {order_id}\n"
                f"💰 *Subtotal:* ₦{order_data.get('total_amount', 0):,}\n"
                f"🚚 *Delivery Fee:* ₦{self.delivery_fee:,}\n"
                f"💸 *Service Charge (2.5%):* ₦{service_charge:,.2f}\n"
                f"💰 *Total:* ₦{total_amount:,.2f}\n"
                f"🛒 *Items:*\n{formatted_items}\n"
                f"📍 *Delivery Address:* {delivery_address}{maps_info}\n\n"
                f"🎉 Thank you for your order! You'll receive updates on processing and delivery."
            )
            self.whatsapp_service.create_text_message(session_id, customer_message)
            self.logger.info(f"Sent payment success text message for order {order_id} to customer {session_id}")
            
            # Merchant notification using Meta API template
            if self.merchant_phone_number:
                formatted_items_for_template = self._format_order_items(items, for_template=True)
                state = self.session_manager.get_session_state(session_id)
                customer_name = state.get("user_name", "Guest")
                try:
                    self.whatsapp_service.send_template_message(
                        phone_number=self.merchant_phone_number,
                        template_name="merchant_order",
                        parameters=[
                            order_id,
                            customer_name,
                            delivery_address,
                            formatted_items_for_template,
                            f"₦{total_amount:,.2f}",
                            f"₦{self.delivery_fee:,}",
                            f"₦{service_charge:,.2f}"
                        ]
                    )
                    self.logger.info(f"Sent merchant_order template notification for order {order_id} to {self.merchant_phone_number}")
                except Exception as e:
                    self.logger.error(f"Failed to send merchant_order template for order {order_id}: {e}", exc_info=True)
                    # Fallback to text message
                    fallback_message = (
                        f"⚠️ *New Order Alert*\n\n"
                        f"Order ID: {order_id}\n"
                        f"Customer: {customer_name}\n"
                        f"Address: {delivery_address}\n"
                        f"Please check system for full details and process order."
                    )
                    self.whatsapp_service.create_text_message(self.merchant_phone_number, fallback_message)
                    self.logger.info(f"Sent fallback merchant notification for order {order_id} to {self.merchant_phone_number}")
            else:
                self.logger.warning("Merchant phone number not configured, skipping merchant notification")
                
        except Exception as e:
            self.logger.error(f"Error sending payment success messages for order {order_id}: {e}", exc_info=True)
            # Send fallback merchant notification if primary fails
            if self.merchant_phone_number:
                fallback_message = (
                    f"⚠️ *New Order Alert*\n\n"
                    f"Order ID: {order_id}\n"
                    f"Customer: {self.session_manager.get_session_state(session_id).get('user_name', 'Guest')}\n"
                    f"Address: {delivery_address}\n"
                    f"Please check system for full details and process order."
                )
                self.whatsapp_service.create_text_message(self.merchant_phone_number, fallback_message)
                self.logger.info(f"Sent fallback merchant notification for order {order_id} to {self.merchant_phone_number}")
    
    def start_payment_monitoring(self, session_id, payment_reference, order_id):
        """Start monitoring payment status every minute for up to 15 minutes."""
        self.logger.info(f"Starting payment monitoring for order {order_id}, reference {payment_reference}")
        
        def check_payment_status(attempt=1, max_attempts=15):
            """Check payment status and handle accordingly."""
            try:
                payment_status, payment_data = self.payment_service.verify_payment_detailed(payment_reference)
                
                if payment_status:
                    self.logger.info(f"Payment verified for order {order_id} on attempt {attempt}")
                    self.handle_successful_auto_payment(session_id, order_id, payment_reference)
                    
                    if session_id in self.payment_timers:
                        self.payment_timers[session_id].cancel()
                        del self.payment_timers[session_id]
                    return
                
                self.logger.info(f"Payment not yet verified for order {order_id}, attempt {attempt}/{max_attempts}")
                
                if attempt == 5:
                    self.send_payment_reminder(session_id, order_id, payment_reference)
                
                if attempt < max_attempts:
                    timer = Timer(60, lambda: check_payment_status(attempt + 1, max_attempts))
                    self.payment_timers[session_id] = timer
                    timer.start()
                else:
                    self.logger.info(f"Payment monitoring expired for order {order_id} after {max_attempts} attempts")
                    self.handle_payment_timeout(session_id, order_id, payment_reference)
                    
                    if session_id in self.payment_timers:
                        del self.payment_timers[session_id]
                        
            except Exception as e:
                self.logger.error(f"Error in payment monitoring for order {order_id}: {e}")
                if attempt < max_attempts:
                    timer = Timer(60, lambda: check_payment_status(attempt + 1, max_attempts))
                    self.payment_timers[session_id] = timer
                    timer.start()
        
        check_payment_status()
    
    def handle_successful_auto_payment(self, session_id, order_id, payment_reference):
        """Handle successful payment detected automatically."""
        try:
            payment_verified, payment_data = self.payment_service.verify_payment_detailed(payment_reference)
            
            if not payment_verified:
                self.logger.warning(f"handle_successful_auto_payment called but payment not verified for {payment_reference}")
                return
            
            order_data = self.data_manager.get_order_by_payment_reference(payment_reference)
            if order_data:
                service_charge = order_data.get("service_charge", 0)
                if service_charge == 0 and order_data.get("total_amount", 0) > 0:
                    service_charge = order_data["total_amount"] * (self.service_charge_percentage / 100)
                    self.logger.warning(f"Service charge was 0 for order {order_id}, recalculated to ₦{service_charge:,.2f}")
                success = self.data_manager.update_order_status(
                    order_id,
                    "confirmed",
                    {
                        "payment_reference": payment_reference,
                        "payment_method_type": payment_data.get("payment_method_type", "paystack"),
                        "delivery_fee": self.delivery_fee,
                        "service_charge": service_charge,
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
                return
            
            state = self.session_manager.get_session_state(session_id)
            state["current_state"] = "order_confirmation"
            state["current_handler"] = "payment_handler"
            state["cart"] = {}
            self.session_manager.update_session_state(session_id, state)
            
            try:
                if hasattr(self, 'lead_tracking_handler') and self.lead_tracking_handler:
                    self.lead_tracking_handler.track_order_conversion(session_id, order_id, order_data["total_amount"] + self.delivery_fee + service_charge)
                else:
                    self.logger.debug("Lead tracking handler not available for order conversion tracking")
            except Exception as e:
                self.logger.error(f"Error tracking order conversion: {e}")
            
            try:
                self.session_manager.extend_session_for_paid_user(session_id, order_id, hours=24)
                self.logger.info(f"Extended session for paid user {session_id} for 24 hours")
            except Exception as e:
                self.logger.error(f"Error extending paid user session: {e}")
            
            try:
                if hasattr(self, 'order_tracking_handler') and self.order_tracking_handler:
                    self.order_tracking_handler.update_order_status(
                        order_id, 
                        "received", 
                        "Your order has been received and is being processed."
                    )
            except Exception as e:
                self.logger.error(f"Error initializing order status: {e}")
            
            maps_info = self._generate_maps_info(state)
            order_items = self.data_manager.get_order_items(order_id)
            total_amount = order_data.get("total_amount", 0) + self.delivery_fee + service_charge
            self._send_payment_success_message(
                session_id,
                order_id,
                total_amount,
                order_items,
                state.get("address", "Not provided"),
                maps_info
            )
            
            # Explicitly trigger feedback collection with enhanced logging
            try:
                if self.feedback_handler:
                    self.logger.info(f"Initiating feedback collection for order {order_id}, session {session_id}")
                    self.feedback_handler.initiate_feedback_request(state, session_id, order_id)
                else:
                    self.logger.warning(f"FeedbackHandler not available for order {order_id}, skipping feedback collection")
            except Exception as e:
                self.logger.error(f"Failed to initiate feedback collection for order {order_id}: {e}", exc_info=True)
            
        except Exception as e:
            self.logger.error(f"Error handling successful auto payment for order {order_id}: {e}", exc_info=True)
    
    def send_payment_reminder(self, session_id, order_id, payment_reference):
        """Send payment reminder after 5 minutes."""
        try:
            state = self.session_manager.get_session_state(session_id)
            
            order_data = self.data_manager.get_order_by_payment_reference(payment_reference)
            if not order_data:
                self.logger.error(f"Order data not found for reminder for order {order_id}.")
                return
            
            subtotal = order_data.get("total_amount", 0)
            service_charge = order_data.get("service_charge", subtotal * (self.service_charge_percentage / 100))
            if service_charge == 0 and subtotal > 0:
                self.logger.warning(f"Service charge was 0 for order {order_id}, recalculated to ₦{service_charge:,.2f}")
            total_amount = subtotal + self.delivery_fee + service_charge
            
            customer_email = self.payment_service.generate_customer_email(
                state.get("phone_number", session_id), 
                state.get("user_name", "Guest")
            )
            
            payment_url = self.payment_service.create_payment_link(
                amount=int(total_amount * 100),
                email=customer_email,
                reference=payment_reference,
                customer_name=state.get("user_name", "Guest"),
                customer_phone=state.get("phone_number", session_id),
                metadata={
                    "order_id": order_id,
                    "delivery_address": state.get("address", "Not provided"),
                    "delivery_fee": self.delivery_fee,
                    "service_charge": service_charge,
                    "phone_number": state.get("phone_number", session_id),
                    "reminder": True
                },
                subaccount_code=self.subaccount_code,
                split_percentage=self.subaccount_percentage
            )
            
            if payment_url:
                order_items = self.data_manager.get_order_items(order_id)
                formatted_items = self._format_order_items(order_items)
                
                reminder_message = (
                    f"⏰ *Payment Reminder*\n\n"
                    f"We notice your payment for Order #{order_id} hasn't been completed yet.\n\n"
                    f"💰 *Subtotal:* ₦{subtotal:,}\n"
                    f"🚚 *Delivery Fee:* ₦{self.delivery_fee:,}\n"
                    f"💸 *Service Charge (2.5%):* ₦{service_charge:,.2f}\n"
                    f"💰 *Total Amount:* ₦{total_amount:,.2f}\n"
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
            success = self.data_manager.update_order_status(order_id, "expired", {})
            if not success:
                self.logger.error(f"Failed to update order {order_id} to expired status for session {session_id}")
            
            state = self.session_manager.get_session_state(session_id)
            state["cart"] = {}
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            
            order_items = self.data_manager.get_order_items(order_id)
            formatted_items = self._format_order_items(order_items)
            order_data = self.data_manager.get_order_by_id(order_id)
            service_charge = order_data.get("service_charge", 0) if order_data else 0
            subtotal = order_data.get("total_amount", 0) if order_data else 0
            total_amount = subtotal + self.delivery_fee + service_charge
            
            timeout_message = (
                f"⏰ *Payment Expired*\n\n"
                f"Your payment for Order #{order_id} has expired after 15 minutes.\n\n"
                f"💰 *Subtotal:* ₦{subtotal:,}\n"
                f"🚚 *Delivery Fee:* ₦{self.delivery_fee:,}\n"
                f"💸 *Service Charge (2.5%):* ₦{service_charge:,.2f}\n"
                f"💰 *Total:* ₦{total_amount:,.2f}\n"
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
        
        if message.lower() == "paid":
            self.logger.info(f"Received 'paid' command for session {session_id}, attempting manual verification for ref: {payment_reference}")
            return self._handle_manual_payment_verification(state, session_id, payment_reference)
        
        elif message.lower() in ["cancel", "cancel_order"]:
            return self._handle_payment_cancellation(state, session_id)
        
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
                self.stop_payment_monitoring(session_id)
                
                service_charge = order_data.get("service_charge", 0)
                if service_charge == 0 and order_data.get("total_amount", 0) > 0:
                    service_charge = order_data["total_amount"] * (self.service_charge_percentage / 100)
                    self.logger.warning(f"Service charge was 0 for order {order_data['order_id']}, recalculated to ₦{service_charge:,.2f}")
                
                success = self.data_manager.update_order_status(
                    order_data["order_id"],
                    "confirmed",
                    {
                        "payment_reference": payment_reference,
                        "payment_method_type": payment_data.get("payment_method_type", "paystack"),
                        "delivery_fee": self.delivery_fee,
                        "service_charge": service_charge,
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
                state["cart"] = {}
                self.session_manager.update_session_state(session_id, state)
                
                try:
                    if hasattr(self, 'lead_tracking_handler') and self.lead_tracking_handler:
                        self.lead_tracking_handler.track_order_conversion(session_id, order_data["order_id"], order_data["total_amount"] + self.delivery_fee + service_charge)
                    else:
                        self.logger.debug("Lead tracking handler not available for order conversion tracking")
                except Exception as e:
                    self.logger.error(f"Error tracking order conversion: {e}")
                
                order_items = self.data_manager.get_order_items(order_data["order_id"])
                maps_info = self._generate_maps_info(state)
                total_amount = order_data.get("total_amount", 0) + self.delivery_fee + service_charge
                self._send_payment_success_message(
                    session_id,
                    order_data["order_id"],
                    total_amount,
                    order_items,
                    state.get("address", "Not provided"),
                    maps_info
                )
                
                # Explicitly trigger feedback collection with enhanced logging
                try:
                    if self.feedback_handler:
                        self.logger.info(f"Initiating feedback collection for order {order_data['order_id']}, session {session_id}")
                        self.feedback_handler.initiate_feedback_request(state, session_id, order_data['order_id'])
                    else:
                        self.logger.warning(f"FeedbackHandler not available for order {order_data['order_id']}, skipping feedback collection")
                except Exception as e:
                    self.logger.error(f"Failed to initiate feedback collection for order {order_data['order_id']}: {e}", exc_info=True)
                
                return {"message": "Payment confirmed and feedback initiated"}
                
            elif not payment_verified:
                self.logger.info(f"Manual payment verification failed for reference {payment_reference}. Paystack status: {payment_data.get('status', 'N/A') if payment_data else 'N/A'}")
                order_items = self.data_manager.get_order_items(order_data["order_id"] if order_data else "0")
                formatted_items = self._format_order_items(order_items)
                service_charge = order_data.get("service_charge", 0) if order_data else 0
                subtotal = order_data.get("total_amount", 0) if order_data else 0
                total_amount = subtotal + self.delivery_fee + service_charge
                return self.whatsapp_service.create_text_message(
                    session_id,
                    f"⏳ *Payment Not Yet Received*\n\n"
                    f"📋 *Order ID:* {order_data['order_id'] if order_data else 'N/A'}\n"
                    f"💰 *Subtotal:* ₦{subtotal:,}\n"
                    f"🚚 *Delivery Fee:* ₦{self.delivery_fee:,}\n"
                    f"💸 *Service Charge (2.5%):* ₦{service_charge:,.2f}\n"
                    f"💰 *Total:* ₦{total_amount:,.2f}\n"
                    f"🛒 *Items:* {formatted_items}\n\n"
                    f"💳 Please:\n"
                    f"1️⃣ Complete the payment using the link provided\n"
                    f"2️⃣ Wait a moment for processing\n"
                    f"3️⃣ Try sending 'paid' again\n\n"
                    f"🔄 We're also checking automatically every minute.\n"
                    f"❌ Send 'cancel' to cancel the order."
                )
            else:
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
            self.stop_payment_monitoring(session_id)
            
            if state.get("payment_reference"):
                order_data = self.data_manager.get_order_by_payment_reference(state["payment_reference"])
                if order_data:
                    success = self.data_manager.update_order_status(order_data["order_id"], "cancelled", {})
                    if not success:
                        self.logger.error(f"Failed to update order {order_data['order_id']} to cancelled status for session {session_id}")
                else:
                    self.logger.warning(f"No order found for payment reference {state['payment_reference']} during cancellation.")
            
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
        order_data = self.data_manager.get_order_by_payment_reference(payment_reference)
        
        if order_data and order_data.get("status") == "confirmed":
            self.logger.info(f"User sent message while in awaiting_payment, but order {order_data['order_id']} was already confirmed.")
            self.stop_payment_monitoring(session_id)
            state["current_state"] = "order_confirmation"
            state["current_handler"] = "payment_handler"
            state["cart"] = {}
            self.session_manager.update_session_state(session_id, state)
            
            order_items = self.data_manager.get_order_items(order_data["order_id"])
            maps_info = self._generate_maps_info(state)
            service_charge = order_data.get("service_charge", 0)
            total_amount = order_data.get("total_amount", 0) + self.delivery_fee + service_charge
            self._send_payment_success_message(
                session_id,
                order_data["order_id"],
                total_amount,
                order_items,
                state.get("address", "Not provided"),
                maps_info
            )
            
            # Explicitly trigger feedback collection with enhanced logging
            try:
                if self.feedback_handler:
                    self.logger.info(f"Initiating feedback collection for order {order_data['order_id']}, session {session_id}")
                    self.feedback_handler.initiate_feedback_request(state, session_id, order_data['order_id'])
                else:
                    self.logger.warning(f"FeedbackHandler not available for order {order_data['order_id']}, skipping feedback collection")
            except Exception as e:
                self.logger.error(f"Failed to initiate feedback collection for order {order_data['order_id']}: {e}", exc_info=True)
            
            return {"message": "Payment already confirmed, text message and feedback initiated"}
        else:
            self.logger.info(f"User sent message while still awaiting payment for order {state.get('order_id', 'N/A')}.")
            order_id = state.get("order_id", "0")
            order_items = self.data_manager.get_order_items(order_id)
            formatted_items = self._format_order_items(order_items)
            service_charge = order_data.get("service_charge", 0) if order_data else 0
            subtotal = order_data.get("total_amount", 0) if order_data else 0
            total_amount = subtotal + self.delivery_fee + service_charge
            
            return self.whatsapp_service.create_text_message(
                session_id,
                f"🔄 *Payment Monitoring Active*\n\n"
                f"📋 *Order ID:* {state.get('order_id', 'N/A')}\n"
                f"💰 *Subtotal:* ₦{subtotal:,}\n"
                f"🚚 *Delivery Fee:* ₦{self.delivery_fee:,}\n"
                f"💸 *Service Charge (2.5%):* ₦{service_charge:,.2f}\n"
                f"💰 *Total:* ₦{total_amount:,.2f}\n"
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
    
    def handle_order_confirmation_state(self, state, session_id):
        """Handle order confirmation state."""
        order_id = state.get("order_id")
        order_data = self.data_manager.get_order_by_payment_reference(state.get("payment_reference"))
        
        if order_data and order_data["status"] == "confirmed":
            state["cart"] = {}
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            
            order_items = self.data_manager.get_order_items(order_id)
            maps_info = self._generate_maps_info(state)
            service_charge = order_data.get("service_charge", 0)
            total_amount = order_data.get("total_amount", 0) + self.delivery_fee + service_charge
            self._send_payment_success_message(
                session_id,
                order_id,
                total_amount,
                order_items,
                state.get("address", "Not provided"),
                maps_info
            )
            
            # Explicitly trigger feedback collection with enhanced logging
            try:
                if self.feedback_handler:
                    self.logger.info(f"Initiating feedback collection for order {order_id}, session {session_id}")
                    self.feedback_handler.initiate_feedback_request(state, session_id, order_id)
                else:
                    self.logger.warning(f"FeedbackHandler not available for order {order_id}, skipping feedback collection")
            except Exception as e:
                self.logger.error(f"Failed to initiate feedback collection for order {order_id}: {e}", exc_info=True)
            
            return {"message": "Order confirmed, text message and feedback initiated"}
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
                
                if not order_data:
                    self.logger.error(f"No order found for payment reference {payment_reference} from webhook.")
                    return
                
                session_id = order_data.get("phone_number")
                if not session_id:
                    session_id = webhook_data.get("data", {}).get("metadata", {}).get("phone_number")
                    if not session_id:
                        self.logger.warning(f"No phone_number found in order_data or webhook metadata for reference {payment_reference}. Processing order status update without user notifications.")
                
                service_charge = order_data.get("service_charge", 0)
                if service_charge == 0 and order_data.get("total_amount", 0) > 0:
                    service_charge = order_data["total_amount"] * (self.service_charge_percentage / 100)
                    self.logger.warning(f"Service charge was 0 for order {order_data['order_id']}, recalculated to ₦{service_charge:,.2f}")
                
                success = self.data_manager.update_order_status(
                    order_data["order_id"],
                    "confirmed",
                    {
                        "payment_reference": payment_reference,
                        "payment_method_type": webhook_data["data"].get("payment_method_type", "paystack"),
                        "delivery_fee": self.delivery_fee,
                        "service_charge": service_charge,
                        "subaccount_split": {
                            "subaccount_code": self.subaccount_code,
                            "percentage": self.subaccount_percentage
                        } if self.subaccount_code else None
                    }
                )
                if not success:
                    self.logger.error(f"Failed to update order {order_data['order_id']} to confirmed status for webhook")
                    return
                
                if session_id:
                    self.stop_payment_monitoring(session_id)
                    
                    state = session_manager.get_session_state(session_id)
                    state["current_state"] = "order_confirmation"
                    state["current_handler"] = "payment_handler"
                    state["cart"] = {}
                    session_manager.update_session_state(session_id, state)
                    
                    try:
                        if hasattr(self, 'lead_tracking_handler') and self.lead_tracking_handler:
                            self.lead_tracking_handler.track_order_conversion(session_id, order_data["order_id"], order_data["total_amount"] + self.delivery_fee + service_charge)
                        else:
                            self.logger.debug("Lead tracking handler not available for order conversion tracking")
                    except Exception as e:
                        self.logger.error(f"Error tracking order conversion: {e}")
                    
                    order_items = self.data_manager.get_order_items(order_data["order_id"])
                    maps_info = self._generate_maps_info(state)
                    total_amount = order_data["total_amount"] + self.delivery_fee + service_charge
                    self._send_payment_success_message(
                        session_id,
                        order_data["order_id"],
                        total_amount,
                        order_items,
                        order_data.get("address", "Not provided"),
                        maps_info
                    )
                    
                    # Explicitly trigger feedback collection with enhanced logging
                    try:
                        if self.feedback_handler:
                            self.logger.info(f"Initiating feedback collection for order {order_data['order_id']}, session {session_id}")
                            self.feedback_handler.initiate_feedback_request(state, session_id, order_data['order_id'])
                        else:
                            self.logger.warning(f"FeedbackHandler not available for order {order_data['order_id']}, skipping feedback collection")
                    except Exception as e:
                        self.logger.error(f"Failed to initiate feedback collection for order {order_data['order_id']}: {e}", exc_info=True)
                else:
                    self.logger.info(f"Order {order_data['order_id']} confirmed, but no session_id available. Sending merchant notification only.")
                    # Send merchant notification even without session_id
                    order_items = self.data_manager.get_order_items(order_data["order_id"])
                    total_amount = order_data["total_amount"] + self.delivery_fee + service_charge
                    self._send_payment_success_message(
                        session_id or order_data.get("phone_number", ""),
                        order_data["order_id"],
                        total_amount,
                        order_items,
                        order_data.get("address", "Not provided")
                    )
                    # Attempt to trigger feedback using order_data phone_number if available
                    try:
                        if self.feedback_handler and order_data.get("phone_number"):
                            state = session_manager.get_session_state(order_data["phone_number"]) or {}
                            self.logger.info(f"Initiating feedback collection for order {order_data['order_id']} using order_data phone_number {order_data['phone_number']}")
                            self.feedback_handler.initiate_feedback_request(state, order_data["phone_number"], order_data['order_id'])
                        else:
                            self.logger.warning(f"FeedbackHandler or phone_number not available for order {order_data['order_id']}, skipping feedback collection")
                    except Exception as e:
                        self.logger.error(f"Failed to initiate feedback collection for order {order_data['order_id']} using order_data phone_number: {e}", exc_info=True)
                
            else:
                self.logger.info(f"Ignored webhook event: {event}")
                
        except Exception as e:
            self.logger.error(f"Error handling payment webhook for reference {payment_reference}: {e}", exc_info=True)
    
    def cleanup_expired_monitoring(self):
        """Clean up expired payment monitoring timers."""
        try:
            expired_sessions = []
            
            for session_id in list(self.payment_timers.keys()):
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
            if self.feedback_handler:
                self.logger.info(f"Attempting feedback collection for order {order_id}, session {session_id}")
                self.feedback_handler.initiate_feedback_request(state, session_id, order_id)
                self.logger.info(f"Successfully initiated feedback collection for order {order_id}")
            else:
                self.logger.warning(f"FeedbackHandler not available for order {order_id}, skipping feedback collection")
        except Exception as e:
            self.logger.error(f"Failed to initiate feedback collection for order {order_id}: {e}", exc_info=True)
    
    def _initiate_feedback_collection_webhook(self, session_id: str, order_id: str, session_manager) -> None:
        """Initiate feedback collection for webhook payments."""
        try:
            if self.feedback_handler:
                state = session_manager.get_session_state(session_id) or {}
                self.logger.info(f"Attempting webhook feedback collection for order {order_id}, session {session_id}")
                self.feedback_handler.initiate_feedback_request(state, session_id, order_id)
                self.logger.info(f"Successfully initiated webhook feedback collection for order {order_id}")
            else:
                self.logger.warning(f"FeedbackHandler not available for order {order_id}, skipping webhook feedback collection")
        except Exception as e:
            self.logger.error(f"Failed to initiate webhook feedback collection for order {order_id}: {e}", exc_info=True)
    
    def handle_back_to_main(self, state, session_id):
        """Return to main menu."""
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        self.session_manager.update_session_state(session_id, state)
        return self.whatsapp_service.create_text_message(
            session_id,
            "🔙 Back to main menu. How can I assist you today?"
        )