"""
Example usage of the Injector class for code injection and modification.
"""

from mcp_remote_run import Injector


def example_variable_injection():
    """Demonstrate variable injection"""
    print("=== Example 1: Variable Injection ===")
    
    code = """
def main():
    print(f"x = {x}, y = {y}")
    print(f"Sum: {x + y}")

if __name__ == "__main__":
    main()
"""
    
    with Injector(code=code) as injector:
        injector.inject_variables({"x": 10, "y": 20})
        print("Modified code:")
        print(injector.get_code())
        print()


def example_dependency_injection():
    """Demonstrate dependency injection"""
    print("=== Example 2: Dependency Injection ===")
    
    code = """
import json

def process_data():
    data = {"message": "Hello, World!"}
    print(json.dumps(data))

if __name__ == "__main__":
    process_data()
"""
    
    with Injector(code=code) as injector:
        injector.add_dependency(["requests", "pandas"])
        print("Modified code:")
        print(injector.get_code())
        print()


def example_function_injection():
    """Demonstrate function body injection"""
    print("=== Example 3: Function Injection ===")
    
    code = """
def calculate():
    pass

def main():
    result = calculate()
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
"""
    
    with Injector(code=code) as injector:
        new_body = """
a = 10
b = 20
return a * b
"""
        injector.inject_function(new_body.strip(), "calculate")
        print("Modified code:")
        print(injector.get_code())
        print()


def example_chaining():
    """Demonstrate method chaining"""
    print("=== Example 4: Method Chaining ===")
    
    code = """
def process():
    pass

if __name__ == "__main__":
    result = process()
    print(f"Result: {result}")
"""
    
    with Injector(code=code) as injector:
        injector.inject_variables({"multiplier": 5}) \
                .add_dependency(["numpy"]) \
                .inject_function("return multiplier * 10", "process")
        
        print("Modified code:")
        print(injector.get_code())
        print()


def example_complete_workflow():
    """Demonstrate a complete workflow"""
    print("=== Example 5: Complete Workflow ===")
    
    code = """
def run_experiment():
    pass

if __name__ == "__main__":
    run_experiment()
"""
    
    with Injector(code=code) as injector:
        # Step 1: Inject configuration variables
        config = {
            "epochs": 10,
            "batch_size": 32,
            "learning_rate": 0.001
        }
        injector.inject_variables(config)
        
        # Step 2: Add required dependencies
        injector.add_dependency(["codecarbon", "torch"])
        
        # Step 3: Inject experiment code
        experiment_code = """
from codecarbon import EmissionsTracker

tracker = EmissionsTracker()
tracker.start()

# Simulate training
for epoch in range(epochs):
    print(f"Epoch {epoch + 1}/{epochs}")
    print(f"Batch size: {batch_size}, LR: {learning_rate}")

tracker.stop()
print("Experiment complete!")
"""
        injector.inject_function(experiment_code.strip(), "run_experiment")
        
        print("Final modified code:")
        print(injector.get_code())
        print()
        print(f"Temporary file created at: {injector.get_temp_file_path()}")
        print("This file can be sent to a remote server for execution.")


if __name__ == "__main__":
    example_variable_injection()
    example_dependency_injection()
    example_function_injection()
    example_chaining()
    example_complete_workflow()
