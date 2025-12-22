---
description: How to update Python __init__.py files when adding new modules
---

# Update Python `__init__.py` Files

When adding new Python modules or functions to the backend, update the corresponding `__init__.py` files to maintain clean re-exports.

## Steps

1. **Add new module/function** to a package directory (e.g., `backend/utils/`, `backend/services/`)

2. **Open the `__init__.py`** in that directory

3. **Add the import**:
   ```python
   from backend.package_name.new_module import new_function
   ```

4. **Update `__all__`** list:
   ```python
   __all__ = ["existing_item", "new_function"]
   ```

## Current Package Locations

- `backend/utils/__init__.py` - Utility functions
- `backend/services/__init__.py` - Service classes
- `backend/repositories/__init__.py` - Repository classes
- `backend/core/__init__.py` - Core config and exceptions
- `backend/api/__init__.py` - API routers

## Example

Adding `my_helper` to utils:

```python
# backend/utils/__init__.py
from backend.utils.validation import parse_uuid
from backend.utils.json_utils import clean_and_fix_json_string
from backend.utils.my_module import my_helper  # NEW

__all__ = ["parse_uuid", "clean_and_fix_json_string", "my_helper"]  # UPDATED
```
