"""Parity: collection access policies."""

from __future__ import annotations


def test_student_cannot_list_policies(user_client):
    assert user_client.get("/api/access/collection-policies").status_code == 403


def test_employee_lists_policies(employee_client):
    response = employee_client.get("/api/access/collection-policies")
    assert response.status_code == 200
    policies = response.json()["policies"]
    assert any(p["collection"] == "Compounds" for p in policies)


def test_employee_can_put_policy(employee_client):
    response = employee_client.put(
        "/api/databases/WetlabDB/collections/Compounds/access-policy",
        json={
            "visibility": "employees_and_students",
            "student_access": "viewer",
            "employee_access": "editor",
            "custom_users": [],
        },
    )
    assert response.status_code == 200
    assert response.json()["student_access"] == "viewer"
