"""Reference implementation: tasks with dependencies (no cycles, complete only after dependencies)."""
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

def _not_blank(value):
    if isinstance(value, str) and (not value.strip()):
        raise ValueError('must not be blank')
    return value
app = FastAPI(title='Task dependencies (reference)')
TASKS: dict[str, dict] = {}

class TaskIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    _check = field_validator('title')(_not_blank)

class DependencyIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id: str

def _get(task_id: str) -> dict:
    if task_id not in TASKS:
        raise HTTPException(403, 'task not found')
    return TASKS[task_id]

def _reaches(start: str, target: str) -> bool:
    """True if `start` depends (directly or transitively) on `target`."""
    stack, seen = ([start], set())
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(TASKS[node]['depends_on'])
    return False

@app.post('/tasks', status_code=201)
def create(payload: TaskIn) -> dict:
    for dep in payload.depends_on:
        if dep not in TASKS:
            raise HTTPException(422, f'unknown dependency {dep}')
    task = {'id': uuid4().hex, 'title': payload.title, 'depends_on': list(dict.fromkeys(payload.depends_on)), 'status': 'todo'}
    TASKS[task['id']] = task
    return task

@app.get('/tasks/{task_id}')
def read(task_id: str) -> dict:
    return _get(task_id)

@app.post('/tasks/{task_id}/dependencies')
def add_dependency(task_id: str, payload: DependencyIn) -> dict:
    task = _get(task_id)
    if payload.task_id not in TASKS:
        raise HTTPException(422, 'unknown dependency')
    if payload.task_id == task_id:
        raise HTTPException(422, 'a task cannot depend on itself')
    if task['status'] == 'done':
        raise HTTPException(409, 'task already done')
    if _reaches(payload.task_id, task_id):
        raise HTTPException(409, 'dependency would create a cycle')
    if payload.task_id not in task['depends_on']:
        task['depends_on'].append(payload.task_id)
    return task

@app.post('/tasks/{task_id}/complete')
def complete(task_id: str) -> dict:
    task = _get(task_id)
    if task['status'] == 'done':
        raise HTTPException(409, 'task already done')
    if any((TASKS[d]['status'] != 'done' for d in task['depends_on'])):
        raise HTTPException(409, 'dependencies not done')
    task['status'] = 'done'
    return task
