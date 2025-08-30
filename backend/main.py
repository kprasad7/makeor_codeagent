from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

# In-memory storage
todos_db = []
next_id = 1

class Todo(BaseModel):
    id: int
    title: str
    completed: bool

class TodoCreate(BaseModel):
    title: str
    completed: bool = False

class TodoUpdate(BaseModel):
    title: Optional[str] = None
    completed: Optional[bool] = None

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/todos", response_model=List[Todo])
async def get_todos():
    return todos_db

@app.post("/todos", response_model=Todo, status_code=status.HTTP_201_CREATED)
async def create_todo(todo: TodoCreate):
    if not todo.title.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Title cannot be empty"
        )
    global next_id
    new_todo = Todo(id=next_id, title=todo.title, completed=todo.completed)
    todos_db.append(new_todo)
    next_id += 1
    return new_todo

@app.put("/todos/{todo_id}", response_model=Todo)
async def update_todo(todo_id: int, update: TodoUpdate):
    for todo in todos_db:
        if todo.id == todo_id:
            if update.title is not None:
                if not update.title.strip():
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Title cannot be empty"
                    )
                todo.title = update.title
            if update.completed is not None:
                todo.completed = update.completed
            return todo
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")

@app.delete("/todos/{todo_id}")
async def delete_todo(todo_id: int):
    for index, todo in enumerate(todos_db):
        if todo.id == todo_id:
            todos_db.pop(index)
            return {"status": "deleted"}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")