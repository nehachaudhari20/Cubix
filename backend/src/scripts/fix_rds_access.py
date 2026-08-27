"""
Open RDS PostgreSQL access for your current public IP.

Requires valid AWS credentials with permission to modify RDS security groups.

Usage:
  python src/scripts/fix_rds_access.py
  python src/scripts/fix_rds_access.py --check-only
  python src/scripts/fix_rds_access.py --ip 49.204.164.70/32
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

import boto3
import requests
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
os.chdir(ROOT)
load_dotenv(ROOT / ".env")

from backend.platform.config import get_settings  # noqa: E402


def get_public_ip() -> str:
    return requests.get("https://checkip.amazonaws.com", timeout=15).text.strip()


def tcp_probe(host: str, port: int, timeout: float = 10.0) -> tuple[bool, str]:
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror as exc:
        return False, f"DNS failed: {exc}"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True, f"TCP {host} ({ip}):{port} reachable"
    except OSError as exc:
        return False, f"TCP {host} ({ip}):{port} blocked — {exc}"
    finally:
        sock.close()


def _boto_session(settings):
    kwargs: dict = {"region_name": settings.aws_region}
    if settings.aws_profile:
        kwargs["profile_name"] = settings.aws_profile
    return boto3.Session(**kwargs)


def find_db_instance(rds_client, host: str):
    paginator = rds_client.get_paginator("describe_db_instances")
    for page in paginator.paginate():
        for db in page["DBInstances"]:
            endpoint = db.get("Endpoint") or {}
            if endpoint.get("Address") == host:
                return db
    raise SystemExit(f"No RDS instance found with endpoint {host} in {rds_client.meta.region_name}")


def ensure_public_access(rds_client, db_instance, apply: bool) -> None:
    ident = db_instance["DBInstanceIdentifier"]
    if db_instance.get("PubliclyAccessible"):
        print(f"  RDS {ident}: already publicly accessible")
        return

    print(f"  RDS {ident}: PubliclyAccessible=false — enabling (may take a few minutes)")
    if not apply:
        print("  (dry-run: skipped modify_db_instance)")
        return

    rds_client.modify_db_instance(
        DBInstanceIdentifier=ident,
        PubliclyAccessible=True,
        ApplyImmediately=True,
    )
    print("  modify_db_instance submitted — wait for status 'available' before connecting")


def authorize_ip(ec2_client, security_group_id: str, cidr: str, apply: bool) -> None:
    perm = {
        "IpProtocol": "tcp",
        "FromPort": 5432,
        "ToPort": 5432,
        "IpRanges": [{"CidrIp": cidr, "Description": "RedBlue local dev access"}],
    }
    if not apply:
        print(f"  Would allow PostgreSQL from {cidr} on {security_group_id}")
        return

    try:
        ec2_client.authorize_security_group_ingress(GroupId=security_group_id, IpPermissions=[perm])
        print(f"  Added inbound rule on {security_group_id} for {cidr}")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("InvalidPermission.Duplicate", "RulesPerSecurityGroupLimitExceeded"):
            print(f"  Rule already exists or limit hit on {security_group_id}: {code}")
        else:
            raise


def verify_aws_credentials(session) -> str:
    sts = session.client("sts")
    identity = sts.get_caller_identity()
    arn = identity.get("Arn", "unknown")
    print(f"AWS identity: {arn}")
    return arn


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix RDS network access for local development")
    parser.add_argument("--check-only", action="store_true", help="Diagnose only; do not modify AWS")
    parser.add_argument("--ip", help="CIDR to allow (default: your current public IP /32)")
    parser.add_argument("--apply", action="store_true", help="Apply AWS changes (default without flag is dry-run)")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.rds_host or not settings.rds_username:
        raise SystemExit("Set RDS_HOST and RDS_USERNAME in .env")

    print("=== RDS connectivity diagnosis ===")
    print(f"  Host:   {settings.rds_host}")
    print(f"  Region: {settings.aws_region}")
    print(f"  Auth:   {settings.db_auth_mode}")

    ok, msg = tcp_probe(settings.rds_host, settings.rds_port)
    print(f"  Probe:  {msg}")
    if ok:
        print("\nPort 5432 is already reachable — no security-group change needed.")
        return

    my_ip = (args.ip or f"{get_public_ip()}/32").strip()
    if "/" not in my_ip:
        my_ip = f"{my_ip}/32"
    print(f"  Your IP: {my_ip}")

    if args.check_only:
        print("\n--check-only: skipping AWS changes.")
        print("Fix: run with --apply after configuring valid AWS credentials:")
        print("  aws configure   # or set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY")
        print("  python src/scripts/fix_rds_access.py --apply")
        sys.exit(1)

    apply = args.apply
    if not apply:
        print("\nDry-run mode (pass --apply to modify AWS resources)")

    try:
        session = _boto_session(settings)
        verify_aws_credentials(session)
        rds = session.client("rds")
        ec2 = session.client("ec2")

        db = find_db_instance(rds, settings.rds_host)
        ident = db["DBInstanceIdentifier"]
        print(f"\nFound instance: {ident}")
        print(f"  Status: {db.get('DBInstanceStatus')}")
        print(f"  Public: {db.get('PubliclyAccessible')}")

        sg_ids = [sg["VpcSecurityGroupId"] for sg in db.get("VpcSecurityGroups", [])]
        if not sg_ids:
            raise SystemExit("No VPC security groups attached to RDS instance")

        ensure_public_access(rds, db, apply=apply)
        print("\nSecurity groups:")
        for sg_id in sg_ids:
            authorize_ip(ec2, sg_id, my_ip, apply=apply)

        if apply:
            print("\nWaiting 5s then re-probing...")
            import time
            time.sleep(5)
            ok, msg = tcp_probe(settings.rds_host, settings.rds_port, timeout=15)
            print(f"  Re-probe: {msg}")
            if ok:
                print("\nSuccess. Test with: python src/scripts/query_rds.py --tables")
            else:
                print("\nStill blocked — RDS modify may still be in progress, or a network ACL blocks 5432.")
        else:
            print("\nRe-run with --apply to open access.")

    except NoCredentialsError:
        print("\nNo AWS credentials found.")
        print("Configure credentials, then re-run:")
        print("  aws configure")
        print("  python src/scripts/fix_rds_access.py --apply")
        sys.exit(1)
    except ClientError as exc:
        print(f"\nAWS API error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
