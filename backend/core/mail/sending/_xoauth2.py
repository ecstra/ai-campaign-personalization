import base64

def build_xoauth2_smtp(user_email: str, access_token: str) -> str:
    auth_string = f"user={user_email}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(auth_string.encode()).decode()

def build_xoauth2_imap(user_email: str, access_token: str) -> bytes:
    auth_string = f"user={user_email}\x01auth=Bearer {access_token}\x01\x01"
    return auth_string.encode()