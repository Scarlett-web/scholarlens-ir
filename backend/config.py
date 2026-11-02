"""Environment configuration shared by HTTP and offline import commands."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from elasticsearch import Elasticsearch


@dataclass(frozen=True)
class Settings:
    """Read connection configuration; default to the accepted real-paper alias."""

    url: str = "http://127.0.0.1:9200"
    index: str = "scholarlens-papers-real"
    pdf_root: str | None = None
    pdf_path_base: str | None = None
    runtime_dir: str = str(Path(__file__).resolve().parent / ".runtime")
    vector_index: str = "scholarlens-vectors-real"
    model_dir: str = str(Path(__file__).resolve().parent / ".runtime" / "minilm")
    cors_origins: str = ""
    ai_base_url: str = ""
    ai_model: str = ""
    ai_api_key: str = field(default="", repr=False)
    ai_timeout: float = 30
    ai_max_tokens: int = 800
    grobid_url: str = ""
    uploads_index: str = "scholarlens-uploads-real"
    upload_vector_index: str = "scholarlens-vectors-uploads-real"
    ai_token_parameter: str = "max_completion_tokens"
    ai_protocol: str = "chat_completions"
    pdf_manifest_path: str = ""
    pdf_roots_path: str = ""
    ai_personal: bool = False
    frontend_dir: str = ""

    def __post_init__(self):
        if (
            self.uploads_index != "scholarlens-uploads-real"
            and self.upload_vector_index == "scholarlens-vectors-uploads-real"
        ):
            object.__setattr__(
                self,
                "upload_vector_index",
                "scholarlens-vectors-" + self.uploads_index.removeprefix("scholarlens-"),
            )

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            url=os.getenv("ELASTICSEARCH_URL", cls.url),
            index=os.getenv("ELASTICSEARCH_INDEX", cls.index),
            pdf_root=os.getenv("SCHOLARLENS_PDF_ROOT") or None,
            pdf_path_base=os.getenv("SCHOLARLENS_PDF_PATH_BASE") or None,
            runtime_dir=os.getenv("SCHOLARLENS_RUNTIME_DIR", cls.runtime_dir),
            vector_index=os.getenv("VECTOR_INDEX", cls.vector_index),
            model_dir=os.getenv("EMBEDDING_MODEL_DIR", cls.model_dir),
            cors_origins=os.getenv("CORS_ORIGINS", ""),
            ai_base_url=os.getenv("AI_BASE_URL", ""),
            ai_model=os.getenv("AI_MODEL", ""),
            ai_api_key=os.getenv("AI_API_KEY", ""),
            ai_timeout=float(os.getenv("AI_TIMEOUT_SECONDS", "30")),
            ai_max_tokens=int(os.getenv("AI_MAX_OUTPUT_TOKENS", "800")),
            grobid_url=os.getenv("GROBID_URL", ""),
            uploads_index=os.getenv("UPLOADS_INDEX", cls.uploads_index),
            upload_vector_index=os.getenv("UPLOAD_VECTOR_INDEX", cls.upload_vector_index),
            ai_token_parameter=os.getenv("AI_TOKEN_PARAMETER", cls.ai_token_parameter),
            ai_protocol=os.getenv("AI_PROTOCOL", cls.ai_protocol),
            pdf_manifest_path=os.getenv("SCHOLARLENS_PDF_MANIFEST", ""),
            pdf_roots_path=os.getenv("SCHOLARLENS_PDF_ROOTS_FILE", ""),
            frontend_dir=os.getenv("FRONTEND_DIST", ""),
        )


def make_client(settings: Settings) -> Elasticsearch:
    """Create a client with bounded requests and optional TLS/API-key settings."""
    options = {"request_timeout": 10, "max_retries": 1, "retry_on_timeout": False}
    if os.getenv("ELASTICSEARCH_API_KEY"):
        options["api_key"] = os.environ["ELASTICSEARCH_API_KEY"]
    if os.getenv("ELASTICSEARCH_CA_CERTS"):
        options["ca_certs"] = os.environ["ELASTICSEARCH_CA_CERTS"]
    return Elasticsearch(settings.url, **options)
