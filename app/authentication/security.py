import base64
import binascii
import hashlib
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SALT_BYTES = 16
TOKEN_BYTES = 32


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    """Hash a password using scrypt and a unique random salt."""

    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_encode(salt)}${_encode(digest)}"


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify a password without exposing timing-sensitive comparisons."""

    try:
        algorithm, n, r, p, salt, expected = encoded_hash.split("$", maxsplit=5)
        if algorithm != "scrypt":
            return False
        decoded_expected = _decode(expected)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(decoded_expected),
        )
    except (AttributeError, binascii.Error, TypeError, ValueError):
        return False

    return secrets.compare_digest(digest, decoded_expected)


def generate_opaque_token() -> str:
    """Generate a high-entropy bearer credential with no embedded claims."""

    return secrets.token_urlsafe(TOKEN_BYTES)


def digest_token(token: str) -> str:
    """Create the non-reversible lookup value stored for a session token."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()
