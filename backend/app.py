"""T1 smoke test: prove the Lambda can read and decrypt the GitHub token from SSM.

T2 replaces the body of handler() with the real ingest; get_token() stays.
"""
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)  # Lambda's root logger defaults to WARNING

_ssm = boto3.client("ssm")
_token: str | None = None


def get_token() -> str:
    """Fetch and decrypt the token once per container; warm invocations reuse it."""
    global _token
    if _token is None:
        resp = _ssm.get_parameter(Name=os.environ["TOKEN_PARAM"], WithDecryption=True)
        _token = resp["Parameter"]["Value"]
    return _token


def handler(event, context):
    token = get_token()
    if not token.startswith("github_pat_"):
        # Fail loudly without echoing any part of the value.
        raise ValueError("SSM value is not a fine-grained GitHub token")
    # Log the length only. Never log the token, or any prefix/suffix of it.
    logger.info("token ok (len=%d)", len(token))
    return {"ok": True}
