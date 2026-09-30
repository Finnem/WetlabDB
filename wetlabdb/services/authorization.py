"""Collection-level access control (student / employee / admin)."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from typing import Literal, Protocol

from wetlabdb.services.auth import META_DATABASE, User
from wetlabdb.services.catalog import CatalogError, CatalogService, is_hidden_database
from wetlabdb.services.catalog_names import validate_catalog_name
from wetlabdb.storage.base import CollectionProto, StorageClientProto

CollectionCapability = Literal["none", "viewer", "editor"]
UserKind = Literal["student", "employee"]
Visibility = Literal[
    "owner_only",
    "employees",
    "students",
    "employees_and_students",
    "custom",
]

POLICIES_COLLECTION = "collection_access_policies"
LOCAL_POLICIES_RELATIVE = os.path.join(".wetlabdb", "collection_policies.json")


class AuthorizationError(ValueError):
    pass


@dataclass
class CollectionAccessPolicy:
    database: str
    collection: str
    owner: str | None = None
    visibility: Visibility = "employees_and_students"
    custom_users: list[str] | None = None
    student_access: CollectionCapability = "viewer"
    employee_access: CollectionCapability = "editor"

    def __post_init__(self) -> None:
        self.custom_users = list(self.custom_users or [])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, row: dict) -> "CollectionAccessPolicy":
        return cls(
            database=str(row.get("database") or ""),
            collection=str(row.get("collection") or ""),
            owner=(str(row["owner"]).strip() if row.get("owner") else None),
            visibility=str(row.get("visibility") or "employees_and_students"),  # type: ignore[arg-type]
            custom_users=[str(u) for u in (row.get("custom_users") or []) if str(u).strip()],
            student_access=str(row.get("student_access") or "viewer"),  # type: ignore[arg-type]
            employee_access=str(row.get("employee_access") or "editor"),  # type: ignore[arg-type]
        )


def default_policy(database: str, collection: str, *, owner: str | None = None) -> CollectionAccessPolicy:
    """Bootstrap policy: students read, employees edit, everyone in lab sees collection."""
    return CollectionAccessPolicy(
        database=database,
        collection=collection,
        owner=owner,
        visibility="employees_and_students",
        student_access="viewer",
        employee_access="editor",
    )


class PolicyStore(Protocol):
    def get(self, database: str, collection: str) -> CollectionAccessPolicy | None: ...

    def list_all(self) -> list[CollectionAccessPolicy]: ...

    def upsert(self, policy: CollectionAccessPolicy) -> None: ...


class JsonPolicyStore:
    def __init__(self, data_dir: str) -> None:
        self._path = os.path.join(data_dir, LOCAL_POLICIES_RELATIVE)
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        if not os.path.exists(self._path):
            return []
        try:
            with open(self._path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def _save(self, rows: list[dict]) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2)
        os.replace(tmp, self._path)

    def get(self, database: str, collection: str) -> CollectionAccessPolicy | None:
        key = (database, collection)
        for row in self._load():
            if (row.get("database"), row.get("collection")) == key:
                return CollectionAccessPolicy.from_dict(row)
        return None

    def list_all(self) -> list[CollectionAccessPolicy]:
        return [CollectionAccessPolicy.from_dict(r) for r in self._load()]

    def upsert(self, policy: CollectionAccessPolicy) -> None:
        with self._lock:
            rows = self._load()
            payload = policy.to_dict()
            replaced = False
            for index, row in enumerate(rows):
                if (row.get("database"), row.get("collection")) == (
                    policy.database,
                    policy.collection,
                ):
                    rows[index] = payload
                    replaced = True
                    break
            if not replaced:
                rows.append(payload)
            self._save(rows)


class MongoPolicyStore:
    def __init__(self, client: StorageClientProto) -> None:
        self._coll: CollectionProto = client[META_DATABASE][POLICIES_COLLECTION]

    def get(self, database: str, collection: str) -> CollectionAccessPolicy | None:
        row = self._coll.find_one({"database": database, "collection": collection})
        return CollectionAccessPolicy.from_dict(row) if row else None

    def list_all(self) -> list[CollectionAccessPolicy]:
        return [CollectionAccessPolicy.from_dict(r) for r in self._coll.find()]

    def upsert(self, policy: CollectionAccessPolicy) -> None:
        payload = policy.to_dict()
        existing = self._coll.find_one(
            {"database": policy.database, "collection": policy.collection}
        )
        if existing:
            self._coll.update_one(
                {"database": policy.database, "collection": policy.collection},
                {"$set": payload},
            )
        else:
            self._coll.insert_one(payload)


class AuthorizationService:
    def __init__(self, store: PolicyStore, catalog: CatalogService) -> None:
        self._store = store
        self._catalog = catalog

    @staticmethod
    def user_kind(user: User) -> UserKind:
        if user.admin:
            return "employee"
        kind = getattr(user, "kind", "student") or "student"
        return "employee" if kind == "employee" else "student"

    @staticmethod
    def can_open_permissions_ui(user: User) -> bool:
        return bool(user.admin) or AuthorizationService.user_kind(user) == "employee"

    def policy_for(self, database: str, collection: str) -> CollectionAccessPolicy:
        database = validate_catalog_name(database, kind="database")
        collection = validate_catalog_name(collection, kind="collection")
        found = self._store.get(database, collection)
        if found is not None:
            return found
        return default_policy(database, collection)

    def effective_capability(self, user: User, database: str, collection: str) -> CollectionCapability:
        if user.admin:
            return "editor"
        database = validate_catalog_name(database, kind="database")
        collection = validate_catalog_name(collection, kind="collection")
        policy = self.policy_for(database, collection)
        kind = self.user_kind(user)

        if policy.visibility == "owner_only":
            if policy.owner and user.username == policy.owner:
                return "editor"
            return "none"

        if policy.owner and user.username == policy.owner:
            return "editor"

        if policy.visibility == "custom":
            if user.username in (policy.custom_users or []):
                return policy.employee_access if kind == "employee" else policy.student_access
            return "none"

        in_audience = False
        if policy.visibility == "employees" and kind == "employee":
            in_audience = True
        elif policy.visibility == "students" and kind == "student":
            in_audience = True
        elif policy.visibility == "employees_and_students":
            in_audience = True

        if not in_audience:
            return "none"

        cap = policy.employee_access if kind == "employee" else policy.student_access
        return cap if cap in ("viewer", "editor") else "none"

    def can_view(self, user: User, database: str, collection: str) -> bool:
        return self.effective_capability(user, database, collection) in ("viewer", "editor")

    def can_edit(self, user: User, database: str, collection: str) -> bool:
        return self.effective_capability(user, database, collection) == "editor"

    def can_manage_policy(self, user: User, database: str, collection: str) -> bool:
        if user.admin:
            return True
        if self.user_kind(user) != "employee":
            return False
        if not self.can_edit(user, database, collection):
            return False
        policy = self.policy_for(database, collection)
        if policy.visibility == "owner_only" and policy.owner and policy.owner != user.username:
            return False
        return True

    def list_accessible_databases(self, user: User) -> list[str]:
        if user.admin:
            return self._catalog.list_databases()
        names: set[str] = set()
        for db in self._catalog.list_databases():
            try:
                for coll in self._catalog.list_collections(db):
                    if self.can_view(user, db, coll):
                        names.add(db)
                        break
            except Exception:
                continue
        return sorted(names)

    def list_accessible_collections(self, user: User, database: str) -> list[str]:
        if is_hidden_database(database):
            raise CatalogError(f"Database '{database}' is not available")
        if user.admin:
            return self._catalog.list_collections(database)
        return sorted(
            name
            for name in self._catalog.list_collections(database)
            if self.can_view(user, database, name)
        )

    def list_policies_for_ui(self, user: User) -> list[CollectionAccessPolicy]:
        if user.admin:
            return self._store.list_all() or self._all_default_policies()
        policies: list[CollectionAccessPolicy] = []
        for database in self._catalog.list_databases():
            for collection in self._catalog.list_collections(database):
                if self.can_manage_policy(user, database, collection):
                    policies.append(self.policy_for(database, collection))
        return policies

    def _all_default_policies(self) -> list[CollectionAccessPolicy]:
        out: list[CollectionAccessPolicy] = []
        for database in self._catalog.list_databases():
            for collection in self._catalog.list_collections(database):
                out.append(self.policy_for(database, collection))
        return out

    def ensure_default_policy(self, database: str, collection: str) -> None:
        """Persist bootstrap policy when none exists (startup / new collection)."""
        database = validate_catalog_name(database, kind="database")
        collection = validate_catalog_name(collection, kind="collection")
        if self._store.get(database, collection) is None:
            self._store.upsert(default_policy(database, collection))

    def set_policy(self, user: User, policy: CollectionAccessPolicy) -> CollectionAccessPolicy:
        if not self.can_manage_policy(user, policy.database, policy.collection):
            raise AuthorizationError("Not allowed to change access policy for this collection")
        validate_catalog_name(policy.database, kind="database")
        validate_catalog_name(policy.collection, kind="collection")
        if policy.visibility == "owner_only" and not policy.owner:
            policy.owner = user.username if self.user_kind(user) == "employee" else policy.owner
        self._store.upsert(policy)
        return policy


def policy_store_for(*, is_local: bool, data_dir: str, client: StorageClientProto) -> PolicyStore:
    if is_local:
        return JsonPolicyStore(data_dir)
    return MongoPolicyStore(client)


__all__ = [
    "AuthorizationError",
    "AuthorizationService",
    "CollectionAccessPolicy",
    "CollectionCapability",
    "Visibility",
    "default_policy",
    "policy_store_for",
]
