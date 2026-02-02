# mcp-remote-run

MCP Server to run code on a remote server and monitor it with CodeCarbon.

## Features

- **Code Injection**: Inject variables, dependencies, and code into Python scripts using AST manipulation
- **Temporary File Management**: Automatic cleanup of temporary files
- **Method Chaining**: Fluent API for multiple operations
- **Context Manager Support**: Use with `with` statement for automatic cleanup

## Installation

```bash
pip install mcp-remote-run
```

For development:

```bash
pip install -e ".[dev]"
```

## Usage

### Basic Variable Injection

```python
from mcp_remote_run import Injector

# Inject variables into code
with Injector(code="print(x + y)") as injector:
    injector.inject_variables({"x": 10, "y": 20})
    print(injector.get_code())
    # Output:
    # x = 10
    # y = 20
    # print(x + y)
```

### Adding Dependencies

```python
from mcp_remote_run import Injector

code = "import requests\nprint(requests.__version__)"
with Injector(code=code) as injector:
    injector.add_dependency(["requests", "numpy"])
    print(injector.get_code())
    # Output:
    # import os
    # os.system("pip install requests numpy")
    # import requests
    # print(requests.__version__)
```

### Function Injection

```python
from mcp_remote_run import Injector

code = """
def calculate():
    pass
"""

with Injector(code=code) as injector:
    new_body = "return 42"
    injector.inject_function(new_body, "calculate")
    print(injector.get_code())
    # Output:
    # def calculate():
    #     return 42
```

### Method Chaining

```python
from mcp_remote_run import Injector

code = """
def process():
    pass
"""

with Injector(code=code) as injector:
    injector.inject_variables({"x": 5}) \
            .add_dependency(["pandas"]) \
            .inject_function("return x * 2", "process")
    
    # Execute the modified code
    temp_file = injector.get_temp_file_path()
    # ... run temp_file remotely
```

### Working with Files

```python
from mcp_remote_run import Injector

# Load from file
injector = Injector(python_file_path="script.py")
injector.inject_variables({"api_key": "secret"})

# Get temporary file path for execution
temp_path = injector.get_temp_file_path()
print(f"Modified script at: {temp_path}")

# Clean up when done
injector.destroy()
```

## API Reference

### `Injector`

#### Constructor

```python
Injector(
    python_file_path: str = None,
    code: str = None,
    module: cst.Module = None,
    filename: str = "script.py"
)
```

- `python_file_path`: Path to existing Python file
- `code`: Python code as string
- `module`: Pre-parsed libcst Module object
- `filename`: Name for temporary file (when using `code` or `module`)

#### Methods

- `inject_variables(variables: Dict[str, Any])`: Inject variable assignments
- `add_dependency(packages: list)`: Add pip install commands
- `inject_function(code: str, func_name: str)`: Replace function body
- `get_code()`: Get modified code as string
- `get_temp_file_path()`: Get path to temporary file
- `get_temp_dir()`: Get path to temporary directory
- `destroy()`: Clean up temporary files

## Testing

```bash
pytest tests/ -v
```

## License

MIT License - see LICENSE file for details.
