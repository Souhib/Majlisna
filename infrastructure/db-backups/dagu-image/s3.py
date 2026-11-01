"""Object-store helper for the Majlisna DB backup (boto3, no shell interpolation).

Two targets, both configured by environment only:
- ``primary``: the SeaweedFS S3 on the VPS (``S3_ENDPOINT``, ``S3_BUCKET``,
  ``S3_ACCESS_KEY``, ``S3_SECRET_KEY``), path-style addressing;
- ``offsite``: an optional second S3 (AWS S3 or any S3-compatible store) through the
  ``OFFSITE_S3_*`` variables; an empty ``OFFSITE_S3_ENDPOINT`` means AWS itself.

Keys are full object keys; a PREFIX argument matches the keys starting with ``PREFIX-``
(``majlisna`` matches ``majlisna-20261031T034500Z.dump.gpg``, never ``drill-majlisna-…``).

    s3.py [--target primary|offsite] put PATH KEY
    s3.py [--target …] verify KEY SIZE        # the object exists with exactly SIZE bytes
    s3.py [--target …] rotate PREFIX KEEP     # keep the newest KEEP objects, print the count
    s3.py [--target …] list PREFIX            # "key<TAB>size", oldest first
    s3.py [--target …] latest PREFIX          # newest key
    s3.py [--target …] count PREFIX
    s3.py [--target …] get KEY DEST           # DEST "-" writes to stdout
    s3.py [--target …] ensure-bucket
    s3.py delete-drill KEY                    # primary only, and only a "drill-" key

Errors print a credential-free one-line diagnostic and exit 1.
"""

import argparse
import os
import sys

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

DRILL_PREFIX = "drill-"
DEFAULT_REGION = "us-east-1"


def setting(name: str, default: str = "") -> str:
    """Read an env var; an unresolved Dagu reference (``${NAME}``) counts as unset."""
    value = os.environ.get(name, "")
    if not value or value.startswith("${"):
        return default
    return value


def required(name: str) -> str:
    value = setting(name)
    if not value:
        raise SystemExit(f"s3: {name} is not set")
    return value


class Target:
    def __init__(self, name: str) -> None:
        self.name = name
        if name == "primary":
            endpoint = required("S3_ENDPOINT")
            self.bucket = required("S3_BUCKET")
            access, secret = required("S3_ACCESS_KEY"), required("S3_SECRET_KEY")
            region = setting("S3_REGION", DEFAULT_REGION)
            addressing = "path"
            self.storage_class = ""
        else:
            endpoint = setting("OFFSITE_S3_ENDPOINT") or None
            self.bucket = required("OFFSITE_S3_BUCKET")
            access, secret = required("OFFSITE_S3_ACCESS_KEY"), required("OFFSITE_S3_SECRET_KEY")
            region = setting("OFFSITE_S3_REGION", DEFAULT_REGION)
            addressing = setting("OFFSITE_S3_ADDRESSING", "auto")
            self.storage_class = setting("OFFSITE_S3_STORAGE_CLASS")
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access,
            aws_secret_access_key=secret,
            region_name=region,
            config=Config(
                s3={"addressing_style": addressing},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=10,
                read_timeout=120,
            ),
        )

    def keys(self, prefix: str) -> list[tuple[str, int]]:
        """Objects whose key starts with ``prefix-``, oldest first (keys embed a UTC stamp)."""
        found = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=f"{prefix}-"):
            found.extend((obj["Key"], obj["Size"]) for obj in page.get("Contents", []))
        return sorted(found)


def run(args: argparse.Namespace) -> int:
    target = Target(args.target)
    command = args.command
    if command == "put":
        extra = {"StorageClass": target.storage_class} if target.storage_class else None
        target.client.upload_file(args.args[0], target.bucket, args.args[1], ExtraArgs=extra)
        return 0
    if command == "verify":
        key, size = args.args[0], int(args.args[1])
        head = target.client.head_object(Bucket=target.bucket, Key=key)
        if head["ContentLength"] != size:
            print(f"s3 {target.name}: {key} has {head['ContentLength']} bytes, expected {size}", file=sys.stderr)  # noqa: T201
            return 1
        return 0
    if command == "rotate":
        prefix, keep = args.args[0], int(args.args[1])
        if keep < 1:
            print("s3: refusing to rotate with KEEP < 1", file=sys.stderr)  # noqa: T201
            return 1
        keys = [key for key, _ in target.keys(prefix)]
        for key in keys[:-keep]:
            target.client.delete_object(Bucket=target.bucket, Key=key)
        print(min(len(keys), keep))  # noqa: T201
        return 0
    if command == "list":
        for key, size in target.keys(args.args[0]):
            print(f"{key}\t{size}")  # noqa: T201
        return 0
    if command == "latest":
        keys = target.keys(args.args[0])
        if not keys:
            print(f"s3 {target.name}: no object starts with {args.args[0]}-", file=sys.stderr)  # noqa: T201
            return 1
        print(keys[-1][0])  # noqa: T201
        return 0
    if command == "count":
        print(len(target.keys(args.args[0])))  # noqa: T201
        return 0
    if command == "get":
        key, dest = args.args
        if dest == "-":
            target.client.download_fileobj(target.bucket, key, sys.stdout.buffer)
            sys.stdout.buffer.flush()
        else:
            target.client.download_file(target.bucket, key, dest)
        return 0
    if command == "ensure-bucket":
        try:
            target.client.head_bucket(Bucket=target.bucket)
        except ClientError:
            region = target.client.meta.region_name
            config = {} if region == DEFAULT_REGION else {"CreateBucketConfiguration": {"LocationConstraint": region}}
            try:
                target.client.create_bucket(Bucket=target.bucket, **config)
            except ClientError as exc:
                # Created meanwhile (a concurrent run, or a store that creates on first put).
                if exc.response.get("Error", {}).get("Code") != "BucketAlreadyOwnedByYou":
                    raise
        target.client.head_bucket(Bucket=target.bucket)
        return 0
    if command == "delete-drill":
        key = args.args[0]
        if target.name != "primary" or not key.startswith(DRILL_PREFIX) or "/" in key:
            print(f"s3: delete-drill only removes a primary '{DRILL_PREFIX}' object", file=sys.stderr)  # noqa: T201
            return 1
        target.client.delete_object(Bucket=target.bucket, Key=key)
        return 0
    print(f"s3: unknown command {command}", file=sys.stderr)  # noqa: T201
    return 2


ARITY = {
    "put": 2, "verify": 2, "rotate": 2, "list": 1, "latest": 1, "count": 1,
    "get": 2, "ensure-bucket": 0, "delete-drill": 1,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Majlisna backup object-store helper")
    parser.add_argument("--target", choices=("primary", "offsite"), default="primary")
    parser.add_argument("command", choices=sorted(ARITY))
    parser.add_argument("args", nargs="*")
    args = parser.parse_args()
    if len(args.args) != ARITY[args.command]:
        parser.error(f"{args.command} takes {ARITY[args.command]} argument(s)")
    try:
        return run(args)
    except ClientError as exc:
        error = exc.response.get("Error", {})
        print(f"s3 {args.target} {args.command} failed: {error.get('Code', 'error')}", file=sys.stderr)  # noqa: T201
    except (BotoCoreError, OSError) as exc:
        print(f"s3 {args.target} {args.command} failed: {type(exc).__name__}", file=sys.stderr)  # noqa: T201
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
