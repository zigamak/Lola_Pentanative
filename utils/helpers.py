"""
Utility helper functions for the WhatsApp Bot.
"""

import re
import datetime
import uuid

def format_cart(cart):
    """
    Formats the items in the user's cart into a human-readable string.
    
    Args:
        cart (dict): The user's shopping cart.
        
    Returns:
        str: A formatted string representing the cart contents and total.
    """
    if not cart:
        return "Your cart is empty."
    
    cart_text = "🛒 *Your Cart:*\n"
    total = 0
    
    for item, details in cart.items():
        subtotal = details["price"] * details["quantity"]
        cart_text += f"• {details['quantity']} x {item} (₦{details['price']:,}) = ₦{subtotal:,}\n"
        total += subtotal
    
    cart_text += f"\n💰 *Total: ₦{total:,}*"
    return cart_text

def truncate_title(title, max_length=24):
    """
    Truncates a string title to a maximum length, ensuring the price part (₦X) is preserved
    and the name is truncated if necessary. This is important for WhatsApp list/button titles.
    
    Args:
        title (str): The title to truncate
        max_length (int): Maximum length allowed
        
    Returns:
        str: Truncated title
    """
    if len(title) <= max_length:
        return title

    # Attempt to split by price part to preserve it
    split_point = title.rfind(" (₦")
    if split_point != -1:
        item_name = title[:split_point]
        price_part = title[split_point:]  # Includes " (₦Price)"
        
        # Calculate available length for the item name
        remaining_length_for_name = max_length - len(price_part)
        
        if remaining_length_for_name > 0:
            truncated_name = item_name[:remaining_length_for_name].rstrip()
            return f"{truncated_name}{price_part}"
    
    # Fallback: if no price part or if truncation logic fails, just truncate the whole string
    return title[:max_length].rstrip() + "..." if len(title) > max_length else title

def validate_phone_number(phone_number):
    """
    Validate phone number format.
    
    Args:
        phone_number (str): Phone number to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    # Remove any spaces, dashes, or other characters
    cleaned = re.sub(r'[^\d+]', '', phone_number)
    
    # Check if it's a valid international format
    if cleaned.startswith('+') and len(cleaned) >= 10:
        return True
    
    # Check if it's a valid local format (adjust based on your country)
    if len(cleaned) >= 10:
        return True
    
    return False

def validate_email(email):
    """
    Validate email format.
    
    Args:
        email (str): Email to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def generate_unique_id(prefix=""):
    """
    Generate a unique ID with optional prefix.
    
    Args:
        prefix (str): Optional prefix for the ID
        
    Returns:
        str: Unique ID
    """
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    unique_part = str(uuid.uuid4())[:8]
    
    if prefix:
        return f"{prefix}-{timestamp}-{unique_part}"
    else:
        return f"{timestamp}-{unique_part}"

def format_currency(amount, currency="₦"):
    """
    Format currency amount with proper separators.
    
    Args:
        amount (float/int): Amount to format
        currency (str): Currency symbol
        
    Returns:
        str: Formatted currency string
    """
    return f"{currency}{amount:,.2f}" if isinstance(amount, float) else f"{currency}{amount:,}"

def parse_name(full_name):
    """
    Parse full name into first and last name.
    
    Args:
        full_name (str): Full name string
        
    Returns:
        tuple: (first_name, last_name)
    """
    if not full_name or full_name.strip() == "":
        return "Customer", "Customer"
    
    name_parts = full_name.strip().split()
    
    if len(name_parts) == 1:
        # If only one name, use it as both first and last name
        return name_parts[0], name_parts[0]
    elif len(name_parts) == 2:
        return name_parts[0], name_parts[1]
    else:
        # More than 2 names: first name is first part, last name is everything else joined
        return name_parts[0], " ".join(name_parts[1:])

def sanitize_input(text, max_length=1000):
    """
    Sanitize user input text.
    
    Args:
        text (str): Input text to sanitize
        max_length (int): Maximum allowed length
        
    Returns:
        str: Sanitized text
    """
    if not text:
        return ""
    
    # Remove excessive whitespace
    sanitized = re.sub(r'\s+', ' ', text.strip())
    
    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip()
    
    return sanitized

def format_timestamp(timestamp=None, format_str="%Y-%m-%d %H:%M:%S"):
    """
    Format timestamp to readable string.
    
    Args:
        timestamp (datetime): Timestamp to format (default: now)
        format_str (str): Format string
        
    Returns:
        str: Formatted timestamp
    """
    if timestamp is None:
        timestamp = datetime.datetime.now()
    
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.datetime.fromisoformat(timestamp)
        except ValueError:
            return timestamp  # Return original if parsing fails
    
    return timestamp.strftime(format_str)

def calculate_time_ago(timestamp):
    """
    Calculate human-readable time ago string.
    
    Args:
        timestamp (datetime/str): Timestamp to compare
        
    Returns:
        str: Human-readable time ago string
    """
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.datetime.fromisoformat(timestamp)
        except ValueError:
            return "Unknown time"
    
    now = datetime.datetime.now()
    diff = now - timestamp
    
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"