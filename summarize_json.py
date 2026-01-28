#!/usr/bin/env python3
"""
JSON Structure Summarizer
Analyzes large JSON files and provides a compact structural summary.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set


def get_json_structure(data: Any, max_depth: int = 5, current_depth: int = 0) -> Dict:
    """
    Recursively analyze JSON structure.
    
    Returns a summary with:
    - type: data type
    - keys: for objects
    - length: for arrays
    - sample: for primitives
    - structure: for nested data
    """
    if current_depth >= max_depth:
        return {"type": type(data).__name__, "note": "max depth reached"}
    
    if isinstance(data, dict):
        result = {
            "type": "object",
            "keys": list(data.keys()),
            "key_count": len(data.keys())
        }
        
        # Sample structure of values
        if data:
            first_key = list(data.keys())[0]
            result["value_structure"] = get_json_structure(data[first_key], max_depth, current_depth + 1)
        
        return result
    
    elif isinstance(data, list):
        result = {
            "type": "array",
            "length": len(data)
        }
        
        # Sample structure of first item
        if data:
            result["item_structure"] = get_json_structure(data[0], max_depth, current_depth + 1)
        
        return result
    
    elif isinstance(data, str):
        return {
            "type": "string",
            "sample_length": len(data),
            "preview": data[:100] if len(data) > 100 else data
        }
    
    elif isinstance(data, (int, float)):
        return {
            "type": type(data).__name__,
            "sample": data
        }
    
    elif isinstance(data, bool):
        return {
            "type": "boolean",
            "sample": data
        }
    
    elif data is None:
        return {
            "type": "null"
        }
    
    else:
        return {
            "type": type(data).__name__
        }


def analyze_json_file(filepath: str) -> Dict:
    """Analyze a JSON file and return structural summary."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    # Get file size
    file_size = Path(filepath).stat().st_size
    
    # Get structure
    structure = get_json_structure(data)
    
    # Build summary
    summary = {
        "file": filepath,
        "file_size_bytes": file_size,
        "file_size_mb": round(file_size / 1024 / 1024, 2),
        "structure": structure
    }
    
    # If it's an array of objects, analyze all unique keys
    if isinstance(data, list) and data and isinstance(data[0], dict):
        all_keys = set()
        for item in data:
            if isinstance(item, dict):
                all_keys.update(item.keys())
        
        summary["array_info"] = {
            "total_items": len(data),
            "all_keys_in_items": sorted(all_keys),
            "unique_key_count": len(all_keys)
        }
    
    # If it's a dict with "data" key (common API pattern)
    if isinstance(data, dict) and "data" in data:
        data_content = data["data"]
        if isinstance(data_content, list):
            summary["api_pattern"] = {
                "type": "paginated_list",
                "item_count": len(data_content),
                "data_structure": get_json_structure(data_content)
            }
    
    return summary


def main():
    if len(sys.argv) < 2:
        print("Usage: python summarize_json.py <json_file>")
        print("\nExample: python summarize_json.py /tmp/models.json")
        sys.exit(1)
    
    filepath = sys.argv[1]
    
    if not Path(filepath).exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    
    print("Analyzing JSON file...")
    summary = analyze_json_file(filepath)
    
    print("\n" + "=" * 80)
    print("JSON STRUCTURE SUMMARY")
    print("=" * 80)
    print(json.dumps(summary, indent=2))
    
    print("\n" + "=" * 80)
    print("HUMAN-READABLE SUMMARY")
    print("=" * 80)
    
    print(f"\nFile: {summary['file']}")
    print(f"Size: {summary['file_size_mb']} MB ({summary['file_size_bytes']:,} bytes)")
    
    structure = summary['structure']
    print(f"\nTop-level type: {structure['type']}")
    
    if structure['type'] == 'object':
        print(f"Keys ({structure['key_count']}): {', '.join(structure['keys'][:10])}")
        if structure['key_count'] > 10:
            print(f"  ... and {structure['key_count'] - 10} more")
    
    if 'array_info' in summary:
        print(f"\nArray contains {summary['array_info']['total_items']} items")
        print(f"Unique keys across all items ({summary['array_info']['unique_key_count']}):")
        for key in summary['array_info']['all_keys_in_items'][:20]:
            print(f"  - {key}")
        if summary['array_info']['unique_key_count'] > 20:
            print(f"  ... and {summary['array_info']['unique_key_count'] - 20} more")
    
    if 'api_pattern' in summary:
        print(f"\nDetected API pattern: {summary['api_pattern']['type']}")
        print(f"Data items: {summary['api_pattern']['item_count']}")


if __name__ == "__main__":
    main()
