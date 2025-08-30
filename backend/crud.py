# In-Memory CRUD Operations for Todo App

from typing import List, Optional
from models import Todo, TodoCreate

# In-memory database
todos_db: List[Todo] = []

# Auto-increment ID
current_id = 1

def get_todos() -> List[Todo]:
    return todos_db

def create_todo(todo: TodoCreate) -> Todo:
    global current_id
    new_todo = Todo(id=current_id, title=todo.title, completed=False)
    todos_db.append(new_todo)
    current_id += 1
    return new_todo

def update_todo(todo_id: int, todo: TodoCreate) -> Optional[Todo]:
    for existing_todo in todos_db:
        if existing_todo.id == todo_id:
            existing_todo.title = todo.title
            return existing_todo
    return None

def delete_todo(todo_id: int) -> bool:
    global todos_db
    initial_length = len(todos_db)
    todos_db = [todo for todo in todos_db if todo.id != todo_id]
    return len(todos_db) < initial_length