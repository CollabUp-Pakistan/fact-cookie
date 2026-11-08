"""Initial schema for Fact Cookie."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_from", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True)

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("prefix", sa.String(32), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_prefix", "api_keys", ["prefix"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)

    op.create_table(
        "plans",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("monthly_claim_limit", sa.Integer(), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="usd"),
        sa.Column("features", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", sa.String(40), sa.ForeignKey("plans.id"), nullable=False, server_default="free"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("provider", sa.String(30), nullable=False, server_default="mock"),
        sa.Column("provider_customer_id", sa.String(120), nullable=True),
        sa.Column("provider_subscription_id", sa.String(120), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
    )

    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("verification_id", sa.String(36), nullable=True),
        sa.Column("claim_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(20), nullable=False, server_default="rest"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_usage_events_user_id", "usage_events", ["user_id"])
    op.create_index("ix_usage_events_verification_id", "usage_events", ["verification_id"])
    op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])
    op.create_index("ix_usage_events_period_start", "usage_events", ["period_start"])

    op.create_table(
        "verifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_agent", sa.String(40), nullable=False, server_default="rest"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("mode", sa.String(20), nullable=False, server_default="sync"),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("context_text", sa.Text(), nullable=True),
        sa.Column("orchestration_mode", sa.String(20), nullable=False, server_default="pipeline"),
        sa.Column("llm_mode", sa.String(20), nullable=False, server_default="mock"),
        sa.Column("trace_id", sa.String(80), nullable=True),
        sa.Column("corrected_text", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("claim_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tavily_search_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tavily_extract_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_verifications_user_id", "verifications", ["user_id"])
    op.create_index("ix_verifications_status", "verifications", ["status"])
    op.create_index("ix_verifications_created_at", "verifications", ["created_at"])

    op.create_table(
        "claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("verification_id", sa.String(36), sa.ForeignKey("verifications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(30), nullable=False, server_default="other"),
        sa.Column("verdict", sa.String(30), nullable=False, server_default="unverifiable"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("page_or_section", sa.String(200), nullable=True),
        sa.Column("corrected_text", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_claims_verification_id", "claims", ["verification_id"])
    op.create_index("ix_claims_user_id", "claims", ["user_id"])
    op.create_index("ix_claims_verdict", "claims", ["verdict"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(40), nullable=False, server_default="verification"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("verification_id", sa.String(36), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])

    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("section", sa.String(300), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_user_id", "document_chunks", ["user_id"])
    op.create_index("ix_document_chunks_document_position", "document_chunks", ["document_id", "chunk_index"])

    op.create_table(
        "preferences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trusted_domains", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("blocked_domains", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("strictness", sa.String(20), nullable=False, server_default="standard"),
        sa.Column("recency_days", sa.Integer(), nullable=True),
        sa.Column("citation_style", sa.String(20), nullable=False, server_default="apa"),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_preferences_user_id"),
    )

    op.create_table(
        "cache_entries",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cache_entries_expires_at", "cache_entries", ["expires_at"])

    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(80), primary_key=True),
        sa.Column("client_secret_hash", sa.String(64), nullable=True),
        sa.Column("client_name", sa.String(200), nullable=False, server_default="MCP Client"),
        sa.Column("redirect_uris", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("grant_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("response_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("token_endpoint_auth_method", sa.String(30), nullable=False, server_default="none"),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "oauth_auth_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("client_id", sa.String(80), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("code_challenge", sa.String(200), nullable=True),
        sa.Column("code_challenge_method", sa.String(10), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_oauth_auth_codes_code_hash", "oauth_auth_codes", ["code_hash"], unique=True)
    op.create_index("ix_oauth_auth_codes_client_id", "oauth_auth_codes", ["client_id"])
    op.create_index("ix_oauth_auth_codes_user_id", "oauth_auth_codes", ["user_id"])

    op.create_table(
        "oauth_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column("access_token_hash", sa.String(64), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(80), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_oauth_tokens_jti", "oauth_tokens", ["jti"], unique=True)
    op.create_index("ix_oauth_tokens_access_token_hash", "oauth_tokens", ["access_token_hash"])
    op.create_index("ix_oauth_tokens_refresh_token_hash", "oauth_tokens", ["refresh_token_hash"], unique=True)
    op.create_index("ix_oauth_tokens_user_id", "oauth_tokens", ["user_id"])
    op.create_index("ix_oauth_tokens_client_id", "oauth_tokens", ["client_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column("meta_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_event", "audit_logs", ["event"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False, server_default="stripe"),
        sa.Column("provider_event_id", sa.String(200), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_billing_provider_event"),
    )
    op.create_index("ix_billing_events_provider_event_id", "billing_events", ["provider_event_id"])


def downgrade() -> None:
    op.drop_table("billing_events")
    op.drop_table("audit_logs")
    op.drop_table("oauth_tokens")
    op.drop_table("oauth_auth_codes")
    op.drop_table("oauth_clients")
    op.drop_table("cache_entries")
    op.drop_table("preferences")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("jobs")
    op.drop_table("claims")
    op.drop_table("verifications")
    op.drop_table("usage_events")
    op.drop_table("subscriptions")
    op.drop_table("plans")
    op.drop_table("api_keys")
    op.drop_table("password_reset_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
