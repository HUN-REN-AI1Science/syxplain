---
description: How to add or modify environment variables
---

# Managing Environment Variables

When introducing a new configuration option that requires an environment variable:

1.  **Update `.env.example`**:
    Add the variable to `.env.example` with a placeholder value or a default comment.
    ```bash
    NEW_VAR=placeholder_value # Description
    ```

2.  **Update `.env`**:
    If doing work in the user's active environment, ensure the `.env` file is also updated so the application works locally.

3.  **Update `README.md`** (CRITICAL):
    You **MUST** document the new variable in the `README.md` file under the `## Web Application > ### Environment Variables` section.
    - Categorize it correctly (Required vs Optional).
    - Provide a clear description and default value if applicable.

    Example format for `README.md`:
    ```markdown
    - `NEW_VAR`: Description of what this does. Default: `value`.
    ```
