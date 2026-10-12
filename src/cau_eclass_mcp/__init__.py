# CAU e-class MCP Server
__version__ = "0.2.0"

from .auth import CauAuthenticator
from .cau_on_client import CAUOnClient
from .utils.credentials import CredentialManager, get_credentials

__all__ = [
    "CauAuthenticator",
    "CAUOnClient",
    "CredentialManager",
    "get_credentials",
    "__version__",
]
