import pytest
import os
import tempfile
from mcp_remote_run import Injector


def test_injector_with_code_string():
    """Test creating Injector with code string"""
    code = "x = 1\nprint(x)"
    injector = Injector(code=code)
    
    assert injector.get_code() == code
    assert os.path.exists(injector.get_temp_file_path())
    
    temp_dir = injector.get_temp_dir()
    injector.destroy()
    assert not os.path.exists(temp_dir)


def test_injector_with_file():
    """Test creating Injector with a file"""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("x = 1\nprint(x)")
        temp_file = f.name
    
    try:
        injector = Injector(python_file_path=temp_file)
        assert "x = 1" in injector.get_code()
        assert os.path.exists(injector.get_temp_file_path())
        injector.destroy()
    finally:
        os.unlink(temp_file)


def test_inject_variables():
    """Test variable injection"""
    code = "print('hello')"
    injector = Injector(code=code)
    
    injector.inject_variables({"x": 10, "y": "test"})
    
    result = injector.get_code()
    assert "x = 10" in result
    assert 'y = "test"' in result
    assert "print('hello')" in result
    
    injector.destroy()


def test_inject_variables_different_types():
    """Test variable injection with different types"""
    code = "pass"
    injector = Injector(code=code)
    
    injector.inject_variables({
        "int_var": 42,
        "float_var": 3.14,
        "str_var": "hello",
        "bool_var": True,
        "none_var": None
    })
    
    result = injector.get_code()
    assert "int_var = 42" in result
    assert "float_var = 3.14" in result
    assert 'str_var = "hello"' in result
    assert "bool_var = True" in result
    assert "none_var = None" in result
    
    injector.destroy()


def test_add_dependency_no_os_import():
    """Test adding dependencies when os is not imported"""
    code = "print('hello')"
    injector = Injector(code=code)
    
    injector.add_dependency(["requests", "numpy"])
    
    result = injector.get_code()
    assert "import os" in result
    assert 'os.system("pip install requests numpy")' in result
    assert "print('hello')" in result
    
    injector.destroy()


def test_add_dependency_with_os_import():
    """Test adding dependencies when os is already imported"""
    code = "import os\nprint('hello')"
    injector = Injector(code=code)
    
    injector.add_dependency(["pandas"])
    
    result = injector.get_code()
    # Should only have one import os
    assert result.count("import os") == 1
    assert 'os.system("pip install pandas")' in result
    
    injector.destroy()


def test_add_dependency_empty_list():
    """Test adding dependencies with empty list"""
    code = "print('hello')"
    injector = Injector(code=code)
    
    injector.add_dependency([])
    
    result = injector.get_code()
    # Should not add any dependency-related code
    assert result == code
    
    injector.destroy()


def test_inject_function():
    """Test injecting code into function"""
    code = """def my_function():
    pass
"""
    injector = Injector(code=code)
    
    new_code = "x = 10\nreturn x"
    injector.inject_function(new_code, "my_function")
    
    result = injector.get_code()
    assert "def my_function():" in result
    assert "x = 10" in result
    assert "return x" in result
    assert "pass" not in result
    
    injector.destroy()


def test_method_chaining():
    """Test chaining multiple operations"""
    code = """def my_function():
    pass
"""
    injector = Injector(code=code)
    
    injector.inject_variables({"x": 5}).add_dependency(["requests"]).inject_function("return x * 2", "my_function")
    
    result = injector.get_code()
    assert "x = 5" in result
    assert "import os" in result
    assert 'os.system("pip install requests")' in result
    assert "return x * 2" in result
    
    injector.destroy()


def test_context_manager():
    """Test using Injector as context manager"""
    code = "x = 1"
    
    with Injector(code=code) as injector:
        temp_dir = injector.get_temp_dir()
        assert os.path.exists(temp_dir)
    
    # After exiting context, temp dir should be cleaned up
    assert not os.path.exists(temp_dir)


def test_get_temp_file_path():
    """Test getting temporary file path"""
    code = "x = 1"
    injector = Injector(code=code, filename="test.py")
    
    temp_file = injector.get_temp_file_path()
    assert os.path.exists(temp_file)
    assert temp_file.endswith("test.py")
    
    injector.destroy()


def test_invalid_multiple_sources():
    """Test that providing multiple sources raises error"""
    with pytest.raises(ValueError, match="Cannot provide multiple sources"):
        Injector(code="x = 1", python_file_path="test.py")


def test_invalid_no_source():
    """Test that providing no source raises error"""
    with pytest.raises(ValueError, match="Must provide either"):
        Injector()


def test_temp_file_modification():
    """Test that modifications are saved to temp file"""
    code = "x = 1"
    injector = Injector(code=code)
    
    injector.inject_variables({"y": 2})
    
    # Read the temp file directly
    with open(injector.get_temp_file_path(), 'r') as f:
        file_content = f.read()
    
    assert "y = 2" in file_content
    assert "x = 1" in file_content
    
    injector.destroy()
