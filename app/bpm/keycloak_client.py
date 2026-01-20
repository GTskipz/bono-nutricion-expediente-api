import os
import httpx


class KeycloakClient:
    def __init__(self):
        self.token_url = os.getenv("KEYCLOAK_TOKEN_URL")
        self.client_id = os.getenv("KEYCLOAK_CLIENT_ID")
        self.client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET")
        self.username = os.getenv("KEYCLOAK_USERNAME")
        self.password = os.getenv("KEYCLOAK_PASSWORD")

        verify_ssl = os.getenv("KEYCLOAK_VERIFY_SSL", "true").lower().strip()
        self.verify_ssl = verify_ssl in ("1", "true", "yes", "y")

        missing = [k for k, v in {
            "KEYCLOAK_TOKEN_URL": self.token_url,
            "KEYCLOAK_CLIENT_ID": self.client_id,
            "KEYCLOAK_CLIENT_SECRET": self.client_secret,
            "KEYCLOAK_USERNAME": self.username,
            "KEYCLOAK_PASSWORD": self.password,
        }.items() if not v]

        if missing:
            raise RuntimeError(f"Faltan variables de entorno: {', '.join(missing)}")

    async def get_token_password_grant(self) -> dict:
        data = {
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": self.username,
            "password": self.password,
        }

        async with httpx.AsyncClient(verify=self.verify_ssl, timeout=30) as client:
            resp = await client.post(
                self.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code >= 400:
            # Keycloak suele devolver JSON con error_description
            try:
                detail = resp.json()
            except Exception:
                detail = {"error": resp.text}
            raise httpx.HTTPStatusError(
                f"Keycloak token error {resp.status_code}: {detail}",
                request=resp.request,
                response=resp,
            )

        return resp.json()
