"""
CAU Portal SSO Authentication
Handles login flow: eclass3 -> iam.cau.ac.kr (SAML) -> eclass3
"""

import re
import time
from typing import Optional, Dict
import requests
from bs4 import BeautifulSoup


class CauAuthenticator:
    """Handles CAU Portal SSO authentication"""

    def __init__(self, username: str, password: str):
        """
        Initialize authenticator

        Args:
            username: CAU portal username (student ID)
            password: CAU portal password
        """
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36'
        })
        self.authenticated = False
        self.last_auth_time = 0

    def _clear_password(self):
        """Clear password from memory after successful authentication"""
        self.password = None

    def login(self, debug: bool = False) -> bool:
        """
        Perform SSO login to CAU e-class

        Flow: eclass3.cau.ac.kr/login.do → canvas.cau.ac.kr/xn-sso → back to eclass3

        Args:
            debug: If True, save HTML responses for debugging

        Returns:
            True if successful, False otherwise
        """
        try:
            # Step 1: Get the e-class login page to obtain CSRF cookie
            print("Step 1: Getting e-class login page...")

            login_page_url = "https://eclass3.cau.ac.kr/login.do"
            response = self.session.get(login_page_url, timeout=10)

            if debug:
                import os
                os.makedirs("tests/fixtures/sample_pages", exist_ok=True)
                with open("tests/fixtures/sample_pages/step1_eclass_login.html", 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print(f"  Saved login page HTML (URL: {response.url})")

            # Step 2: Extract CSRF token from cookies
            print("Step 2: Extracting CSRF token...")

            csrf_token = self.session.cookies.get('xn_sso_csrf_token_for_this_login', '')
            if not csrf_token:
                # Try to find it in the HTML or generate it
                print("  Warning: CSRF token not found in cookies, trying to extract from HTML...")
                soup = BeautifulSoup(response.text, 'lxml')
                csrf_input = soup.find('input', {'id': 'login_form1_csrf_token'})
                if csrf_input and csrf_input.get('value'):
                    csrf_token = csrf_input.get('value')
                else:
                    print("  Warning: CSRF token not found, proceeding anyway...")

            print(f"  CSRF token: {csrf_token[:20] if csrf_token else 'None'}...")

            # Step 3: Prepare login form data
            print("Step 3: Preparing login credentials...")

            # The form action from the HTML
            login_action_url = "https://canvas.cau.ac.kr/xn-sso/gw-cb.php"
            params = {
                'from': 'web_redirect',
                'login_type': 'standalone',
                'return_url': 'https://eclass3.cau.ac.kr/learningx/login'
            }

            form_data = {
                'csrf_token': csrf_token,
                'login_user_id': self.username,
                'login_user_password': self.password
            }

            print(f"  Form fields: {list(form_data.keys())}")

            # Step 4: Submit login form
            print("Step 4: Submitting login credentials...")

            response = self.session.post(
                login_action_url,
                params=params,
                data=form_data,
                allow_redirects=True,
                timeout=10
            )

            if debug:
                with open("tests/fixtures/sample_pages/step4_after_login.html", 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print(f"  Saved post-login HTML (URL: {response.url})")

            # Step 5: Verify authentication
            print(f"Step 5: Verifying authentication (final URL: {response.url})...")

            # Check if we're back at e-class
            if 'eclass3.cau.ac.kr' in response.url:
                # Process auto-submit form with RSA decryption
                if 'login_form' in response.text and 'loginCryption' in response.text:
                    print("  Found auto-submit form with RSA decryption...")

                    soup = BeautifulSoup(response.text, 'lxml')

                    # Extract encrypted data and private key from JavaScript
                    import re
                    script_content = response.text

                    # Find: window.loginCryption("encrypted_data", "private_key")
                    match = re.search(r'window\.loginCryption\("([^"]+)",\s*"([^"]+)"\)', script_content)

                    if match:
                        encrypted_data = match.group(1)
                        private_key_raw = match.group(2)

                        # Convert single-line private key to proper PEM format
                        # Remove BEGIN/END tags
                        key_body = private_key_raw.replace('-----BEGIN RSA PRIVATE KEY-----', '')
                        key_body = key_body.replace('-----END RSA PRIVATE KEY-----', '')
                        key_body = key_body.strip()

                        # Add line breaks every 64 characters
                        key_lines = [key_body[i:i+64] for i in range(0, len(key_body), 64)]
                        key_formatted = '\n'.join(key_lines)

                        # Reconstruct PEM format
                        private_key_pem = f"-----BEGIN RSA PRIVATE KEY-----\n{key_formatted}\n-----END RSA PRIVATE KEY-----"

                        print(f"  Found encrypted data (length: {len(encrypted_data)})")
                        print(f"  Found RSA private key (formatted)")

                        # Decrypt using RSA
                        try:
                            from cryptography.hazmat.primitives import serialization, hashes
                            from cryptography.hazmat.primitives.asymmetric import padding
                            from cryptography.hazmat.backends import default_backend
                            import base64

                            # Load private key
                            private_key = serialization.load_pem_private_key(
                                private_key_pem.encode(),
                                password=None,
                                backend=default_backend()
                            )

                            # Decrypt (encrypted_data is base64 encoded)
                            encrypted_bytes = base64.b64decode(encrypted_data)
                            decrypted_bytes = private_key.decrypt(
                                encrypted_bytes,
                                padding.PKCS1v15()
                            )
                            decrypted_password = decrypted_bytes.decode('utf-8')

                            print(f"  Successfully decrypted password (length: {len(decrypted_password)})")

                            # Now POST /login/canvas with decrypted password
                            login_form = soup.find('form', {'id': 'login_form'})
                            if login_form:
                                action = login_form.get('action', '')
                                form_data = {}

                                # Extract all form fields
                                for input_field in login_form.find_all('input'):
                                    name = input_field.get('name')
                                    value = input_field.get('value', '')
                                    if name:
                                        # Override password with decrypted value
                                        if 'password' in name:
                                            form_data[name] = decrypted_password
                                        else:
                                            form_data[name] = value

                                print(f"  Submitting to: {action}")

                                # Add Referer header (required by server)
                                headers = {
                                    'Referer': response.url,  # Current page URL
                                    'Origin': 'https://eclass3.cau.ac.kr',
                                    'Content-Type': 'application/x-www-form-urlencoded',
                                }

                                response = self.session.post(action, data=form_data, headers=headers, allow_redirects=True, timeout=10)

                                print(f"  POST response: {response.status_code}, Final URL: {response.url}")

                                if debug:
                                    with open("tests/fixtures/sample_pages/step6_post_login_canvas.html", 'w', encoding='utf-8') as f:
                                        f.write(response.text)

                        except ImportError:
                            print("  [ERROR] cryptography library not installed")
                            print("  Install with: pip install cryptography")
                            return False
                        except Exception as e:
                            print(f"  [ERROR] RSA decryption failed: {e}")
                            import traceback
                            traceback.print_exc()
                            return False

                # Check for logout link or user-specific content
                if 'logout' in response.text.lower() or '로그아웃' in response.text:
                    print("  Login successful! (found logout link)")
                    self.authenticated = True
                    self.last_auth_time = time.time()
                    return True

                # Check if we're at the main canvas page
                if 'canvas.cau.ac.kr' in response.url and '/' == response.url.split('canvas.cau.ac.kr')[-1]:
                    print("  Login successful! (at canvas home)")
                    self.authenticated = True
                    self.last_auth_time = time.time()
                    return True

                # CRITICAL: Visit root (/) to get the final API-enabled session
                # This is the missing step that activates API permissions!
                print("  Visiting root (/) to finalize session...")
                root_response = self.session.get('https://eclass3.cau.ac.kr/', timeout=10)

                if debug:
                    with open("tests/fixtures/sample_pages/step8_root_visit.html", 'w', encoding='utf-8') as f:
                        f.write(root_response.text)
                    print(f"  Saved root (/) response")

                # Now check dashboard access to verify login
                print("  Checking dashboard access...")
                dashboard_test = self.session.get('https://eclass3.cau.ac.kr/learningx/dashboard', timeout=10)
                if dashboard_test.status_code == 200 and 'login' not in dashboard_test.url.lower():
                    if debug:
                        with open("tests/fixtures/sample_pages/dashboard_test.html", 'w', encoding='utf-8') as f:
                            f.write(dashboard_test.text)
                    print("  Login successful! (can access dashboard)")

                    # Add client-side cookies that JavaScript would normally set
                    # These are required for API access (discovered via Burp Suite analysis)
                    import random
                    import time as time_module

                    # PCID: Persistent Client ID (random number + timestamp)
                    pcid = f"{random.randint(10000000000000000, 99999999999999999)}{int(time_module.time() * 1000)}"
                    self.session.cookies.set('PCID', pcid, domain='.cau.ac.kr')

                    # RC_COLOR: Fixed value (seems to be a constant)
                    self.session.cookies.set('RC_COLOR', '24', domain='.cau.ac.kr')

                    # RC_RESOLUTION: Screen resolution
                    self.session.cookies.set('RC_RESOLUTION', '1920*1080', domain='.cau.ac.kr')

                    # _gid: Google Analytics ID (format: GA1.3.random.timestamp)
                    gid = f"GA1.3.{random.randint(100000000, 999999999)}.{int(time_module.time())}"
                    self.session.cookies.set('_gid', gid, domain='.cau.ac.kr')

                    print("  Added client-side cookies (PCID, RC_COLOR, RC_RESOLUTION, _gid)")

                    # NEW: Critical initialization steps discovered via browser analysis
                    print("  Performing post-login session initialization...")
                    
                    # 1. Visit main learningx page
                    self.session.get('https://eclass3.cau.ac.kr/learningx/main', timeout=10)
                    
                    # 2. Check for xn_api_token
                    xn_api_token = self.session.cookies.get('xn_api_token')
                    if xn_api_token:
                        print("  Found API token (stored in session)")
                    
                    # 3. Visit session activation endpoint if found (common in Canvas)
                    self.session.get('https://eclass3.cau.ac.kr/api/v1/users/self/activity_stream', timeout=10)

                    self.authenticated = True
                    self.last_auth_time = time.time()
                    self._clear_password()
                    return True

            # Check for error messages in response
            if '아이디' in response.text and '비밀번호' in response.text:
                print("  Login failed: Still at login page")
                return False

            if 'login fail' in response.text.lower() or 'invalid' in response.text.lower():
                print("  Login failed: Invalid credentials")
                return False

            # If we're at canvas or other SSO intermediate page, try to follow redirects
            if 'canvas.cau.ac.kr' in response.url:
                print("  At SSO intermediate page, checking for auto-redirect...")
                soup = BeautifulSoup(response.text, 'lxml')

                # Look for auto-submit forms (common in SSO)
                auto_form = soup.find('form')
                if auto_form:
                    action = auto_form.get('action', '')
                    if not action.startswith('http'):
                        base_url = response.url.rsplit('/', 1)[0]
                        action = f"{base_url}/{action.lstrip('/')}"

                    form_data = {}
                    for input_field in auto_form.find_all('input'):
                        name = input_field.get('name')
                        value = input_field.get('value', '')
                        if name:
                            form_data[name] = value

                    print(f"  Submitting auto-form to: {action}")
                    response = self.session.post(action, data=form_data, allow_redirects=True, timeout=10)

                    if 'eclass3.cau.ac.kr' in response.url and 'logout' in response.text.lower():
                        print("  Login successful after auto-redirect!")

                        # Add client-side cookies that JavaScript would normally set
                        # These are required for API access (discovered via Burp Suite analysis)
                        import random
                        import time as time_module

                        # PCID: Persistent Client ID (random number + timestamp)
                        pcid = f"{random.randint(10000000000000000, 99999999999999999)}{int(time_module.time() * 1000)}"
                        self.session.cookies.set('PCID', pcid, domain='.cau.ac.kr')

                        # RC_COLOR: Fixed value (seems to be a constant)
                        self.session.cookies.set('RC_COLOR', '24', domain='.cau.ac.kr')

                        # RC_RESOLUTION: Screen resolution
                        self.session.cookies.set('RC_RESOLUTION', '1920*1080', domain='.cau.ac.kr')

                        # _gid: Google Analytics ID (format: GA1.3.random.timestamp)
                        gid = f"GA1.3.{random.randint(100000000, 999999999)}.{int(time_module.time())}"
                        self.session.cookies.set('_gid', gid, domain='.cau.ac.kr')

                        print("  Added client-side cookies (PCID, RC_COLOR, RC_RESOLUTION, _gid)")

                        # NEW: Critical initialization steps discovered via browser analysis
                        print("  Performing post-login session initialization...")
                        
                        # 1. Visit main learningx page
                        self.session.get('https://eclass3.cau.ac.kr/learningx/main', timeout=10)
                        
                        # 2. Check for xn_api_token
                        xn_api_token = self.session.cookies.get('xn_api_token')
                        if xn_api_token:
                            print(f"  Found API token: {xn_api_token[:20]}...")
                        
                        # 3. Visit session activation endpoint if found (common in Canvas)
                        self.session.get('https://eclass3.cau.ac.kr/api/v1/users/self/activity_stream', timeout=10)

                        self.authenticated = True
                        self.last_auth_time = time.time()
                        self._clear_password()
                        return True

            print(f"  Login failed: Unexpected final URL: {response.url}")
            if debug:
                print(f"  Final URL: {response.url}")
                print(f"  Response status: {response.status_code}")

            return False

        except requests.RequestException as e:
            print(f"Network error during login: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error during login: {e}")
            return False

    def ensure_authenticated(self, max_age_seconds: int = 1800) -> bool:
        """
        Ensure session is authenticated, re-login if needed

        Args:
            max_age_seconds: Maximum session age before re-auth (default: 30 min)

        Returns:
            True if authenticated, False otherwise
        """
        if not self.authenticated:
            return self.login()

        # Check if session is too old
        age = time.time() - self.last_auth_time
        if age > max_age_seconds:
            print(f"Session expired (age: {age:.0f}s), re-authenticating...")
            self.authenticated = False
            return self.login()

        return True

    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """
        Make authenticated GET request

        Args:
            url: URL to request
            **kwargs: Additional arguments for requests.get()

        Returns:
            Response object or None if authentication failed
        """
        if not self.ensure_authenticated():
            print("  Authentication check failed in get()")
            return None

        try:
            response = self.session.get(url, timeout=10, **kwargs)
            print(f"  GET {url} → {response.status_code}")
            return response
        except requests.RequestException as e:
            print(f"  Request error: {e}")
            return None
        except Exception as e:
            print(f"  Unexpected error in get(): {e}")
            return None

    def get_text(self, url: str, **kwargs) -> Optional[str]:
        """
        Get page content as text

        Args:
            url: URL to request
            **kwargs: Additional arguments for requests.get()

        Returns:
            Page HTML or None if failed
        """
        response = self.get(url, **kwargs)
        if response and response.status_code == 200:
            return response.text
        return None


# Global authenticator instance (initialized on first use)
_global_auth: Optional[CauAuthenticator] = None


def get_authenticator(username: str = None, password: str = None) -> CauAuthenticator:
    """
    Get or create global authenticator instance

    Args:
        username: CAU username (required on first call)
        password: CAU password (required on first call)

    Returns:
        CauAuthenticator instance
    """
    global _global_auth

    if _global_auth is None:
        if not username or not password:
            raise ValueError("Username and password required for first authentication")
        _global_auth = CauAuthenticator(username, password)

    return _global_auth


def reset_authenticator() -> None:
    """Reset global authenticator (for testing or credential changes)"""
    global _global_auth
    _global_auth = None
