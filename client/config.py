"""Constantes do servidor lab."""

SERVER_HOST = "lab.devi.tools"
TUNNEL_URL = f"wss://{SERVER_HOST}/tunnel/"

TUNNEL_LOCAL_TIMEOUT_S = 30
RECONNECT_BACKOFF_S = (1, 2, 4, 8, 16, 30)
