from abc import ABC, abstractmethod
import logging
import requests
from jinja2 import Environment, BaseLoader

from app.classes.shared.helpers import Helpers

logger = logging.getLogger(__name__)
helper = Helpers()


class WebhookProvider(ABC):
    """
    Base class for all webhook providers.

    Provides a common interface for all webhook provider implementations,
    ensuring that each provider will have a send method.
    """

    def __init__(self):
        self.jinja_env = Environment(loader=BaseLoader())

    WEBHOOK_USERNAME = "Crafty Webhooks"
    WEBHOOK_PFP_URL = (
        "https://gitlab.com/crafty-controller/crafty-4/-"
        + "/raw/master/app/frontend/static/assets/images/"
        + "Crafty_4-0.png"
    )
    CRAFTY_VERSION = helper.get_version_string()

    def _send_request(self, url, payload, headers=None):
        """Send a POST request to the given URL with the provided payload."""
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            return "Dispatch successful"
        except requests.RequestException as error:
            logger.error(error)
            raise RuntimeError(f"Failed to dispatch notification: {error}") from error

    def render_template(self, template_str, context):
        """
        Renders a Jinja2 template with the provided context.

        Args:
            template_str (str): The Jinja2 template string.
            context (dict): A dictionary containing all the variables needed for
            rendering the template.

        Returns:
            str: The rendered message.
        """
        try:
            template = self.jinja_env.from_string(template_str)
            return template.render(context)
        except Exception as error:
            logger.error(f"Error rendering Jinja2 template: {error}")
            raise

    @abstractmethod
    def send(self, server_name, title, url, message_template, event_data, **kwargs):
        """Abstract method that derived classes will implement for sending webhooks."""
