# app/__init__.py
import logging # Already there
from flask import Flask
from .config import Config, configure_logging
from .views import webhook_blueprint

def create_app():
    app = Flask(__name__)

    config_obj = Config()
    app.config.from_object(config_obj)

    # --- ADD THESE DEBUG LINES ---
    logging.info(f"DEBUG: APP_SECRET from os.getenv: {os.getenv('APP_SECRET')}")
    logging.info(f"DEBUG: APP_SECRET in app.config: {app.config.get('APP_SECRET')}")
    if not app.config.get('APP_SECRET'):
        logging.error("CRITICAL ERROR: APP_SECRET is not set in Flask app.config!")
    # --- END DEBUG LINES ---

    configure_logging() # Ensure this is called after logging imports are set up

    app.register_blueprint(webhook_blueprint)

    return app

app = create_app()