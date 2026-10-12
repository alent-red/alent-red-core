import base64
import os
import socket


def find_free_port() -> int:
    """Find an unused TCP port on localhost.

    Returns:
        Port number suitable for binding a server to.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
        tcp_socket.bind(("127.0.0.1", 0))
        port: int = tcp_socket.getsockname()[1]
        return port


def generate_encryption_key() -> str:
    """Generate a random base64-encoded AES-256 key.

    Returns:
        Base64-encoded 32-byte key.
    """
    return base64.b64encode(os.urandom(32)).decode()
