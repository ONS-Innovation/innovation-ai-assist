# Generate a JWT token for the example API
import time
from datetime import datetime, timezone
from google.auth.crypt import RSASigner
from google.auth.jwt import encode
import google.auth


TOKEN_EXPIRY = 3600  # 1 hour
REFRESH_THRESHOLD = 300  # 5 minutes


def current_utc_time():
    """Get the current UTC time."""
    return datetime.fromtimestamp(time.time(), tz=timezone.utc)


def generate_jwt(sa_keyfile, 
                 sa_email="account@project.iam.gserviceaccount.com",
                 audience="service-name",
                 expiry_length=3600):

    now = int(time.time())

    payload = {
        "iat": now,
        "exp": now + expiry_length,
        "iss": sa_email,
        "aud": audience,
        "sub": sa_email,
        "email": sa_email
    }

    signer = google.auth.crypt.RSASigner.from_service_account_file(sa_keyfile)
    jwt = google.auth.jwt.encode(signer, payload)

    # The actual token is between b'my_jwt_token' so strip the b' and '
    return jwt.decode("utf-8")


def check_and_refresh_token(token_start_time,
                            current_token,
                            jwt_secret_path,
                            api_gateway,
                            sa_email):
    """Check if the token needs refreshing and refresh if necessary."""
    if not token_start_time:
        # If no token exists, create one
        token_start_time = current_utc_time()
        current_token = generate_jwt(jwt_secret_path,
                                     audience=api_gateway,
                                     sa_email=sa_email,
                                     expiry_length=TOKEN_EXPIRY)

    elapsed_time = (current_utc_time() - token_start_time).total_seconds()
    remaining_time = TOKEN_EXPIRY - elapsed_time

    if remaining_time <= REFRESH_THRESHOLD:
        # Refresh the token
        print("Refreshing JWT token...")
        token_start_time = current_utc_time()
        current_token = generate_jwt(jwt_secret_path,
                                     audience=api_gateway,
                                     sa_email=sa_email,
                                     expiry_length=TOKEN_EXPIRY)
        print(f"JWT Token ends with {current_token[-5:]} created at {token_start_time}")

    return token_start_time, current_token
