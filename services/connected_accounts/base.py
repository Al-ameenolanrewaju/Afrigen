import abc
from typing import Dict, Any

class BaseProviderAdapter(abc.ABC):
    """
    Base interface for all Connected Account provider adapters.
    The Publishing Engine and other services should interact with providers through this interface.
    """
    
    @abc.abstractmethod
    def connect(self, user_id: int, **kwargs) -> Dict[str, Any]:
        """Initiate or complete an OAuth connection."""
        pass

    @abc.abstractmethod
    def disconnect(self, user_id: int) -> Dict[str, Any]:
        """Disconnect the account and remove credentials."""
        pass

    @abc.abstractmethod
    def refresh(self, user_id: int) -> Dict[str, Any]:
        """Refresh the access token if needed/supported."""
        pass

    @abc.abstractmethod
    def test_connection(self, user_id: int) -> Dict[str, Any]:
        """Verify the stored credentials are still valid."""
        pass
        
    @classmethod
    def get_auth_methods(cls) -> list[str]:
        """Return supported auth methods, e.g. ['oauth'], ['token'], or ['oauth', 'app_password']."""
        return ['oauth']
        
    def handle_callback(self, request_args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Handle OAuth callback to exchange code for token."""
        return {"ok": False, "error": "Not implemented"}
        
    @abc.abstractmethod
    def publish(self, user_id: int, content: Any, preferences: Any = None) -> Dict[str, Any]:
        """Publish content to the provider using stored credentials."""
        pass
