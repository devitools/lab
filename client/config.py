"""Constantes do servidor floofy-sun."""

SERVER_HOST = "floofy.lab.devi.tools"
PUBLISH_URL = f"https://{SERVER_HOST}/publish/"
TUNNEL_URL = f"wss://{SERVER_HOST}/tunnel/"

UPLOAD_TIMEOUT_S = 120
TUNNEL_LOCAL_TIMEOUT_S = 30
RECONNECT_BACKOFF_S = (1, 2, 4, 8, 16, 30)
MAX_UPLOAD_MB = 50
