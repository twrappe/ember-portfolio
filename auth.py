import os, hashlib, secrets, base64, urllib.parse, webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from dotenv import load_dotenv, set_key

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(ENV_FILE)

CLIENT_ID = os.getenv("OURA_CLIENT_ID")
CLIENT_SECRET = os.getenv("OURA_CLIENT_SECRET")
REDIRECT_URI = os.getenv("OURA_REDIRECT_URI")
HTTP_TIMEOUT_SECONDS = 20

missing = [k for k, v in {"OURA_CLIENT_ID": CLIENT_ID, "OURA_CLIENT_SECRET": CLIENT_SECRET, "OURA_REDIRECT_URI": REDIRECT_URI}.items() if not v]
if missing:
    raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

def generate_pkce_pair():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b'=').decode('utf-8')
    return verifier, challenge

auth_code = None # Global variable to store the authorization code

expected_state = None

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code, expected_state
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        returned_state = params.get("state", [None])[0]
        if returned_state != expected_state:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>EMBER: state mismatch. Authorization rejected.</h2>")
            return
        auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>EMBER: authorization complete. You can close this tab.</h2>")

    def log_message(self, format, *args):
        pass  # silence server logs

def get_tokens():
    global auth_code, expected_state
    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(16)
    expected_state = state

    # Build and open auth URL
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "daily heartrate personal session spo2 workout",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    auth_url = "https://cloud.ouraring.com/oauth/authorize?" + urllib.parse.urlencode(params)
    print(f"Opening browser for Oura authorization...")
    webbrowser.open(auth_url)

    # Listen for callback
    server = HTTPServer(("localhost", 8080), CallbackHandler)
    server.handle_request()

    if not auth_code:
        raise RuntimeError("No auth code received.")

    # Exchange code for tokens
    resp = requests.post(
        "https://api.ouraring.com/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code_verifier": code_verifier,
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    tokens = resp.json()

    # Persist to .env
    set_key(ENV_FILE, "OURA_ACCESS_TOKEN", tokens["access_token"])
    set_key(ENV_FILE, "OURA_REFRESH_TOKEN", tokens["refresh_token"])
    print("✓ Tokens saved to .env")
    return tokens

if __name__ == "__main__":
    get_tokens()