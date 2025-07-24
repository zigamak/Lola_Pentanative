from flask import Flask

from .views import webhook_blueprint


def create_app():
    app = Flask(__name__)

    # Load configurations and logging settings
    load_configurations(app)
    configure_logging()

    # Register blueprints
    app.register_blueprint(webhook_blueprint)

    return app
