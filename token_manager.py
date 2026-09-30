import os, requests
from dotenv import load_dotenv, set_key
from analytics import emit_event

HTTP_TIMEOUT_SECONDS = 20
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(ENV_FILE)

def get_valid_token() -> str:
    """Returns a valid access token, refreshing if needed."""
    access_token = os.getenv("OURA_ACCESS_TOKEN")
    refresh_token = os.getenv("OURA_REFRESH_TOKEN")

    if not access_token or not refresh_token:
        raise EnvironmentError("OURA_ACCESS_TOKEN and OURA_REFRESH_TOKEN are not set. Run auth.py first.")

    session_id = "sync-auth-token"
    emit_event("sync_started", session_id, {"sync_scope": "auth_token"})

    try:
        # Quick validity check
        r = requests.get(
            "https://api.ouraring.com/v2/usercollection/personal_info",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if r.status_code == 200:
            emit_event(
                "sync_completed",
                session_id,
                {
                    "sync_scope": "auth_token",
                    "status": "success",
                    "path": "valid_access_token",
                    "http_status": 200,
                },
            )
            return access_token
        if r.status_code != 401:
            r.raise_for_status()  # surface 429, 500, etc. — don't treat as expired

        # Refresh
        print("Access token expired — refreshing...")
        resp = requests.post(
            "https://api.ouraring.com/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": os.getenv("OURA_CLIENT_ID"),
                "client_secret": os.getenv("OURA_CLIENT_SECRET"),
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        tokens = resp.json()

        if "access_token" not in tokens or "refresh_token" not in tokens:
            raise ValueError(f"Unexpected response from token endpoint: {tokens}")

        set_key(ENV_FILE, "OURA_ACCESS_TOKEN", tokens["access_token"])
        set_key(ENV_FILE, "OURA_REFRESH_TOKEN", tokens["refresh_token"])
        print("Tokens refreshed")
        emit_event(
            "sync_completed",
            session_id,
            {
                "sync_scope": "auth_token",
                "status": "success",
                "path": "refresh",
                "http_status": resp.status_code,
            },
        )
        return tokens["access_token"]
    except Exception as exc:
        emit_event(
            "sync_completed",
            session_id,
            {
                "sync_scope": "auth_token",
                "status": "error",
                "error_type": type(exc).__name__,
            },
        )
        raise