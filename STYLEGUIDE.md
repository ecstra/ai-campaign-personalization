# Python Style Guide & Conventions

This guide outlines the strict coding standards, formatting rules, and architectural patterns used in this codebase. The philosophy heavily favors **explicit readability, vertical formatting, strict type safety, and defensive programming**—designed for scalable systems and engine-level integrations.

## 1. Module Structure & Imports

Imports must be strictly grouped into three categories, separated by a single blank line. Do not mix standard `import x` and `from y import z` on the same line, and never chain multiple modules in a single standard import (e.g., `import os, sys` is forbidden).

**Order of Imports:**

1. Standard Library
2. Third-Party / External Dependencies
3. Internal / Local Modules

```python
# 1. Standard Library
import os
import sys
from typing import Any, Optional, Dict

# 2. Third-Party / External
import requests
from pydantic import BaseModel

# 3. Internal / Local
from .engine import CoreEngine
from .utility import FileUtility
```

## 2. Naming Conventions

* **Classes:** `PascalCase` (e.g., `ConfigUtility`, `NetworkManager`).
* **Functions & Methods:** `snake_case` (e.g., `parse_payload`, `initialize_system`).
* **Variables & Arguments:** `snake_case` (e.g., `raw_data`, `timeout_seconds`).
* **Constants:** `UPPER_SNAKE_CASE` (e.g., `DEFAULT_TIMEOUT`, `MAX_RETRIES`).

## 3. Namespacing (The Utility Class Pattern)

To keep imports clean and prevent global namespace pollution, utility functions must be grouped logically into classes as `@staticmethod`s. Do not leave functions floating at the module level unless they are the primary entry point of a script.

```python
# GOOD: Accessed via FileUtility.read_json()
class FileUtility:
    
    @staticmethod
    def read_json(file_path: str) -> dict[str, Any]:
        """Reads and parses a JSON file."""
        pass
```

## 4. Function Signatures & Vertical Stacking

Horizontal brevity is explicitly rejected in favor of vertical readability.
Function signatures with multiple arguments must be vertically stacked. Each argument gets its own line, followed by a trailing comma. The closing parenthesis `)` and the return type hint `->` must reside on their own line.

```python
class NetworkUtility:

    @staticmethod
    def fetch_user_data(
        endpoint_url: str,
        auth_token: str,
        timeout_seconds: float = 5.0,
        strict_validation: bool = False,
    ) -> dict[str, Any]:
        """
        Fetches user data from the provided API endpoint.
        """
        pass
```

## 5. Data Structures & Formatting

The vertical stacking rule extends to all complex data structures (Dictionaries, Lists, Sets). Every element must be on its own line with a trailing comma to keep git diffs clean and readable.

```python
# Vertically stacked dictionary mapping
payload = {
    "user_id": 1042,
    "session_token": auth_token,
    "preferences": {
        "dark_mode": True,
        "auto_save": False,
    },
}

# Vertically stacked list
valid_extensions = [
    ".json",
    ".yaml",
    ".toml",
]
```

## 6. Type Safety

Strict type hinting is mandatory across the entire codebase. Every function argument and return value must be explicitly typed.

```python
# Forbidden:
# def process(data):

# Required:
def process(data: dict[str, Any]) -> Optional[list[str]]:
```

## 7. Error Handling & Control Flow

* **Early Returns:** Handle base cases and validations at the top of the function to avoid deep, unreadable indentation (guard clauses).
* **Idiomatic Python Exceptions:** Use standard `try...except` blocks. Do not attempt to replicate Rust/Go-style tuple returns (e.g., `return data, err`).

```python
@staticmethod
def load_config(
    file_path: str,
) -> dict[str, Any]:
    """
    Loads configuration, returning early if the path is invalid.
    """
    # Early return guard clause
    if not os.path.exists(file_path):
        return {}

    # Standard exception handling
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config: {e}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error loading config: {e}")
```

## 8. Documentation & Comments

* **Docstrings:** Must use the `"""` format and be placed *immediately below* the function/method definition (not above it).
* **Inline Comments:** Used sparingly to explain *why* a specific block of complex logic exists, not *what* the code is doing. Maintain vertical breathing room (empty lines) around logical blocks.

***

## 9. Comprehensive Example

Putting all the rules together, a standard Python file in your project should look exactly like this:

```python
import os
import json
from typing import Any, Optional

import requests
from pydantic import ValidationError

from .logger import LogUtility
from .exceptions import APIError


class SystemConfigUtility:
    
    @staticmethod
    def sync_remote_config(
        api_url: str,
        api_key: str,
        max_retries: int = 3,
    ) -> Optional[dict[str, Any]]:
        """
        Fetches the latest remote configuration from the control server.
        Falls back to returning None if the maximum retries are exceeded.
        """
        
        if not api_url or not api_key:
            LogUtility.warning("Missing API credentials. Aborting sync.")
            return None

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "EngineBridge/1.0",
        }

        try:
            # Execute request
            response = requests.get(
                api_url,
                headers=headers,
                timeout=10.0,
            )
            response.raise_for_status()

            # Parse and validate the response payload
            raw_data = response.json()
            
            validated_config = {
                "engine_version": raw_data.get("version", "1.0.0"),
                "feature_flags": raw_data.get("flags", []),
                "is_active": bool(raw_data.get("active", False)),
            }
            
            return validated_config

        except requests.RequestException as e:
            LogUtility.error(f"Network failure during config sync: {e}")
            raise APIError(f"Failed to reach control server: {e}")
            
        except Exception as e:
            LogUtility.error(f"Fatal error during sync: {e}")
            raise RuntimeError(f"Sync routine crashed: {e}")
```
