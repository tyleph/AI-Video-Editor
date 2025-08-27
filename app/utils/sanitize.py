import re

def sanitize_firebase_key(key: str) -> str:
    """
    Sanitizes a string to be used as a Firebase Realtime Database key.
    Replaces ['.', '#', '$', '[', ']', '/'] with '_'.
    """
    return re.sub(r'[.#$\[\]/]', '_', key)
