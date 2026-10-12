"""Password hashing for government officials (bcrypt)."""

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


MIN_LENGTH = 10


def check_new_password(new: str, email: str, current: str | None = None) -> str | None:
    """None if the password is acceptable, otherwise the reason (shown to the official)."""
    if len(new) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters."
    if current is not None and new == current:
        return "Choose a password different from the current one."
    if new.lower() in {email.lower(), email.split("@")[0].lower()}:
        return "Don't use your email address as the password."
    return None
