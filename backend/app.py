"""Ingest Lambda: read the GitHub token from SSM, pull new commits, store them in DynamoDB."""
import json
import logging
import os
from datetime import UTC, datetime

import boto3
from github_client import GitHubClient
from ingest import run
from store import CommitStore

logger = logging.getLogger()
logger.setLevel(logging.INFO)  # Lambda's root logger defaults to WARNING

# Module scope: created once per container, reused across warm invocations.
_ssm = boto3.client("ssm")
_table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
_token: str | None = None


def get_token() -> str:
    """Fetch and decrypt the token once per container; warm invocations reuse it."""
    global _token
    if _token is None:
        resp = _ssm.get_parameter(Name=os.environ["TOKEN_PARAM"], WithDecryption=True)
        _token = resp["Parameter"]["Value"]
    return _token


def handler(event, context):
    gh = GitHubClient(get_token())
    result = run(gh, CommitStore(_table), datetime.now(UTC))
    logger.info(json.dumps({"msg": "ingest ok", **result, "github_calls": gh.calls}))
    return result
