#!/usr/bin/env python3
"""
Test script to demonstrate the rich logging in an interactive session
Run this with: python test_interactive.py
"""

if __name__ == "__main__":
    print("\nTesting Rich Logging with Agent Skills Framework")
    print("=" * 50)
    print("\nTry these commands:")
    print("  1. 'which skills do you have' - should NOT activate greet skill")
    print("  2. 'greet Polyphemus' - should activate greet skill with rich logging")
    print("=" * 50)
    print("\nStarting agent...\n")
    
    from agent import main
    main()
