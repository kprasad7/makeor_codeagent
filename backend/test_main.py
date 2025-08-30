import pytest
from fastapi.testclient import TestClient
from main import app, todos_db

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_create_todo():
    response = client.post("/todos", json={"title": "Test Todo", "completed": False})
    assert response.status_code == 201
    assert response.json() == {"id": 1, "title": "Test Todo", "completed": False}

def test_create_todo_empty_title():
    response = client.post("/todos", json={"title": "", "completed": False})
    assert response.status_code == 422

def test_get_todos():
    todos_db.clear()
    client.post("/todos", json={"title": "Todo 1", "completed": False})
    client.post("/todos", json={"title": "Todo 2", "completed": True})
    response = client.get("/todos")
    assert response.status_code == 200
    assert len(response.json()) == 2

def test_update_todo():
    todos_db.clear()
    client.post("/todos", json={"title": "Original", "completed": False})
    response = client.put("/todos/1", json={"title": "Updated", "completed": True})
    assert response.status_code == 200
    assert response.json() == {"id": 1, "title": "Updated", "completed": True}

def test_update_todo_empty_title():
    todos_db.clear()
    client.post("/todos", json={"title": "Original", "completed": False})
    response = client.put("/todos/1", json={"title": "", "completed": True})
    assert response.status_code == 422

def test_update_todo_not_found():
    response = client.put("/todos/999", json={"title": "Updated", "completed": True})
    assert response.status_code == 404

def test_delete_todo():
    todos_db.clear()
    client.post("/todos", json={"title": "To Delete", "completed": False})
    response = client.delete("/todos/1")
    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}

def test_delete_todo_not_found():
    response = client.delete("/todos/999")
    assert response.status_code == 404