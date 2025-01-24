import os

from ai_assist_builder.utils.jwt_utils import current_utc_time, generate_jwt

token_start_time = current_utc_time()
api_gateway = os.getenv("API_GATEWAY")
sa_email = os.getenv("SA_EMAIL")
jwt_secret_path = os.getenv("JWT_SECRET")

TOKEN_EXPIRY = 3600

# Generate JWT (lasts 1 hour - TODO rotate before expiry)
jwt_token = generate_jwt(
    jwt_secret_path, audience=api_gateway, sa_email=sa_email, expiry_length=TOKEN_EXPIRY
)

print(jwt_token)
