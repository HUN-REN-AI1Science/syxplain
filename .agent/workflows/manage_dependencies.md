---
description: How to add or update project dependencies
---

# Managing Dependencies

This project uses **Conda** as the primary environment manager. The source of truth for dependencies is `syxplain_environment.yml`.

## Adding a Dependency

1.  **Check availability**: Determine if the package is available on `conda-forge` or `defaults`.
2.  **Update `syxplain_environment.yml`**:
    *   If available on Conda: Add to the `dependencies` list.
    *   If ONLY available on PyPI: Add to the `dependencies -> pip` list.
3.  **Apply changes**:
    Run the following command to update the environment:
    ```bash
    // turbo
    conda env update --file syxplain_environment.yml --prune
    ```
4.  **Update `requirements.txt`** (Optional but recommended for non-conda deployments):
    If the package was added to pip dependencies, add it to `requirements.txt` as well to keep it in sync for Docker/Systemd builds that don't use Conda.

**DO NOT** rely solely on `pip install <package>` or modifying `requirements.txt` alone. Always update `syxplain_environment.yml`.
