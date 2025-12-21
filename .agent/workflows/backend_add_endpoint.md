---
description: Guide for adding new API endpoints to the backend
---

# Backend: Add New API Endpoint

This workflow outlines the steps to add a new API endpoint to the Syxplain backend, following the layered architecture.

## 1. Define Data Schemas (Pydantic)
If the endpoint accepts or returns structured data, define Pydantic models.
- **Location**: `backend/api/schemas.py` (or inside the specific router file if specific to that domain).
- **Naming**: Use `Request` and `Response` suffixes (e.g., `AnalysisRequest`, `AnalysisResponse`).

## 2. Implement Business Logic (Service Layer)
Business logic should reside in services, not routers.
- **Location**: `backend/services/`
- **Pattern**:
  - Create or update a service class/module (e.g., `RunService`, `AuthService`).
  - Use dependency injection for settings or repositories.
  - Return Pydantic models or clean dictionaries.
  - Raise `backend.core.exceptions` (e.g., `NotFoundException`) for errors.

## 3. Create/Update Router
- **Location**: `backend/api/routers/`
- **Pattern**:
  - Use `APIRouter`.
  - Inject services using `Depends`.
  - Define proper HTTP methods and status codes.
  - Use `response_model` for output validation.

```python
from fastapi import APIRouter, Depends
from backend.services.my_service import MyService

router = APIRouter()

@router.post("/items", response_model=ItemResponse)
def create_item(item: ItemRequest, service: MyService = Depends()):
    return service.create_item(item)
```

## 4. Register Router (if new)
- **Location**: `backend/main.py`
- **Action**: Add `app.include_router(new_router, prefix="/api/new", tags=["New"])`.
- **Note**: Pay attention to registration order if paths overlap (specific before parameterized).

## 5. Security & Auth
- If the endpoint requires authentication, use `get_current_user` dependency.
- **Location**: `backend/api/deps.py` (or `backend/core/security.py`).
