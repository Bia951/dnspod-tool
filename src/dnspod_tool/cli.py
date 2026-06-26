from __future__ import annotations

import argparse
import getpass
import json
import sys
from typing import Any, Sequence

from . import __version__
from .api import DEFAULT_RECORD_LINE, DnspodClient
from .config import Credential, CredentialStore, default_profile
from .errors import DnspodToolError
from .models import Record


class DetailedArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any):
        kwargs.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> None:
        self.print_help(sys.stderr)
        self.exit(2, f"\nError: {message}\n")


TOP_LEVEL_EPILOG = """Examples:
  dnspod tui
  dnspod use example.com
  dnspod ls
  dnspod add www A 203.0.113.10
  dnspod set www A 203.0.113.11
  dnspod del www
  dnspod auth status
  dnspod domains list
  dnspod records list example.com
  dnspod records create example.com --name www --type A --value 203.0.113.10

The global `--profile` / `-p` option may be placed anywhere.
Run `dnspod <command> --help` for command-specific help.
"""

USE_EPILOG = """Examples:
  dnspod use
  dnspod use example.com
  dnspod -p work use example.com
"""

LS_EPILOG = """Examples:
  dnspod ls
  dnspod ls example.com
  dnspod ls --json
"""

ADD_EPILOG = """Examples:
  dnspod add www A 203.0.113.10
  dnspod add example.com www A 203.0.113.10
  dnspod add mail MX mail.example.com --mx 10
"""

SET_EPILOG = """Examples:
  dnspod set www A 203.0.113.11
  dnspod set example.com www A 203.0.113.11
  dnspod set api CNAME target.example.com
"""

DEL_EPILOG = """Examples:
  dnspod del www
  dnspod del example.com www
  dnspod del example.com 123456 --yes
  dnspod del example.com www A --yes
"""

AUTH_EPILOG = """Examples:
  dnspod auth status
  dnspod auth token --id 12345 --token your-token --storage auto
  dnspod auth key --secret-id your-secret-id --secret-key your-secret-key --storage file
  dnspod auth clear --storage file
"""

DOMAINS_EPILOG = """Examples:
  dnspod domains list
  dnspod domains list --json
  dnspod domains list --token-id 12345 --token your-token
"""

RECORDS_EPILOG = """Examples:
  dnspod records list example.com
  dnspod records create example.com --name www --type A --value 203.0.113.10
  dnspod records update example.com 123456 --value 203.0.113.11
  dnspod records delete example.com 123456 --yes

Runtime credential examples:
  dnspod records list example.com --token-id 12345 --token your-token
  dnspod records list example.com --secret-id your-secret-id --secret-key your-secret-key
"""

RECORDS_LIST_EPILOG = """Examples:
  dnspod records list example.com
  dnspod records list example.com --json
  dnspod records list example.com --secret-id your-secret-id --secret-key your-secret-key
"""

RECORDS_CREATE_EPILOG = """Examples:
  dnspod records create example.com --name www --type A --value 203.0.113.10
  dnspod records create example.com --name mail --type MX --value mail.example.com --mx 10
"""

RECORDS_UPDATE_EPILOG = """Examples:
  dnspod records update example.com 123456 --value 203.0.113.11
  dnspod records update example.com 123456 --name api --type CNAME --value target.example.com
"""

RECORDS_DELETE_EPILOG = """Examples:
  dnspod records delete example.com 123456
  dnspod records delete example.com 123456 --yes
"""


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    profile, args_list = extract_profile(args_list)
    if not args_list:
        from .tui import run_interactive

        return run_interactive(profile)

    parser = build_parser(profile)
    args = parser.parse_args(args_list)
    args.profile = profile

    try:
        return args.handler(args)
    except DnspodToolError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


def extract_profile(args_list: list[str]) -> tuple[str, list[str]]:
    profile = default_profile()
    cleaned: list[str] = []
    index = 0
    while index < len(args_list):
        item = args_list[index]
        if item == "--":
            cleaned.extend(args_list[index:])
            break
        if item == "--profile" or item == "-p":
            if index + 1 >= len(args_list):
                raise SystemExit("Error: --profile requires a value.\n")
            profile = args_list[index + 1]
            index += 2
            continue
        if item.startswith("--profile="):
            profile = item.split("=", 1)[1]
            index += 1
            continue
        cleaned.append(item)
        index += 1
    return profile, cleaned


def build_parser(profile: str | None = None) -> argparse.ArgumentParser:
    parser = DetailedArgumentParser(
        prog="dnspod",
        description="Manage DNSPod domains and records from the command line.",
        epilog=TOP_LEVEL_EPILOG,
    )
    parser.add_argument("--version", action="version", version=f"dnspod-tool {__version__}")
    parser.add_argument(
        "-p",
        "--profile",
        default=profile or default_profile(),
        help="Profile name. This option can be placed anywhere in the command.",
    )
    subparsers = parser.add_subparsers(dest="command", parser_class=DetailedArgumentParser)

    tui_parser = subparsers.add_parser("tui", help="Open the interactive terminal UI.")
    tui_parser.set_defaults(handler=handle_tui)

    use_parser = subparsers.add_parser("use", help="Show or set the default domain.", epilog=USE_EPILOG)
    use_parser.add_argument("domain", nargs="?", help="Domain to use by default.")
    use_parser.set_defaults(handler=handle_use)

    ls_parser = subparsers.add_parser("ls", help="List records with the default domain.", epilog=LS_EPILOG)
    ls_parser.add_argument("domain", nargs="?", help="Domain to list. Defaults to `dnspod use`.")
    ls_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    add_runtime_credential_options(ls_parser)
    ls_parser.set_defaults(handler=handle_short_list)

    add_parser = subparsers.add_parser("add", help="Create a record with short syntax.", epilog=ADD_EPILOG)
    add_parser.usage = "dnspod add [domain] name type value [options]"
    add_parser.add_argument("items", nargs="+", metavar="item", help="[domain] name type value")
    add_record_options(add_parser)
    add_runtime_credential_options(add_parser)
    add_parser.set_defaults(handler=handle_short_add)

    set_parser = subparsers.add_parser("set", help="Create or update a record.", epilog=SET_EPILOG)
    set_parser.usage = "dnspod set [domain] name type value [options]"
    set_parser.add_argument("items", nargs="+", metavar="item", help="[domain] name type value")
    add_record_options(set_parser)
    add_runtime_credential_options(set_parser)
    set_parser.set_defaults(handler=handle_short_set)

    del_parser = subparsers.add_parser("del", help="Delete a record by ID or record name.", epilog=DEL_EPILOG)
    del_parser.usage = "dnspod del [domain] id|name [type] [value] [options]"
    del_parser.add_argument("items", nargs="+", metavar="item", help="[domain] id|name [type] [value]")
    del_parser.add_argument("-y", "--yes", action="store_true", help="Do not prompt for confirmation.")
    add_runtime_credential_options(del_parser)
    del_parser.set_defaults(handler=handle_short_delete)

    auth_parser = subparsers.add_parser("auth", help="Manage credentials.", epilog=AUTH_EPILOG)
    auth_parser.set_defaults(
        handler=missing_subcommand_handler(
            auth_parser,
            "Choose an auth command: token, key, status, or clear.",
        )
    )
    auth_subparsers = auth_parser.add_subparsers(
        dest="auth_command",
        parser_class=DetailedArgumentParser,
    )

    token_parser = auth_subparsers.add_parser(
        "token",
        help="Save DNSPod token credentials.",
        epilog="Example:\n  dnspod auth token --id 12345 --token your-token --storage file",
    )
    token_parser.add_argument("--id", dest="token_id", help="DNSPod token ID.")
    token_parser.add_argument("--token", help="DNSPod token value.")
    add_storage_option(token_parser)
    token_parser.set_defaults(handler=handle_auth_token)

    key_parser = auth_subparsers.add_parser(
        "key",
        help="Save Tencent Cloud SecretId/SecretKey.",
        epilog=(
            "Example:\n"
            "  dnspod auth key --secret-id your-secret-id "
            "--secret-key your-secret-key --storage file"
        ),
    )
    key_parser.add_argument("--secret-id", help="Tencent Cloud SecretId.")
    key_parser.add_argument("--secret-key", help="Tencent Cloud SecretKey.")
    add_storage_option(key_parser)
    key_parser.set_defaults(handler=handle_auth_key)

    status_parser = auth_subparsers.add_parser("status", help="Show credential status.")
    status_parser.set_defaults(handler=handle_auth_status)

    clear_parser = auth_subparsers.add_parser(
        "clear",
        help="Remove saved credentials.",
        epilog="Example:\n  dnspod auth clear --storage all --yes",
    )
    clear_parser.add_argument("--storage", choices=("all", "keyring", "file"), default="all")
    clear_parser.add_argument("-y", "--yes", action="store_true", help="Do not prompt for confirmation.")
    clear_parser.set_defaults(handler=handle_auth_clear)

    domains_parser = subparsers.add_parser("domains", help="Manage domains.", epilog=DOMAINS_EPILOG)
    domains_parser.set_defaults(
        handler=missing_subcommand_handler(
            domains_parser,
            "Choose a domains command: list.",
        )
    )
    domains_subparsers = domains_parser.add_subparsers(
        dest="domains_command",
        parser_class=DetailedArgumentParser,
    )
    domains_list_parser = domains_subparsers.add_parser(
        "list",
        help="List domains.",
        epilog=DOMAINS_EPILOG,
    )
    domains_list_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    add_runtime_credential_options(domains_list_parser)
    domains_list_parser.set_defaults(handler=handle_domains_list)

    records_parser = subparsers.add_parser("records", help="Manage records.", epilog=RECORDS_EPILOG)
    records_parser.set_defaults(
        handler=missing_subcommand_handler(
            records_parser,
            "Choose a records command: list, create, update, or delete.",
        )
    )
    records_subparsers = records_parser.add_subparsers(
        dest="records_command",
        parser_class=DetailedArgumentParser,
    )

    records_list_parser = records_subparsers.add_parser(
        "list",
        help="List records for a domain.",
        epilog=RECORDS_LIST_EPILOG,
    )
    records_list_parser.add_argument("domain")
    records_list_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    add_runtime_credential_options(records_list_parser)
    records_list_parser.set_defaults(handler=handle_records_list)

    create_parser = records_subparsers.add_parser(
        "create",
        help="Create a record.",
        epilog=RECORDS_CREATE_EPILOG,
    )
    create_parser.add_argument("domain")
    create_parser.add_argument("--name", required=True, help="Record name, for example www, @, or *.")
    create_parser.add_argument("--type", required=True, dest="record_type", help="Record type, for example A.")
    create_parser.add_argument("--value", required=True, help="Record value.")
    add_record_options(create_parser)
    add_runtime_credential_options(create_parser)
    create_parser.set_defaults(handler=handle_records_create)

    update_parser = records_subparsers.add_parser(
        "update",
        help="Update a record.",
        epilog=RECORDS_UPDATE_EPILOG,
    )
    update_parser.add_argument("domain")
    update_parser.add_argument("record_id")
    update_parser.add_argument("--name", help="New record name.")
    update_parser.add_argument("--type", dest="record_type", help="New record type.")
    update_parser.add_argument("--value", help="New record value.")
    add_record_options(update_parser)
    add_runtime_credential_options(update_parser)
    update_parser.set_defaults(handler=handle_records_update)

    delete_parser = records_subparsers.add_parser(
        "delete",
        help="Delete a record.",
        epilog=RECORDS_DELETE_EPILOG,
    )
    delete_parser.add_argument("domain")
    delete_parser.add_argument("record_id")
    delete_parser.add_argument("-y", "--yes", action="store_true", help="Do not prompt for confirmation.")
    add_runtime_credential_options(delete_parser)
    delete_parser.set_defaults(handler=handle_records_delete)

    return parser


def missing_subcommand_handler(parser: argparse.ArgumentParser, message: str):
    def handler(args: argparse.Namespace) -> int:
        parser.print_help(sys.stderr)
        print(f"\nError: {message}", file=sys.stderr)
        return 2

    return handler


def add_storage_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--storage",
        choices=("auto", "keyring", "file"),
        default="auto",
        help="Credential storage backend. Use file on headless Linux if keyring is unavailable.",
    )


def add_runtime_credential_options(parser: argparse.ArgumentParser) -> None:
    auth_group = parser.add_argument_group("runtime credentials")
    auth_group.add_argument("--token-id", help="DNSPod token ID for this command.")
    auth_group.add_argument("--token", help="DNSPod token value for this command.")
    auth_group.add_argument("--secret-id", help="Tencent Cloud SecretId for this command.")
    auth_group.add_argument("--secret-key", help="Tencent Cloud SecretKey for this command.")
    auth_group.add_argument(
        "--auth-storage",
        choices=("auto", "keyring", "file"),
        default="auto",
        help="Storage backend to use if command-line credentials are saved.",
    )
    save_group = auth_group.add_mutually_exclusive_group()
    save_group.add_argument(
        "--save-credentials",
        action="store_true",
        help="Save command-line credentials without prompting.",
    )
    save_group.add_argument(
        "--no-save-credentials",
        action="store_true",
        help="Do not ask to save command-line credentials.",
    )


def add_record_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--line", default=None, help="Record line. Defaults to DNSPod's default line.")
    parser.add_argument("--mx", type=int, help="MX priority.")
    parser.add_argument("--ttl", type=int, help="TTL in seconds.")


def handle_tui(args: argparse.Namespace) -> int:
    from .tui import run_interactive

    return run_interactive(args.profile)


def handle_auth_token(args: argparse.Namespace) -> int:
    token_id = args.token_id or input("DNSPod token ID: ").strip()
    token = args.token or getpass.getpass("DNSPod token: ").strip()
    credential = Credential(mode="token", token_id=token_id, token=token)
    storage = store_from_args(args).save(credential, args.storage)
    print(f"Saved DNSPod token credentials to {storage} for profile `{args.profile}`.")
    return 0


def handle_auth_key(args: argparse.Namespace) -> int:
    secret_id = args.secret_id or input("Tencent Cloud SecretId: ").strip()
    secret_key = args.secret_key or getpass.getpass("Tencent Cloud SecretKey: ").strip()
    credential = Credential(mode="key", secret_id=secret_id, secret_key=secret_key)
    storage = store_from_args(args).save(credential, args.storage)
    print(f"Saved Tencent Cloud key credentials to {storage} for profile `{args.profile}`.")
    return 0


def handle_auth_status(args: argparse.Namespace) -> int:
    status = store_from_args(args).status()
    if not status["configured"]:
        print("No credentials configured.")
        print(f"Profile: {status['profile']}")
        print(f"Default domain: {status['default_domain'] or '-'}")
        print(f"Config directory: {status['config_dir']}")
        return 1
    print("Credentials configured.")
    print(f"Profile: {status['profile']}")
    print(f"Mode: {status['mode']}")
    print(f"Source: {status['source']}")
    print(f"Default domain: {status['default_domain'] or '-'}")
    print(f"Config directory: {status['config_dir']}")
    return 0


def handle_auth_clear(args: argparse.Namespace) -> int:
    if not args.yes:
        answer = input(f"Remove {args.storage} saved credentials? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return 0
    store_from_args(args).clear(args.storage)
    print(f"Saved credentials removed for profile `{args.profile}`.")
    return 0


def handle_use(args: argparse.Namespace) -> int:
    store = store_from_args(args)
    if not args.domain:
        current = store.get_default_domain()
        if current:
            print(current)
            return 0
        print(f"No default domain set for profile `{args.profile}`.")
        print("Run `dnspod use example.com` or pass a domain to commands.")
        return 1
    store.set_default_domain(args.domain)
    print(f"Default domain for profile `{args.profile}` set to {args.domain}.")
    return 0


def handle_short_list(args: argparse.Namespace) -> int:
    domain = args.domain or require_default_domain(args)
    return list_records_for_domain(args, domain)


def handle_short_add(args: argparse.Namespace) -> int:
    domain, name, record_type, value = parse_record_write_items(args, "add")
    client = load_client(args)
    client.create_record(
        domain=domain,
        name=name,
        record_type=record_type.upper(),
        value=value,
        line=args.line or DEFAULT_RECORD_LINE,
        mx=args.mx,
        ttl=args.ttl,
    )
    print(f"Record created: {name} {record_type.upper()} {value}")
    return 0


def handle_short_set(args: argparse.Namespace) -> int:
    domain, name, record_type, value = parse_record_write_items(args, "set")
    client = load_client(args)
    matches = [
        record
        for record in client.list_records(domain)
        if record.name == name and record.record_type.upper() == record_type.upper()
    ]
    if not matches:
        client.create_record(
            domain=domain,
            name=name,
            record_type=record_type.upper(),
            value=value,
            line=args.line or DEFAULT_RECORD_LINE,
            mx=args.mx,
            ttl=args.ttl,
        )
        print(f"Record created: {name} {record_type.upper()} {value}")
        return 0

    if len(matches) > 1:
        print_record_table([record.to_dict() for record in matches])
        raise DnspodToolError(
            "Multiple records match this name and type. Use `records update` with a record ID."
        )

    current = matches[0]
    client.modify_record(
        domain=domain,
        record_id=current.record_id,
        name=current.name,
        record_type=current.record_type,
        value=value,
        line=args.line or current.line or DEFAULT_RECORD_LINE,
        mx=args.mx if args.mx is not None else current.mx,
        ttl=args.ttl if args.ttl is not None else current.ttl,
    )
    print(f"Record updated: {name} {record_type.upper()} {value}")
    return 0


def handle_short_delete(args: argparse.Namespace) -> int:
    domain, target, record_type, value = parse_delete_items(args)
    client = load_client(args)

    target_id = target[1:] if target.startswith("#") else target
    if target_id.isdigit():
        record = find_record(client, domain, target_id)
    else:
        matches = [record for record in client.list_records(domain) if record.name == target]
        if record_type:
            matches = [
                record for record in matches if record.record_type.upper() == record_type.upper()
            ]
        if value:
            matches = [record for record in matches if record.value == value]
        if not matches:
            raise DnspodToolError(f"No record matched `{target}` in {domain}.")
        if len(matches) > 1:
            print_record_table([record.to_dict() for record in matches])
            raise DnspodToolError("Multiple records matched. Add type/value filters or delete by ID.")
        record = matches[0]

    if not args.yes:
        prompt = (
            f"Delete {record.name} {record.record_type} {record.value} "
            f"from {domain}? [y/N]: "
        )
        answer = input(prompt).strip().lower()
        if answer != "y":
            print("Aborted.")
            return 0

    client.delete_record(domain, record.record_id)
    print(f"Record deleted: {record.name} {record.record_type} {record.value}")
    return 0


def handle_domains_list(args: argparse.Namespace) -> int:
    client = load_client(args)
    domains = client.list_domains()
    rows = [domain.to_dict() for domain in domains]
    if args.json:
        print_json(rows)
    else:
        print_table(rows, [("name", "Domain")])
    return 0


def handle_records_list(args: argparse.Namespace) -> int:
    return list_records_for_domain(args, args.domain)


def handle_records_create(args: argparse.Namespace) -> int:
    client = load_client(args)
    client.create_record(
        domain=args.domain,
        name=args.name,
        record_type=args.record_type.upper(),
        value=args.value,
        line=args.line or DEFAULT_RECORD_LINE,
        mx=args.mx,
        ttl=args.ttl,
    )
    print("Record created.")
    return 0


def handle_records_update(args: argparse.Namespace) -> int:
    client = load_client(args)
    current = find_record(client, args.domain, args.record_id)
    client.modify_record(
        domain=args.domain,
        record_id=current.record_id,
        name=args.name or current.name,
        record_type=(args.record_type or current.record_type).upper(),
        value=args.value or current.value,
        line=args.line or current.line or DEFAULT_RECORD_LINE,
        mx=args.mx if args.mx is not None else current.mx,
        ttl=args.ttl if args.ttl is not None else current.ttl,
    )
    print("Record updated.")
    return 0


def handle_records_delete(args: argparse.Namespace) -> int:
    if not args.yes:
        answer = input(f"Delete record {args.record_id} from {args.domain}? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return 0
    client = load_client(args)
    client.delete_record(args.domain, args.record_id)
    print("Record deleted.")
    return 0


def list_records_for_domain(args: argparse.Namespace, domain: str) -> int:
    client = load_client(args)
    records = client.list_records(domain)
    rows = [record.to_dict() for record in records]
    if args.json:
        print_json(rows)
    else:
        print(f"Domain: {domain}")
        print_record_table(rows)
    return 0


def store_from_args(args: argparse.Namespace | None = None) -> CredentialStore:
    profile = getattr(args, "profile", default_profile()) if args is not None else default_profile()
    return CredentialStore(profile=profile)


def load_client(args: argparse.Namespace | None = None) -> DnspodClient:
    credential = credential_from_args(args) if args is not None else None
    if credential is None:
        credential = store_from_args(args).load()
    else:
        maybe_save_runtime_credential(credential, args)
    return DnspodClient(credential)


def credential_from_args(args: argparse.Namespace | None) -> Credential | None:
    if args is None:
        return None

    token_id = getattr(args, "token_id", None)
    token = getattr(args, "token", None)
    secret_id = getattr(args, "secret_id", None)
    secret_key = getattr(args, "secret_key", None)

    if token and not token_id and "," in token:
        token_id, token = token.split(",", 1)

    has_token_fields = bool(token_id or token)
    has_key_fields = bool(secret_id or secret_key)
    if has_token_fields and has_key_fields:
        raise DnspodToolError(
            "Use either DNSPod token credentials or Tencent Cloud key credentials, not both."
        )
    if has_token_fields:
        if not token_id or not token:
            raise DnspodToolError("Both --token-id and --token are required for DNSPod token mode.")
        return Credential(mode="token", token_id=token_id, token=token, source="command-line")
    if has_key_fields:
        if not secret_id or not secret_key:
            raise DnspodToolError(
                "Both --secret-id and --secret-key are required for Tencent Cloud key mode."
            )
        return Credential(mode="key", secret_id=secret_id, secret_key=secret_key, source="command-line")
    return None


def maybe_save_runtime_credential(credential: Credential, args: argparse.Namespace) -> None:
    if getattr(args, "no_save_credentials", False):
        return

    should_save = bool(getattr(args, "save_credentials", False))
    if not should_save:
        if not sys.stdin.isatty():
            return
        print(
            "Command-line credentials were provided. Save them for future commands? [y/N]: ",
            end="",
            file=sys.stderr,
            flush=True,
        )
        answer = sys.stdin.readline().strip().lower()
        should_save = answer == "y"

    if should_save:
        storage = store_from_args(args).save(credential, getattr(args, "auth_storage", "auto"))
        print(
            f"Saved command-line credentials to {storage} for profile `{args.profile}`.",
            file=sys.stderr,
        )


def require_default_domain(args: argparse.Namespace) -> str:
    domain = store_from_args(args).get_default_domain()
    if not domain:
        raise DnspodToolError(
            "No default domain set. Run `dnspod use example.com` or pass a domain."
        )
    return domain


def parse_record_write_items(args: argparse.Namespace, command: str) -> tuple[str, str, str, str]:
    items = list(args.items)
    if len(items) == 3:
        domain = require_default_domain(args)
        name, record_type, value = items
        return domain, name, record_type, value
    if len(items) == 4:
        domain, name, record_type, value = items
        return domain, name, record_type, value
    raise DnspodToolError(
        f"Usage: dnspod {command} [domain] name type value. "
        f"Run `dnspod {command} --help` for examples."
    )


def parse_delete_items(args: argparse.Namespace) -> tuple[str, str, str | None, str | None]:
    items = list(args.items)
    if len(items) == 1:
        return require_default_domain(args), items[0], None, None
    if len(items) == 2:
        first, second = items
        if looks_like_domain(first):
            return first, second, None, None
        return require_default_domain(args), first, second, None
    if len(items) == 3:
        first, second, third = items
        if looks_like_domain(first):
            return first, second, third, None
        return require_default_domain(args), first, second, third
    if len(items) == 4:
        domain, target, record_type, value = items
        return domain, target, record_type, value
    raise DnspodToolError(
        "Usage: dnspod del [domain] id|name [type] [value]. "
        "Run `dnspod del --help` for examples."
    )


def looks_like_domain(value: str) -> bool:
    return "." in value and not value.startswith("#")


def find_record(client: DnspodClient, domain: str, record_id: str) -> Record:
    records = client.list_records(domain)
    for record in records:
        if record.record_id == str(record_id):
            return record
    raise DnspodToolError(f"Record not found: {record_id}")


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def print_record_table(rows: list[dict[str, Any]]) -> None:
    print_table(
        rows,
        [
            ("id", "ID"),
            ("name", "Name"),
            ("type", "Type"),
            ("value", "Value"),
            ("line", "Line"),
            ("ttl", "TTL"),
            ("mx", "MX"),
            ("status", "Status"),
        ],
    )


def print_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> None:
    if not rows:
        print("No results.")
        return
    widths = {}
    for key, label in columns:
        widths[key] = max(len(label), *(len(str(row.get(key) or "")) for row in rows))

    header = "  ".join(label.ljust(widths[key]) for key, label in columns)
    divider = "  ".join("-" * widths[key] for key, _ in columns)
    print(header)
    print(divider)
    for row in rows:
        print("  ".join(str(row.get(key) or "").ljust(widths[key]) for key, _ in columns))
