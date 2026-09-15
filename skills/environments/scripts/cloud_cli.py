#!/usr/bin/env python3
"""Run AWS or Alibaba Cloud CLI with this skill's SOPS credentials."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def field(record, name, optional=False):
    value = record.get(name)
    if optional and value is None:
        return None
    if (not isinstance(value, str) or not value.strip()
            or any(c in value for c in "\r\n\0")):
        raise ValueError("Invalid credential field")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", help="Target region; required when no region is saved")
    parser.add_argument("--account", choices=("prod", "humble-little-c1"),
                        help="Required for Alibaba Cloud; select the stored account")
    parser.add_argument("provider", choices=("aws", "aliyun"))
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="CLI service, operation, and arguments")
    args = parser.parse_args()
    if len(args.command) < 2 or any(x.startswith("-") for x in args.command[:2]):
        parser.error("Provide a service and operation after the provider")
    # These commands/options can expose or replace the selected credentials.
    blocked = {"--profile", "--debug", "--access-key-id", "--access-key-secret",
               "--sts-token", "--mode", "--no-sign-request", "--region", "--account"}
    if (args.command[0] in {"configure", "login", "logout"}
            or any(x.split("=", 1)[0] in blocked for x in args.command)):
        parser.error("Use --region/--account before the provider; no profile, credential, or debug overrides")
    if args.provider == "aliyun" and not args.account:
        parser.error("Alibaba Cloud requires --account before aliyun: prod or humble-little-c1")
    if args.provider == "aws" and args.account:
        parser.error("--account is only supported for Alibaba Cloud")
    if args.provider == "aws" and not args.region:
        parser.error("AWS has no saved region; provide --region before aws")
    if not shutil.which("sops") or not shutil.which(args.provider):
        parser.error("sops and the selected cloud CLI must be on PATH")

    secret_file = Path(__file__).resolve().parents[1] / "references/secrets.enc.yaml"
    credential_path = (["aliyun", "accounts", args.account]
                       if args.provider == "aliyun" else ["aws"])
    extract_path = "".join(f"[{json.dumps(key)}]" for key in credential_path)
    try:
        result = subprocess.run(
            ["sops", "decrypt", "--extract", extract_path,
             "--output-type", "json", str(secret_file)],
            capture_output=True, check=True, timeout=30,
        )
        record = json.loads(result.stdout)
        access_key = field(record, "access_key_id")
        secret_key = field(record, "secret_access_key" if args.provider == "aws"
                           else "access_key_secret")
        region = args.region or field(record, "region", optional=True)
        if args.provider == "aliyun" and record.get("mode") != "AK":
            raise ValueError("Only the stored AK mode is supported")
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError, TypeError):
        sys.exit("Cloud credential unavailable; check SOPS, the matching private key, and required fields")
    if not region:
        parser.error("Selected account has no saved region; provide --region before the provider")

    # Do not mix the selected key with a host's profile, token, or endpoint.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AWS_", "ALIBABA_CLOUD_", "ALICLOUD_", "ALIYUN_"))}
    if args.provider == "aws":
        env.update({
            "AWS_ACCESS_KEY_ID": access_key,
            "AWS_SECRET_ACCESS_KEY": secret_key,
            "AWS_CONFIG_FILE": os.devnull,
            "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
            "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_PAGER": "",
            "AWS_CLI_AUTO_PROMPT": "off",
            "AWS_DEFAULT_OUTPUT": "json",
        })
    else:
        env.update({
            "ALIBABA_CLOUD_ACCESS_KEY_ID": access_key,
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET": secret_key,
            "ALIBABA_CLOUD_IGNORE_PROFILE": "TRUE",
        })
    try:
        result = subprocess.run(
            [args.provider, *args.command, "--region", region],
            env=env, capture_output=True,
        )
    except OSError:
        sys.exit("Could not start the selected cloud CLI")
    for output, stream in ((result.stdout, sys.stdout), (result.stderr, sys.stderr)):
        for value in (access_key, secret_key):
            output = output.replace(value.encode(), b"[REDACTED]")
        stream.buffer.write(output)
        stream.buffer.flush()
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


if __name__ == "__main__":
    sys.exit(main())
