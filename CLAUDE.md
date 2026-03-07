# CLAUDE.md

Coding standards and best practices for this repository.

## Environment Management

### Pixi + Conda-Forge

This project uses **pixi** as the environment manager with **conda-forge** as the primary channel.

```bash
# Install environment
pixi install
pixi run postinstall

# Run commands via pixi
pixi run python script.py
pixi run test
```

### Dependency Organization

Dependencies are organized into **features** by domain in `pixi.toml`:

```toml
# Runtime features
[feature.py_core.dependencies]        # Core utilities (attrs, arrow)
[feature.py_data_processing.dependencies]  # pandas, polars, numpy, pyarrow
[feature.py_ml.dependencies]          # pytorch, scikit-learn, transformers
[feature.py_web.dependencies]         # fastapi, streamlit, uvicorn

# Development features
[feature.py_test.dependencies]        # pytest, mypy
[feature.py_lint.dependencies]        # ruff, pre-commit
```

**Rules:**

- Prefer conda-forge packages over PyPI (`[feature.X.dependencies]`)
- Use `[feature.X.pypi-dependencies]` only when package is not on conda-forge
- Group related dependencies in semantic features
- New CLI commands should be registered as pixi tasks

### Pixi Tasks

Register reusable commands as tasks:

```toml
[tasks]
postinstall = "pip install -e ."

[feature.py_test.tasks]
test = "pytest tests/"

[feature.py_lint.tasks]
pre-commit-install = "pre-commit install"
pre-commit-run = "pre-commit run -a"
```

## Modern Python (>= 3.12)

### Syntax

```python
# Union types - use | not Union
def process(data: str | bytes | None) -> dict[str, Any]: ...

# Built-in generics - never import from typing
items: list[str]
mapping: dict[str, int]
optional: str | None

# Annotated for metadata
from typing import Annotated
count: Annotated[int, "must be positive"]

# match statements for complex branching
match event:
    case {"type": "click", "x": x, "y": y}:
        handle_click(x, y)
    case {"type": "keypress", "key": key}:
        handle_key(key)
```

### Preferred Libraries

| Category        | Library                | Notes                                            |
| --------------- | ---------------------- | ------------------------------------------------ |
| Data structures | `attrs`, `dataclasses` | attrs for complex, dataclasses for simple        |
| Paths           | `pathlib.Path`         | Never use `os.path`                              |
| CLI             | `typer` + `rich`       | Modern CLI with rich output                      |
| HTTP client     | `httpx`                | Async-first, requests-compatible                 |
| Data frames     | `polars`, `pandas`     | Polars for performance, pandas for compatibility |
| Dates           | `arrow`                | Human-friendly datetime                          |
| Logging         | `structlog`            | Structured logging                               |
| Config          | `pydantic` >= 2        | Settings and validation                          |
| Async           | `asyncio` native       | Use async/await patterns                         |

### Type Hints

```python
# Modern syntax
from collections.abc import Callable, Sequence, Mapping
from typing import Annotated, TypeAlias

# Type aliases for complex types
JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

# Annotated for CLI params
def download(
    output_dir: Annotated[Path, typer.Option("--output", "-o", help="Output directory")],
) -> None: ...
```

## Naming

Names tell a domain story, not describe implementation.

- `Tool` not `AbstractToolInterface`
- `execute()` not `executeToolWithValidation()`
- Never use temporal context: `NewAPI`, `LegacyHandler`, `OldService`
- Avoid: "new", "old", "legacy", "wrapper", "unified", implementation details

## Comments

### Module Docstring Pattern

Every Python file starts with a module docstring:

```python
"""Brief one-line description of what this file does.

Second line with additional context if needed.
"""
```

### Comment Rules

- Comments explain **what** or **why**, never implementation comparison
- No "this replaces the old X" or "unlike the legacy system"
- Do not use `---` separator comment patterns (for example, `# --- Create offer ---`)

## Testing

- All test failures are your responsibility (Broken Windows theory)
- Never delete a test because it's failing
- Fix the code or fix the test

## Debugging

1. Form a **single hypothesis**
2. Make the **smallest possible change** to test it
3. If it doesn't work, **stop and re-analyze** - don't pile on fixes

## Design

### YAGNI

- Don't add features we don't need right now
- Discuss architectural decisions before implementation
- Routine fixes don't need discussion

## Code Style

Do not hard code fall backs but raise exceptions instead. Problems in the code should be surfaced loudly.

### Formatting

- Line length: 88 (ruff default)
- Quotes: double
- Indent: spaces
- Enforced by ruff + pre-commit

### Imports

```python
# 1. Standard library
from pathlib import Path
from typing import Annotated

# 2. Third-party
import typer
from rich.console import Console

# 3. Local
from myproject.utils import get_logger
```

- Use absolute imports rooted at `sp26_gke` in this repo.
- Do not use relative imports (for example, `from .validator import ...`).

### CLI Pattern

```python
#!/usr/bin/env python3
"""Description of what this CLI does.

Additional context.
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(name="tool-name", help="Description", no_args_is_help=True)
console = Console()

@app.command()
def command(
    arg: Annotated[Path, typer.Argument(help="Input path")],
    flag: Annotated[bool, typer.Option("--flag", "-f", help="Enable feature")] = False,
) -> None:
    """Command docstring explains what it does."""
    console.print("[green]Success[/green]")

if __name__ == "__main__":
    app()
```

## Git

- Meaningful commit messages
- Atomic, focused commits
- Run `pixi run pre-commit-run` before pushing
