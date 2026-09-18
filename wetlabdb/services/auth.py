"""Application-level user accounts (not MongoDB credentials)."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Protocol

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from wetlabdb.storage.base import CollectionProto, StorageClientProto

_HASHER = PasswordHasher()

META_DATABASE = "wetlabdb_meta"
USERS_COLLECTION = "users"
LOCAL_USERS_RELATIVE = os.path.join(".wetlabdb", "users.json")


class AuthError(ValueError):
    """Invalid auth operation (duplicate user, empty username, ...)."""


@dataclass
class User:
    """A WetlabDB application user. ``password_hash`` is never sent to clients."""

    username: str
    password_hash: str
    admin: bool = False

    def public_dict(self) -> dict:
        return {"username": self.username, "admin": self.admin}


class UserStore(Protocol):
    def list_users(self) -> list[User]: ...

    def get(self, username: str) -> User | None: ...

    def upsert(self, user: User) -> None: ...


class JsonUserStore:
    """``{data_dir}/.wetlabdb/users.json`` for serverless mode."""

    def __init__(self, data_dir: str) -> None:
        self.path = os.path.join(data_dir, LOCAL_USERS_RELATIVE)
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def _save(self, rows: list[dict]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)
        os.replace(tmp, self.path)

    def list_users(self) -> list[User]:
        with self._lock:
            return [_row_to_user(r) for r in self._load() if r.get("username")]

    def get(self, username: str) -> User | None:
        username = username.strip()
        for user in self.list_users():
            if user.username == username:
                return user
        return None

    def upsert(self, user: User) -> None:
        with self._lock:
            rows = self._load()
            replaced = False
            for i, row in enumerate(rows):
                if row.get("username") == user.username:
                    rows[i] = _user_to_row(user)
                    replaced = True
                    break
            if not replaced:
                rows.append(_user_to_row(user))
            self._save(rows)


class MongoUserStore:
    """``wetlabdb_meta.users`` on the shared Mongo backend."""

    def __init__(self, client: StorageClientProto) -> None:
        self._coll: CollectionProto = client[META_DATABASE][USERS_COLLECTION]

    def list_users(self) -> list[User]:
        return [_row_to_user(r) for r in self._coll.find() if r.get("username")]

    def get(self, username: str) -> User | None:
        row = self._coll.find_one({"username": username.strip()})
        return _row_to_user(row) if row else None

    def upsert(self, user: User) -> None:
        existing = self._coll.find_one({"username": user.username})
        payload = _user_to_row(user)
        if existing is not None:
            self._coll.update_one(
                {"username": user.username},
                {"$set": payload},
            )
        else:
            self._coll.insert_one(payload)


def _row_to_user(row: dict) -> User:
    return User(
        username=str(row.get("username") or ""),
        password_hash=str(row.get("password_hash") or ""),
        admin=bool(row.get("admin")),
    )


def _user_to_row(user: User) -> dict:
    return {
        "username": user.username,
        "password_hash": user.password_hash,
        "admin": bool(user.admin),
    }


class AuthService:
    """Verify / create / list application users."""

    def __init__(self, store: UserStore) -> None:
        self._store = store

    @classmethod
    def json_store(cls, data_dir: str) -> "AuthService":
        return cls(JsonUserStore(data_dir))

    @classmethod
    def mongo_store(cls, client: StorageClientProto) -> "AuthService":
        return cls(MongoUserStore(client))

    def list_users(self) -> list[User]:
        return self._store.list_users()

    def get(self, username: str) -> User | None:
        if not username:
            return None
        return self._store.get(username)

    def verify(self, username: str, password: str) -> User | None:
        user = self.get(username or "")
        if user is None or not user.password_hash:
            return None
        try:
            _HASHER.verify(user.password_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return None
        return user

    def bootstrap(self, username: str, password: str) -> User | None:
        """Create the first admin if the store is empty. Never overwrites."""
        if self.list_users():
            return None
        if not username or not password:
            return None
        return self.create_user(username, password, admin=True)

    def create_user(self, username: str, password: str, *, admin: bool = False) -> User:
        username = (username or "").strip()
        if not username:
            raise AuthError("Username is required")
        if not password:
            raise AuthError("Password is required")
        if self.get(username) is not None:
            raise AuthError(f"User '{username}' already exists")
        user = User(
            username=username,
            password_hash=_HASHER.hash(password),
            admin=bool(admin),
        )
        self._store.upsert(user)
        return user

    def update_user(
        self,
        username: str,
        *,
        password: str | None = None,
        admin: bool | None = None,
    ) -> User:
        user = self.get(username)
        if user is None:
            raise AuthError(f"User '{username}' not found")
        if password:
            user.password_hash = _HASHER.hash(password)
        if admin is not None:
            user.admin = bool(admin)
        self._store.upsert(user)
        return user


__all__ = [
    "AuthError",
    "AuthService",
    "JsonUserStore",
    "META_DATABASE",
    "MongoUserStore",
    "User",
]
