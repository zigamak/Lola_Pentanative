# app/__init__.py
from flask import Flask
# Import the Config class directly, and configure_logging if it's a standalone function
from app.config import Config, configure_logging
from .views import webhook_blueprint


def create_app():
    app = Flask(__name__)

    # Instantiate the Config class to load environment variables
    config_obj = Config()

    # Load configurations into the Flask app from the Config object
    # This will set app.config['DB_URL'] = config_obj.DB_URL, etc.
    app.config.from_object(config_obj)

    # Configure logging (assuming configure_logging is a standalone function in config.py)
    configure_logging()

    # Register blueprints
    app.register_blueprint(webhook_blueprint)

    return app
