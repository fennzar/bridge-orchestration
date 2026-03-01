#!/usr/bin/env python3
"""Generate fresh EVM keys and infrastructure secrets for the bridge stack.

Usage:
  ./scripts/keygen.py                  # Print generated keys to stdout
  ./scripts/keygen.py --write-env      # Write to .env (from .env.example template)
  ./scripts/keygen.py --mode dev       # Dev mode (default): mnemonic + random keys
  ./scripts/keygen.py --mode prod      # Prod mode: all random, no mnemonic
  ./scripts/keygen.py --write-env --force  # Overwrite existing .env without asking
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"


def run(cmd: list[str]) -> str:
    """Run a command and return stripped stdout."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def generate_keypair() -> tuple[str, str]:
    """Generate a random EVM keypair via cast. Returns (address, private_key)."""
    out = run(["cast", "wallet", "new", "--json"])
    data = json.loads(out)
    entry = data[0] if isinstance(data, list) else data
    return entry["address"], entry["private_key"]


def generate_mnemonic() -> tuple[str, str, str]:
    """Generate a BIP-39 mnemonic + index-0 account. Returns (mnemonic, address, private_key)."""
    out = run(["cast", "wallet", "new-mnemonic"])
    # Parse: "Phrase:\n<mnemonic>\n\nAccounts:\n- Account 0:\nAddress: ...\nPrivate key: ..."
    mnemonic = ""
    address = ""
    pk = ""
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "Phrase:" and i + 1 < len(lines):
            mnemonic = lines[i + 1].strip()
        if "Address:" in line:
            address = line.split("Address:")[-1].strip()
        if "Private key:" in line:
            pk = line.split("Private key:")[-1].strip()
    if not mnemonic or not address or not pk:
        raise RuntimeError(f"Failed to parse mnemonic output:\n{out}")
    return mnemonic, address, pk


def generate_keys(mode: str) -> dict[str, str]:
    """Generate all keys for the given mode. Returns a dict of placeholder -> value."""
    keys: dict[str, str] = {}

    if mode == "dev":
        mnemonic, deployer_addr, deployer_pk = generate_mnemonic()
        keys["EVM_DEV_MNEMONIC"] = mnemonic
        keys["DEPLOYER_ADDRESS"] = deployer_addr
        keys["DEPLOYER_PRIVATE_KEY"] = deployer_pk
    else:
        # Prod: no mnemonic, deployer is a random keypair
        keys["EVM_DEV_MNEMONIC"] = "N/A (prod mode - no mnemonic)"
        deployer_addr, deployer_pk = generate_keypair()
        keys["DEPLOYER_ADDRESS"] = deployer_addr
        keys["DEPLOYER_PRIVATE_KEY"] = deployer_pk

    # Bridge signer
    addr, pk = generate_keypair()
    keys["BRIDGE_SIGNER_ADDRESS"] = addr
    keys["BRIDGE_PK"] = pk

    # Engine
    addr, pk = generate_keypair()
    keys["ENGINE_ADDRESS"] = addr
    keys["ENGINE_PK"] = pk

    # CEX (fake exchange EVM wallet)
    addr, pk = generate_keypair()
    keys["CEX_ADDRESS"] = addr
    keys["CEX_PK"] = pk

    # Test users 1-3
    for i in range(1, 4):
        addr, pk = generate_keypair()
        keys[f"TEST_USER_{i}_ADDRESS"] = addr
        keys[f"TEST_USER_{i}_PK"] = pk

    # Infrastructure secrets
    keys["POSTGRES_PASSWORD"] = secrets.token_hex(16)
    keys["ADMIN_TOKEN"] = secrets.token_hex(32)

    return keys


def print_keys(keys: dict[str, str], mode: str) -> None:
    """Pretty-print generated keys to stdout."""
    print(f"\n=== Generated Keys ({mode} mode) ===\n")

    if mode == "dev":
        print("ANVIL MNEMONIC:")
        print(f"  EVM_DEV_MNEMONIC={keys['EVM_DEV_MNEMONIC']}")
        print()
        print("DEPLOYER (mnemonic index 0):")
    else:
        print("DEPLOYER (random keypair):")
    print(f"  DEPLOYER_ADDRESS={keys['DEPLOYER_ADDRESS']}")
    print(f"  DEPLOYER_PRIVATE_KEY={keys['DEPLOYER_PRIVATE_KEY']}")
    print()

    print("BRIDGE SIGNER:")
    print(f"  BRIDGE_SIGNER_ADDRESS={keys['BRIDGE_SIGNER_ADDRESS']}")
    print(f"  BRIDGE_PK={keys['BRIDGE_PK']}")
    print()

    print("ENGINE:")
    print(f"  ENGINE_ADDRESS={keys['ENGINE_ADDRESS']}")
    print(f"  ENGINE_PK={keys['ENGINE_PK']}")
    print()

    print("CEX (fake exchange):")
    print(f"  CEX_ADDRESS={keys['CEX_ADDRESS']}")
    print(f"  CEX_PK={keys['CEX_PK']}")
    print()

    for i in range(1, 4):
        print(f"TEST USER {i}:")
        print(f"  TEST_USER_{i}_ADDRESS={keys[f'TEST_USER_{i}_ADDRESS']}")
        print(f"  TEST_USER_{i}_PK={keys[f'TEST_USER_{i}_PK']}")
        print()

    print("INFRASTRUCTURE:")
    print(f"  POSTGRES_PASSWORD={keys['POSTGRES_PASSWORD']}")
    print(f"  ADMIN_TOKEN={keys['ADMIN_TOKEN']}")
    print()

    if mode == "dev":
        print("NOTE: After generating new keys, import the mnemonic into MetaMask")
        print("      to access the deployer account in the browser.")
    print()


def detect_paths() -> dict[str, str]:
    """Auto-detect ROOT and PATH values based on repo layout."""
    parent = ROOT.parent
    paths: dict[str, str] = {}

    # ROOT = parent directory containing all sibling repos
    paths["ROOT"] = str(parent)

    # PATH = include node (via nvm), foundry, and system PATH
    path_parts: list[str] = []

    # nvm node
    nvm_dir = Path(os.environ.get("NVM_DIR", Path.home() / ".nvm"))
    if nvm_dir.exists():
        # Find the current node version directory
        node_bin = shutil.which("node")
        if node_bin:
            path_parts.append(str(Path(node_bin).parent))

    # foundry
    foundry_bin = Path.home() / ".foundry" / "bin"
    if foundry_bin.exists():
        path_parts.append(str(foundry_bin))

    path_parts.append("$PATH")
    paths["PATH"] = ":".join(path_parts)

    return paths


def write_env(keys: dict[str, str], force: bool) -> None:
    """Read .env.example, replace <KEYGEN:XXX> placeholders, write .env."""
    if not ENV_EXAMPLE.exists():
        print(f"Error: {ENV_EXAMPLE} not found", file=sys.stderr)
        sys.exit(1)

    if ENV_FILE.exists() and not force:
        resp = input(f"{ENV_FILE} already exists. Overwrite? [y/N] ").strip().lower()
        if resp != "y":
            print("Aborted.")
            sys.exit(0)

    template = ENV_EXAMPLE.read_text()

    # Replace all <KEYGEN:XXX> placeholders
    def replacer(match: re.Match) -> str:
        name = match.group(1)
        if name in keys:
            return keys[name]
        print(f"Warning: unknown placeholder <KEYGEN:{name}>", file=sys.stderr)
        return match.group(0)

    output = re.sub(r"<KEYGEN:(\w+)>", replacer, template)

    # Auto-detect and set ROOT and PATH
    detected = detect_paths()

    # Replace ROOT placeholder
    output = re.sub(
        r"^ROOT=.*$",
        f"ROOT={detected['ROOT']}",
        output,
        count=1,
        flags=re.MULTILINE,
    )

    # Replace PATH line
    output = re.sub(
        r"^PATH=.*$",
        f"PATH={detected['PATH']}",
        output,
        count=1,
        flags=re.MULTILINE,
    )

    # Verify no unresolved placeholders remain
    remaining = re.findall(r"<KEYGEN:\w+>", output)
    if remaining:
        print(f"Warning: {len(remaining)} unresolved placeholders: {remaining}", file=sys.stderr)

    ENV_FILE.write_text(output)
    print(f"Written to {ENV_FILE}")
    print(f"  ROOT={detected['ROOT']}")
    print(f"  PATH={detected['PATH']}")
    print(f"Next: run ./scripts/sync-env.sh to propagate to sub-repos")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate EVM keys and secrets")
    parser.add_argument("--mode", choices=["dev", "prod"], default="dev",
                        help="Key generation mode (default: dev)")
    parser.add_argument("--write-env", action="store_true",
                        help="Write generated keys to .env")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite .env without asking")
    args = parser.parse_args()

    # Verify cast is available
    try:
        run(["cast", "--version"])
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Error: 'cast' (Foundry) is required but not found in PATH.", file=sys.stderr)
        print("Install: https://getfoundry.sh", file=sys.stderr)
        sys.exit(1)

    keys = generate_keys(args.mode)
    print_keys(keys, args.mode)

    if args.write_env:
        write_env(keys, args.force)


if __name__ == "__main__":
    main()
