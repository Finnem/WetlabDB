import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";

export default function Users() {
  const [users, setUsers] = useState<{ username: string; admin: boolean }[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [admin, setAdmin] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    setUsers(await api.users());
  }

  useEffect(() => {
    refresh().catch((err) => setError(String(err)));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      await api.createUser(username, password, admin);
      setUsername("");
      setPassword("");
      setAdmin(false);
      setMessage("User created");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create user");
    }
  }

  return (
    <div className="search-page">
      <div className="panel">
        <h2>Users</h2>
        <table>
          <thead>
            <tr>
              <th>Username</th>
              <th>Admin</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.username}>
                <td>{u.username}</td>
                <td>{u.admin ? "yes" : "no"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <form className="form" onSubmit={submit} style={{ marginTop: "1rem", maxWidth: "24rem" }}>
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
          {error && <p className="error">{error}</p>}
          {message && <p className="ok">{message}</p>}
          <button type="submit">Create user</button>
        </form>
      </div>
    </div>
  );
}
