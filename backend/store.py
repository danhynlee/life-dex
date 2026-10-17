"""DynamoDB access. Single table, pk/sk:
  pk="COMMIT", sk=<sha>          one item per commit (dedup by SHA)
  pk="META",   sk="ingest"       last_run cursor
T6/T7 will add pk="MISSION"/"UNLOCK" partitions to the same table.
"""
from __future__ import annotations

from botocore.exceptions import ClientError

COMMIT_PK = "COMMIT"
META_KEY = {"pk": "META", "sk": "ingest"}


class CommitStore:
    def __init__(self, table):  # boto3.resource("dynamodb").Table(...)
        self._t = table

    def put_commit(self, item: dict) -> bool:
        """Insert if new. Returns True if added, False if the SHA already existed."""
        try:
            self._t.put_item(
                Item={"pk": COMMIT_PK, "sk": item["sha"], **item},
                ConditionExpression="attribute_not_exists(pk)",
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def get_cursor(self) -> str | None:
        r = self._t.get_item(Key=META_KEY, ConsistentRead=True)
        return r.get("Item", {}).get("last_run")

    def set_cursor(self, ts: str) -> None:
        self._t.put_item(Item={**META_KEY, "last_run": ts})
