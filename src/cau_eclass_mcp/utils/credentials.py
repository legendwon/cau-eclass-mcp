"""
Cross-platform credential management using OS keyring.
Falls back to environment variables if keyring is unavailable.
"""

import os
from typing import Dict, Optional

try:
    import keyring
    from keyring.errors import KeyringError
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False
    KeyringError = Exception  # Dummy for type hints


class CredentialManager:
    """Manages credentials using OS keyring with environment variable fallback"""

    SERVICE_NAME = "cau-eclass-mcp"

    def __init__(self):
        """Initialize credential manager"""
        pass

    def save_credentials(self, username: str, password: str) -> bool:
        """
        Save credentials to OS keyring

        Args:
            username: CAU student ID
            password: CAU portal password

        Returns:
            True if saved successfully, False otherwise
        """
        if not HAS_KEYRING:
            print("Warning: keyring not available. Use environment variables instead:")
            print(f"  export CAU_USERNAME={username}")
            print("  export CAU_PASSWORD=your_password")
            return False

        try:
            keyring.set_password(self.SERVICE_NAME, "username", username)
            keyring.set_password(self.SERVICE_NAME, username, password)
            print(f"Credentials saved to system keyring for user: {username}")
            return True
        except KeyringError as e:
            print(f"Failed to save to keyring: {e}")
            print("\nAlternative: Use environment variables:")
            print(f"  export CAU_USERNAME={username}")
            print("  export CAU_PASSWORD=your_password")
            return False

    def load_credentials(self) -> Optional[Dict[str, str]]:
        """
        Load credentials from keyring → environment variables → prompt

        Returns:
            dict with 'username' and 'password' keys, or None if not available
        """
        # Try keyring first
        if HAS_KEYRING:
            try:
                username = keyring.get_password(self.SERVICE_NAME, "username")
                if username:
                    password = keyring.get_password(self.SERVICE_NAME, username)
                    if password:
                        return {"username": username, "password": password}
            except KeyringError:
                pass

        # Fallback to environment variables
        username = os.environ.get("CAU_USERNAME")
        password = os.environ.get("CAU_PASSWORD")
        if username and password:
            return {"username": username, "password": password}

        # No credentials found
        return None

    def prompt_for_credentials(self) -> Dict[str, str]:
        """
        Prompt user for credentials interactively

        Returns:
            dict with 'username' and 'password' keys
        """
        import getpass

        print("\n" + "="*60)
        print("CAU e-class MCP - Credential Setup")
        print("="*60)
        print("\nNo credentials found. Please enter your CAU portal credentials.")
        print("(These will be used to access e-class via SSO)\n")

        username = input("CAU Student ID: ").strip()
        password = getpass.getpass("CAU Password: ")

        # Offer to save to keyring
        if HAS_KEYRING:
            save_choice = input("\nSave credentials to system keyring? (y/n): ").lower().strip()
            if save_choice == 'y':
                self.save_credentials(username, password)
            else:
                print("\nTo avoid this prompt in the future, set environment variables:")
                print(f"  export CAU_USERNAME={username}")
                print("  export CAU_PASSWORD=your_password")
        else:
            print("\nKeyring not available. To avoid this prompt, set environment variables:")
            print(f"  export CAU_USERNAME={username}")
            print("  export CAU_PASSWORD=your_password")

        return {"username": username, "password": password}

    def get_credentials(self) -> Dict[str, str]:
        """
        Get credentials (load from keyring/env or prompt if not found)

        Returns:
            dict with 'username' and 'password' keys
        """
        creds = self.load_credentials()

        if not creds:
            creds = self.prompt_for_credentials()

        return creds

    def check_credentials_exist(self) -> bool:
        """
        Check if credentials are configured (keyring or environment variables)

        Returns:
            True if credentials exist, False otherwise
        """
        # Try keyring first
        if HAS_KEYRING:
            try:
                username = keyring.get_password(self.SERVICE_NAME, "username")
                if username:
                    password = keyring.get_password(self.SERVICE_NAME, username)
                    if password:
                        return True
            except KeyringError:
                pass

        # Check environment variables
        username = os.environ.get("CAU_USERNAME")
        password = os.environ.get("CAU_PASSWORD")
        if username and password:
            return True

        return False

    def delete_credentials(self) -> bool:
        """
        Delete stored credentials from keyring

        Returns:
            True if deleted successfully, False otherwise
        """
        if not HAS_KEYRING:
            print("Keyring not available. Nothing to delete.")
            return False

        try:
            username = keyring.get_password(self.SERVICE_NAME, "username")
            if username:
                keyring.delete_password(self.SERVICE_NAME, username)
                keyring.delete_password(self.SERVICE_NAME, "username")
                print(f"Credentials deleted from keyring for user: {username}")
                return True
            else:
                print("No credentials found in keyring.")
                return False
        except KeyringError as e:
            print(f"Failed to delete credentials: {e}")
            return False


# Convenience function for easy import
def get_credentials() -> Dict[str, str]:
    """
    Get CAU portal credentials (load or prompt)

    Returns:
        dict with 'username' and 'password' keys
    """
    manager = CredentialManager()
    return manager.get_credentials()


# Migration helper for users with old DPAPI credentials
def migrate_from_dpapi(old_credentials_path: Optional[str] = None) -> bool:
    """
    Migrate credentials from old Windows DPAPI format to keyring

    Args:
        old_credentials_path: Path to old .credentials.json file
                             Defaults to ~/.claude/.credentials.json

    Returns:
        True if migration successful, False otherwise
    """
    from pathlib import Path
    import json
    import base64

    if old_credentials_path:
        cred_path = Path(old_credentials_path)
    else:
        cred_path = Path.home() / ".claude" / ".credentials.json"

    if not cred_path.exists():
        print(f"No old credentials file found at {cred_path}")
        return False

    try:
        # Try importing Windows DPAPI
        import win32crypt
        HAS_DPAPI = True
    except ImportError:
        print("Cannot migrate: win32crypt not available on this system")
        return False

    try:
        with open(cred_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if 'cau_portal' not in data:
            print("No CAU portal credentials found in old format")
            return False

        cau_data = data['cau_portal']

        # Decrypt old credentials
        def decrypt_dpapi(encrypted: str) -> str:
            encrypted_bytes = base64.b64decode(encrypted.encode())
            _, plaintext_bytes = win32crypt.CryptUnprotectData(
                encrypted_bytes, None, None, None, 0
            )
            return plaintext_bytes.decode()

        username = decrypt_dpapi(cau_data['username'])
        password = decrypt_dpapi(cau_data['password'])

        # Save to new keyring format
        manager = CredentialManager()
        if manager.save_credentials(username, password):
            print(f"\nMigration successful!")
            print(f"Old credentials file: {cred_path}")
            print("You can safely delete the old file after verifying login works.")
            return True
        else:
            return False

    except Exception as e:
        print(f"Migration failed: {e}")
        return False
