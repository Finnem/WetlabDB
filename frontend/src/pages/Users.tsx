import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import type { User } from "../types";

export default function Users() {
  const [users, setUsers] = useState<User[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [admin, setAdmin] = useState(false);
  const [kind, setKind] = useState<"student" | "employee">("student");
  const [editUser, setEditUser] = useState<User | null>(null);
  const [editPassword, setEditPassword] = useState("");
  const [editAdmin, setEditAdmin] = useState(false);
  const [editKind, setEditKind] = useState<"student" | "employee">("student");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    setUsers(await api.users());
  }

  useEffect(() => {
    refresh().catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    if (!editUser) return;
    setEditPassword("");
    setEditAdmin(editUser.admin);
    setEditKind(editUser.kind === "employee" ? "employee" : "student");
  }, [editUser]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      await api.createUser(username, password, admin, kind);
      setUsername("");
      setPassword("");
      setAdmin(false);
      setKind("student");
      setMessage("User created");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create user");
    }
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editUser) return;
    setError("");
    setMessage("");
    try {
      const patch: { password?: string; admin?: boolean; kind?: "student" | "employee" } = {
        admin: editAdmin,
      };
      if (editPassword.trim()) patch.password = editPassword;
      if (!editAdmin) patch.kind = editKind;
      await api.updateUser(editUser.username, patch);
      setEditUser(null);
      setMessage(`Updated ${editUser.username}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update user");
    }
  }

  async function removeUser(target: User) {
    if (!window.confirm(`Delete user "${target.username}"? This cannot be undone.`)) return;
    setError("");
    setMessage("");
    try {
      await api.deleteUser(target.username);
      if (editUser?.username === target.username) setEditUser(null);
      setMessage(`Deleted ${target.username}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete user");
    }
  }

  return (
    <div className="search-page">
      <div className="panel">
        <h2>Users</h2>
        {error && <p className="error">{error}</p>}
        {message && <p className="ok">{message}</p>}
        <table>
          <thead>
            <tr>
              <th>Username</th>
              <th>Admin</th>
              <th>Kind</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.username}>
                <td>{u.username}</td>
                <td>{u.admin ? "yes" : "no"}</td>
                <td>{u.admin ? "employee" : u.kind ?? "student"}</td>
                <td>
                  <button type="button" className="secondary" onClick={() => setEditUser(u)}>
                    Edit
                  </button>{" "}
                  <button type="button" className="secondary" onClick={() => removeUser(u)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {editUser && (
          <form className="form" onSubmit={saveEdit} style={{ marginTop: "1rem", maxWidth: "24rem" }}>
            <h3>Edit {editUser.username}</h3>
            <input
              placeholder="New password (leave blank to keep)"
              type="password"
              value={editPassword}
              onChange={(e) => setEditPassword(e.target.value)}
            />
            <label>
              <input type="checkbox" checked={editAdmin} onChange={(e) => setEditAdmin(e.target.checked)} /> Admin
            </label>
            {!editAdmin && (
              <label>
                Account kind
                <select value={editKind} onChange={(e) => setEditKind(e.target.value as "student" | "employee")}>
                  <option value="student">Student</option>
                  <option value="employee">Employee</option>
                </select>
              </label>
            )}
            <button type="submit">Save changes</button>{" "}
            <button type="button" className="secondary" onClick={() => setEditUser(null)}>
              Cancel
            </button>
          </form>
        )}

        <form className="form" onSubmit={submit} style={{ marginTop: "1rem", maxWidth: "24rem" }}>
          <h3>Create user</h3>
          <input placeholder="username" value={username} onChange={(e) => setUsername(e.target.value)} />
          <input
            placeholder="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <label>
            <input type="checkbox" checked={admin} onChange={(e) => setAdmin(e.target.checked)} /> Admin
          </label>
          {!admin && (
            <label>
              Account kind
              <select value={kind} onChange={(e) => setKind(e.target.value as "student" | "employee")}>
                <option value="student">Student</option>
                <option value="employee">Employee</option>
              </select>
            </label>
          )}
          <button type="submit">Create user</button>
        </form>
      </div>
    </div>
  );
}
