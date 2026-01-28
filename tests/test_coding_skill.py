#!/usr/bin/env python3
"""
Test script for the coding skill
"""
import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.coding.scripts.tools import write_code, run_code

def test_write_code():
    """Test writing code to file"""
    print("=" * 80)
    print("TEST 1: write_code")
    print("=" * 80)
    
    code = """#!/usr/bin/env python3
import json
from pathlib import Path

# Read all query files from scratch directory
scratch_dir = Path("scratch")
query_files = list(scratch_dir.glob("query_*.jsonl"))

print(f"Found {len(query_files)} query files:")
for qf in query_files:
    print(f"  - {qf.name}")
    
# Read first query file if exists
if query_files:
    with open(query_files[0]) as f:
        for line in f:
            data = json.loads(line)
            print(f"\\nResult: {data.get('title', 'N/A')}")
            print(f"URL: {data.get('href', 'N/A')}")
"""
    
    result = write_code("test_reader.py", code)
    result_data = json.loads(result)
    
    if "result" in result_data:
        print("✓ write_code succeeded:")
        print(f"  Status: {result_data['result']['status']}")
        print(f"  File: {result_data['result']['filepath']}")
        return True
    else:
        print("✗ write_code failed:")
        print(f"  Error: {result_data.get('error')}")
        return False

def test_run_code():
    """Test running code"""
    print("\n" + "=" * 80)
    print("TEST 2: run_code")
    print("=" * 80)
    
    # First write a simple test script
    test_code = """
import sys
print("Hello from the coding skill!")
print(f"Python version: {sys.version}")
print("Test completed successfully!")
"""
    
    write_result = write_code("hello.py", test_code)
    write_data = json.loads(write_result)
    
    if "error" in write_data:
        print("✗ Failed to write test code")
        return False
    
    # Now run it
    result = run_code("hello.py")
    result_data = json.loads(result)
    
    if "result" in result_data:
        print("✓ run_code succeeded:")
        print(f"  Status: {result_data['result']['status']}")
        print(f"  Exit Code: {result_data['result']['exit_code']}")
        print(f"\nOutput:\n{result_data['result']['output']}")
        return True
    else:
        print("✗ run_code failed:")
        print(f"  Error: {result_data.get('error')}")
        return False

def test_scratch_access():
    """Test accessing scratch directory from code"""
    print("\n" + "=" * 80)
    print("TEST 3: Access scratch directory")
    print("=" * 80)
    
    # Create a test file in scratch
    from pathlib import Path
    scratch_dir = Path("scratch")
    scratch_dir.mkdir(exist_ok=True)
    
    test_file = scratch_dir / "test_data.txt"
    with open(test_file, 'w') as f:
        f.write("Test data from scratch directory\n")
    
    # Write code to read it
    reader_code = """
from pathlib import Path

scratch_file = Path("scratch/test_data.txt")
if scratch_file.exists():
    with open(scratch_file) as f:
        content = f.read()
    print(f"Successfully read: {content.strip()}")
else:
    print("File not found!")
"""
    
    write_code("read_scratch.py", reader_code)
    result = run_code("read_scratch.py")
    result_data = json.loads(result)
    
    if "result" in result_data and "Successfully read" in result_data['result']['output']:
        print("✓ Scratch access test passed:")
        print(f"  Output: {result_data['result']['output'].strip()}")
        
        # Cleanup
        test_file.unlink()
        return True
    else:
        print("✗ Scratch access test failed")
        if "error" in result_data:
            print(f"  Error: {result_data['error']}")
        return False

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("CODING SKILL TEST SUITE")
    print("=" * 80 + "\n")
    
    results = []
    
    results.append(("write_code", test_write_code()))
    results.append(("run_code", test_run_code()))
    results.append(("scratch_access", test_scratch_access()))
    
    print("\n" + "=" * 80)
    print("TEST RESULTS")
    print("=" * 80)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)
