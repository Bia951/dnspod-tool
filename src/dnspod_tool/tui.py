from __future__ import annotations

import getpass
import os
import sys

from .api import DEFAULT_RECORD_LINE, DnspodClient
from .cli import print_record_table, print_table
from .config import Credential, CredentialStore
from .errors import DnspodToolError
from .models import Domain, Record


class TerminalUI:
    def __init__(self, profile: str = "default"):
        self.profile = profile
        self.store = CredentialStore(profile=profile)

    def run(self) -> int:
        while True:
            self.clear()
            print("DNSPod Tool")
            print("=" * 40)
            print(f"Profile: {self.profile}")
            print(f"Default domain: {self.store.get_default_domain() or '-'}")
            print("=" * 40)
            print("1. Credential settings")
            print("2. Use default domain")
            print("3. List domains")
            print("4. List records")
            print("5. Create record")
            print("6. Update record")
            print("7. Delete record")
            print("Q. Quit")
            choice = input("\nSelect an action: ").strip().lower()
            try:
                if choice == "1":
                    self.auth_menu()
                elif choice == "2":
                    self.use_domain()
                elif choice == "3":
                    self.list_domains()
                elif choice == "4":
                    self.list_records()
                elif choice == "5":
                    self.create_record()
                elif choice == "6":
                    self.update_record()
                elif choice == "7":
                    self.delete_record()
                elif choice == "q":
                    return 0
            except DnspodToolError as exc:
                print(f"\nError: {exc}")
                self.pause()
            except KeyboardInterrupt:
                print("\nInterrupted.")
                self.pause()

    def auth_menu(self) -> None:
        self.clear()
        status = self.store.status()
        print("Credential settings")
        print("=" * 40)
        print(f"Profile: {self.profile}")
        if status["configured"]:
            print(f"Current mode: {status['mode']}")
            print(f"Current source: {status['source']}")
        else:
            print("No credentials configured.")
        print()
        print("1. Save DNSPod token")
        print("2. Save Tencent Cloud key")
        print("3. Clear saved credentials")
        print("Q. Back")
        choice = input("\nSelect an action: ").strip().lower()
        if choice == "1":
            token_id = input("DNSPod token ID: ").strip()
            token = getpass.getpass("DNSPod token: ").strip()
            storage = self.prompt_storage()
            saved_to = self.store.save(Credential(mode="token", token_id=token_id, token=token), storage)
            print(f"\nSaved to {saved_to}.")
            self.pause()
        elif choice == "2":
            secret_id = input("Tencent Cloud SecretId: ").strip()
            secret_key = getpass.getpass("Tencent Cloud SecretKey: ").strip()
            storage = self.prompt_storage()
            saved_to = self.store.save(
                Credential(mode="key", secret_id=secret_id, secret_key=secret_key),
                storage,
            )
            print(f"\nSaved to {saved_to}.")
            self.pause()
        elif choice == "3":
            answer = input("Remove all saved credentials? [y/N]: ").strip().lower()
            if answer == "y":
                self.store.clear("all")
                print("Saved credentials removed.")
            else:
                print("Aborted.")
            self.pause()

    def use_domain(self) -> None:
        self.clear()
        current = self.store.get_default_domain()
        print("Use default domain")
        print("=" * 40)
        print(f"Current default domain: {current or '-'}")
        domain = input("New default domain, or press Enter to keep current: ").strip()
        if domain:
            self.store.set_default_domain(domain)
            print(f"\nDefault domain set to {domain}.")
        else:
            print("\nNo change.")
        self.pause()

    def list_domains(self) -> None:
        self.clear()
        domains = self.client().list_domains()
        print_table([domain.to_dict() for domain in domains], [("name", "Domain")])
        self.pause()

    def list_records(self) -> None:
        domain = self.select_domain()
        if not domain:
            return
        self.clear()
        records = self.client().list_records(domain.name)
        print(f"Domain: {domain.name}\n")
        print_record_table([record.to_dict() for record in records])
        self.pause()

    def create_record(self) -> None:
        domain = self.select_domain()
        if not domain:
            return
        self.clear()
        print(f"Create record for {domain.name}")
        print("=" * 40)
        name = input("Name [@]: ").strip() or "@"
        record_type = (input("Type [A]: ").strip() or "A").upper()
        value = input("Value: ").strip()
        line = input("Line [default]: ").strip() or DEFAULT_RECORD_LINE
        mx = self.optional_int("MX priority")
        ttl = self.optional_int("TTL")
        self.client().create_record(domain.name, name, record_type, value, line, mx=mx, ttl=ttl)
        print("\nRecord created.")
        self.pause()

    def update_record(self) -> None:
        domain = self.select_domain()
        if not domain:
            return
        record = self.select_record(domain.name)
        if not record:
            return
        self.clear()
        print(f"Update record {record.record_id} for {domain.name}")
        print("=" * 40)
        name = input(f"Name [{record.name}]: ").strip() or record.name
        record_type = input(f"Type [{record.record_type}]: ").strip().upper() or record.record_type
        value = input(f"Value [{record.value}]: ").strip() or record.value
        line = input(f"Line [{record.line or 'default'}]: ").strip() or record.line or DEFAULT_RECORD_LINE
        mx = self.optional_int("MX priority", record.mx)
        ttl = self.optional_int("TTL", record.ttl)
        self.client().modify_record(
            domain.name,
            record.record_id,
            name,
            record_type,
            value,
            line,
            mx=mx,
            ttl=ttl,
        )
        print("\nRecord updated.")
        self.pause()

    def delete_record(self) -> None:
        domain = self.select_domain()
        if not domain:
            return
        record = self.select_record(domain.name)
        if not record:
            return
        answer = input(f"Delete {record.name} {record.record_type} {record.value}? [y/N]: ").strip().lower()
        if answer == "y":
            self.client().delete_record(domain.name, record.record_id)
            print("Record deleted.")
        else:
            print("Aborted.")
        self.pause()

    def select_domain(self) -> Domain | None:
        self.clear()
        domains = self.client().list_domains()
        if not domains:
            print("No domains found.")
            self.pause()
            return None
        print("Domains")
        print("=" * 40)
        for index, domain in enumerate(domains, 1):
            print(f"{index}. {domain.name}")
        default_domain = self.store.get_default_domain()
        if default_domain:
            prompt = f"\nSelect a domain number, Enter for {default_domain}, or Q to cancel: "
        else:
            prompt = "\nSelect a domain number, or press Enter to cancel: "
        choice = input(prompt).strip()
        if not choice:
            if default_domain:
                return Domain(name=default_domain)
            return None
        if choice.lower() == "q":
            return None
        if not choice.isdigit() or not 1 <= int(choice) <= len(domains):
            print("Invalid selection.")
            self.pause()
            return None
        return domains[int(choice) - 1]

    def select_record(self, domain: str) -> Record | None:
        self.clear()
        records = self.client().list_records(domain)
        if not records:
            print("No records found.")
            self.pause()
            return None
        print(f"Records for {domain}")
        print("=" * 40)
        for index, record in enumerate(records, 1):
            print(f"{index}. {record.name} {record.record_type} {record.value} (ID: {record.record_id})")
        choice = input("\nSelect a record number, #ID, or press Enter to cancel: ").strip()
        if not choice:
            return None
        if choice.startswith("#"):
            wanted = choice[1:]
            for record in records:
                if record.record_id == wanted:
                    return record
        if choice.isdigit() and 1 <= int(choice) <= len(records):
            return records[int(choice) - 1]
        print("Invalid selection.")
        self.pause()
        return None

    def client(self) -> DnspodClient:
        return DnspodClient(self.store.load())

    @staticmethod
    def prompt_storage() -> str:
        print("\nStorage backends:")
        print("1. auto")
        print("2. keyring")
        print("3. file")
        choice = input("Select storage [auto]: ").strip()
        storage = {"1": "auto", "2": "keyring", "3": "file"}.get(choice, choice or "auto")
        if storage not in {"auto", "keyring", "file"}:
            raise DnspodToolError(f"Invalid storage backend: {storage}")
        return storage

    @staticmethod
    def optional_int(label: str, current: int | None = None) -> int | None:
        suffix = f" [{current}]" if current is not None else ""
        value = input(f"{label}{suffix}: ").strip()
        if not value:
            return current
        try:
            return int(value)
        except ValueError as exc:
            raise DnspodToolError(f"{label} must be an integer.") from exc

    @staticmethod
    def clear() -> None:
        os.system("cls" if os.name == "nt" else "clear")

    @staticmethod
    def pause() -> None:
        input("\nPress Enter to continue...")


def run_interactive(profile: str = "default") -> int:
    try:
        return TerminalUI(profile).run()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
