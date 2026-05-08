"""
Minimal tenant resolver for authentication.
"""
from typing import Optional
import logging

from jose import jwt, JWTError

from ..config import settings

logger = logging.getLogger(__name__)


class TenantResolver:
    """Minimal tenant resolver that extracts tenant_id from JWT claims."""

    @staticmethod
    def resolve_tenant_from_token(token_payload: dict) -> Optional[str]:
        """
        Extract tenant_id from JWT token payload.

        Args:
            token_payload: Decoded JWT payload

        Returns:
            Tenant ID if found, None otherwise
        """
        # Try user_metadata first (most common location)
        if 'user_metadata' in token_payload:
            tenant_id = token_payload['user_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        # Try app_metadata as fallback
        if 'app_metadata' in token_payload:
            tenant_id = token_payload['app_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        # Try root level
        tenant_id = token_payload.get('tenant_id')
        if tenant_id:
            return tenant_id

        logger.warning("No tenant_id found in token payload")
        return None

    @staticmethod
    def resolve_tenant_from_user(user_data: dict) -> Optional[str]:
        """
        Extract tenant_id from user data.

        Args:
            user_data: User data dictionary

        Returns:
            Tenant ID if found, None otherwise
        """
        # Check various possible locations
        if 'tenant_id' in user_data:
            return user_data['tenant_id']

        if 'user_metadata' in user_data:
            tenant_id = user_data['user_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        if 'app_metadata' in user_data:
            tenant_id = user_data['app_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        return None

    @staticmethod
    async def resolve_tenant_id(user_id: str, user_email: str, token: Optional[str] = None) -> Optional[str]:
        """
        Resolve tenant ID for a user.

        Resolution order:
            1. Decode the JWT (if provided) and look for tenant_id claims.
            2. Query the ``user_tenants`` table for an active assignment.

        Returns the resolved tenant id, or ``None`` if no tenant could be
        determined for the user. Callers MUST treat ``None`` as a missing
        assignment and refuse access — never fall back to a default tenant,
        as that would break tenant isolation.
        """
        # 1) Try to extract tenant_id directly from the JWT claims
        if token:
            try:
                # We don't need to verify the signature here; auth has already
                # validated the token. We just want the claims.
                payload = jwt.decode(
                    token,
                    settings.secret_key,
                    algorithms=["HS256"],
                    options={"verify_signature": False, "verify_aud": False},
                )
                tenant_from_token = TenantResolver.resolve_tenant_from_token(payload)
                if tenant_from_token:
                    return tenant_from_token
            except JWTError as exc:
                logger.debug(f"resolve_tenant_id: could not decode token claims: {exc}")
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(f"resolve_tenant_id: unexpected error decoding token: {exc}")

        # 2) Fall back to the user_tenants table
        try:
            # Imported lazily to avoid circular imports at module load time.
            from ..database import supabase

            result = (
                supabase.service.table("user_tenants")
                .select("tenant_id, role")
                .eq("user_id", user_id)
                .eq("is_active", True)
                .execute()
            )
            rows = result.data or []
            if rows:
                # Prefer admin/owner assignment if multiple exist
                for row in rows:
                    if row.get("role") in ("admin", "owner") and row.get("tenant_id"):
                        return row["tenant_id"]
                # Otherwise return the first non-empty tenant_id
                for row in rows:
                    if row.get("tenant_id"):
                        return row["tenant_id"]
        except Exception as exc:
            logger.error(
                f"resolve_tenant_id: DB lookup failed for user {user_id} ({user_email}): {exc}"
            )

        logger.warning(
            f"resolve_tenant_id: no tenant assignment found for user {user_id} ({user_email})"
        )
        return None

    @staticmethod
    async def update_user_tenant_metadata(user_id: str, tenant_id: str) -> None:
        """
        Update user metadata with tenant_id.
        
        Args:
            user_id: User ID
            tenant_id: Tenant ID
        """
        # No-op in this resolver implementation.
        pass
