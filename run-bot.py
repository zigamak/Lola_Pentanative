#!/usr/bin/env python3
"""
WhatsApp Bot Runner Script

This script provides a convenient way to run the WhatsApp bot with different configurations
and includes startup checks to ensure everything is properly configured.
"""

import os
import sys
import logging
import json
from pathlib import Path

def check_environment():
    """Check if all required environment variables and files are present."""
    print("🔍 Checking environment setup...")
    
    # Determine project root
    project_root = Path.cwd()
    menu_file = os.getenv('MENU_FILE_PATH', 'menu.json')
    menu_path = project_root / menu_file
    
    # Check if .env file exists
    env_path = project_root / '.env'
    if not env_path.exists():
        print("❌ ERROR: .env file not found!")
        print("   Please create a .env file with your configuration.")
        print("   See the documentation for required environment variables.")
        return False
    
    # Check required environment variables
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path)
    
    required_vars = [
        'WHATSAPP_ACCESS_TOKEN',
        'WHATSAPP_PHONE_NUMBER_ID', 
        'VERIFY_TOKEN',
        'PAYSTACK_SECRET_KEY'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ ERROR: Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("   Please add these to your .env file.")
        return False
    
    # Check if menu.json exists and is readable
    if not menu_path.exists():
        print(f"❌ ERROR: {menu_file} not found at {menu_path}!")
        print("   Please provide a valid menu.json file with your menu data.")
        return False
    
    # Validate menu.json content
    try:
        with open(menu_path, 'r') as f:
            menu_data = json.load(f)
        if not isinstance(menu_data, dict):
            print(f"❌ ERROR: {menu_file} must contain a dictionary of categories.")
            return False
        logger.info(f"Menu categories loaded: {list(menu_data.keys())}")
    except json.JSONDecodeError as e:
        print(f"❌ ERROR: Invalid {menu_file} format: {e}")
        print(f"   Please ensure {menu_file} contains valid JSON data.")
        return False
    except Exception as e:
        print(f"❌ ERROR: Could not read {menu_file}: {e}")
        return False
    
    # Check directory structure
    required_dirs = ['handlers', 'services', 'utils']
    for directory in required_dirs:
        dir_path = project_root / directory
        if not dir_path.exists():
            print(f"❌ ERROR: Directory '{directory}' not found!")
            print("   Please ensure the project structure is correct.")
            return False
        
        # Check for __init__.py files
        init_file = dir_path / '__init__.py'
        if not init_file.exists():
            print(f"⚠️  WARNING: {init_file} not found. Creating...")
            init_file.touch()
    
    print("✅ Environment check completed successfully!")
    return True

def setup_logging(debug=False):
    """Setup logging configuration."""
    log_level = logging.DEBUG if debug else logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("bot.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Reduce noise from requests library
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

def print_startup_info():
    """Print startup information and instructions."""
    print("\n" + "="*60)
    print("🤖 WhatsApp Food Ordering Bot")
    print("="*60)
    print("📱 Bot Features:")
    print("   • Menu browsing and ordering")
    print("   • Paystack payment integration")
    print("   • Customer enquiries and complaints")
    print("   • Session management with timeouts")
    print("   • Persistent user data storage")
    print("\n📋 Next Steps:")
    print("   1. Make sure ngrok is running: ngrok http 8000")
    print("   2. Update your WhatsApp webhook URL in Meta Developer Console")
    print("   3. Test the bot by sending a message to your WhatsApp number")
    print("\n🔗 Important URLs:")
    print("   • Webhook: http://0.0.0.0:8000/webhook")
    print("   • Payment Callback: http://0.0.0.0:8000/payment-callback")
    print("   • Logs: Check bot.log file for detailed logs")
    print("="*60 + "\n")

def main():
    """Main function to run the WhatsApp bot."""
    import argparse
    
    parser = argparse.ArgumentParser(description='WhatsApp Food Ordering Bot')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--port', type=int, default=8000, help='Port to run the server on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to run the server on')
    parser.add_argument('--no-check', action='store_true', help='Skip environment checks')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(debug=args.debug)
    logger = logging.getLogger(__name__)
    
    try:
        # Check environment unless --no-check is specified
        if not args.no_check:
            if not check_environment():
                logger.error("Environment check failed. Please fix the issues above.")
                sys.exit(1)
        
        # Print startup information
        print_startup_info()
        
        # Import and run the Flask app
        logger.info("Attempting to import Flask app...")
        try:
            from app import app
        except ImportError as e:
            logger.error(f"Failed to import app: {e}")
            print(f"❌ ERROR: Could not import app: {e}")
            print("   Ensure app.py exists and has no circular imports.")
            print("   Run: pip install -r requirements.txt")
            sys.exit(1)
        
        logger.info("Starting WhatsApp bot server...")
        app.run(
            host=args.host,
            port=args.port,
            debug=args.debug,
            use_reloader=False  # Disable reloader to avoid double startup messages
        )
        
    except KeyboardInterrupt:
        logger.info("Bot server stopped by user.")
        print("\n👋 Bot server stopped. Goodbye!")
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"❌ ERROR: An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()