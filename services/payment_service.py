import os
import logging
import datetime
import random
import requests
from utils.helpers import parse_name

logger = logging.getLogger(__name__)

class PaymentService:
    """Handles payment processing and verification."""
    
    def __init__(self, config):
        self.config = config
        self.paystack_secret_key = config.PAYSTACK_SECRET_KEY
        self.paystack_public_key = config.PAYSTACK_PUBLIC_KEY
        self.callback_base_url = config.CALLBACK_BASE_URL
        
        logger.info("PaymentService initialized")
    
    def generate_order_id(self):
        """Generate a unique order ID."""
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        random_num = random.randint(1000, 9999)
        return f"ORDER-{timestamp}-{random_num}"
    
    def calculate_cart_total(self, cart):
        """Calculate total amount in kobo (Paystack uses kobo)."""
        total = 0
        for item, details in cart.items():
            subtotal = details["price"] * details["quantity"]
            total += subtotal
        return total * 100  # Convert to kobo
    
    def generate_customer_email(self, phone_number, user_name):
        """Generate a customer email from name and phone."""
        first_name, last_name = parse_name(user_name)
        
        # Create email from name and phone
        clean_first_name = ''.join(c.lower() for c in first_name if c.isalnum())
        clean_phone = phone_number.replace('+', '').replace('-', '').replace(' ', '')[-4:]
        
        return f"{clean_first_name}{clean_phone}@lola.com"
    
    def create_payment_link(self, amount, email, reference, customer_name, customer_phone, metadata=None, subaccount_code=None, split_percentage=None):
        """Create a Paystack payment link with optional subaccount splitting."""
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {self.paystack_secret_key}",
            "Content-Type": "application/json"
        }
        
        # Parse customer name
        first_name, last_name = parse_name(customer_name)
        
        # Base data for the Paystack API request
        data = {
            "amount": amount,  # Amount in kobo
            "email": email,
            "reference": reference,
            "callback_url": f"{self.callback_base_url}",
            "customer": {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "phone": customer_phone
            },
            "metadata": {
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "first_name": first_name,
                "last_name": last_name,
                **(metadata or {})
            }
        }
        
        # Add subaccount splitting if provided
        if subaccount_code and split_percentage:
            data["subaccount"] = subaccount_code
            data["transaction_charge"] = int(amount * (split_percentage / 100))  # Calculate subaccount share in kobo
            data["bearer"] = "account"  # Main account bears Paystack fees unless specified otherwise
            logger.info(f"Adding subaccount split: code={subaccount_code}, percentage={split_percentage}%")
        
        try:
            logger.info(f"Attempting to create payment link for reference: {reference} with amount: {amount}, email: {email}")
            response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            result = response.json()
            logger.debug(f"Paystack initialize response for {reference}: {result}")
            
            if result["status"]:
                logger.info(f"Payment link created for {first_name} {last_name} ({customer_phone}), URL: {result['data']['authorization_url']}")
                return result["data"]["authorization_url"]
            else:
                logger.error(f"Paystack payment link creation failed for {reference}: {result.get('message', 'Unknown error')}. Response: {result}")
                return None
                
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error creating Paystack payment link for {reference}: {http_err}. Response: {http_err.response.text}", exc_info=True)
            return None
        except requests.RequestException as e:
            logger.error(f"Network or connection error creating Paystack payment link for {reference}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating Paystack payment link for {reference}: {e}", exc_info=True)
            return None
    
    def verify_payment(self, reference):
        """Simple payment verification - returns status string."""
        verified, _ = self.verify_payment_detailed(reference)
        return "success" if verified else "failed"
    
    def verify_payment_detailed(self, reference):
        """Detailed payment verification - returns (bool, dict)."""
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {
            "Authorization": f"Bearer {self.paystack_secret_key}",
            "Content-Type": "application/json"
        }
        
        try:
            logger.info(f"Attempting to verify payment for reference: {reference}")
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            result = response.json()
            logger.debug(f"Paystack verification response for {reference}: {result}")
            
            if result["status"] and result["data"]["status"] == "success":
                payment_data = {
                    "amount": result["data"]["amount"],
                    "currency": result["data"]["currency"],
                    "reference": result["data"]["reference"],
                    "status": result["data"]["status"],
                    "gateway_response": result["data"]["gateway_response"],
                    "paid_at": result["data"]["paid_at"],
                    "channel": result["data"]["channel"],
                    "fees": result["data"].get("fees", 0),
                    "authorization": result["data"].get("authorization", {}),
                    "customer": result["data"].get("customer", {}),
                    "transaction_date": result["data"].get("transaction_date"),
                    "verification_timestamp": datetime.datetime.now().isoformat(),
                    "full_response": result  # Include full response for deeper debugging if needed
                }
                logger.info(f"Payment verified successfully for reference {reference}. Status: {result['data']['status']}")
                return True, payment_data
            else:
                current_paystack_status = result["data"]["status"] if "data" in result else "API_ERROR_NO_DATA"
                logger.warning(f"Payment not successful for reference {reference}. Paystack status: {current_paystack_status}. Response: {result}")
                return False, result.get("data", {})
                
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error verifying Paystack payment for {reference}: {http_err}. Response: {http_err.response.text}", exc_info=True)
            return False, {"error": f"HTTPError: {http_err.response.text}"}
        except requests.RequestException as e:
            logger.error(f"Network or connection error verifying Paystack payment for {reference}: {e}", exc_info=True)
            return False, {"error": f"RequestException: {e}"}
        except Exception as e:
            logger.error(f"Unexpected error verifying Paystack payment for {reference}: {e}", exc_info=True)
            return False, {"error": f"Unexpected Error: {e}"}