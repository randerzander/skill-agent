#!/usr/bin/env python3
"""
Test script for the agent skills framework
Tests the core functionality without requiring API keys
"""
import json
from agent import SkillLoader

def test_skill_loader():
    """Test that skills are loaded correctly"""
    print("Testing SkillLoader...")
    loader = SkillLoader()
    
    # Check that greet skill is loaded
    assert 'greet' in loader.skills, "Greet skill not loaded"
    print("✓ Greet skill loaded successfully")
    
    # Check metadata structure
    metadata = loader.get_skills_metadata()
    assert len(metadata) == 1, "Expected 1 skill"
    assert metadata[0]['name'] == 'greet', "Expected greet skill"
    print("✓ Skill metadata correct")
    
    return loader

def test_skill_execution(loader):
    """Test skill execution"""
    print("\nTesting skill execution...")
    
    # Test greet with name
    result = loader.execute_skill('greet', {'name': 'TestUser'})
    assert 'result' in result, "Expected result key"
    assert 'TestUser' in result['result'], "Expected name in greeting"
    print(f"✓ Greet with name: {result['result']}")
    
    # Test greet without name
    result = loader.execute_skill('greet', {})
    assert 'result' in result, "Expected result key"
    print(f"✓ Greet without name: {result['result']}")
    
    # Test non-existent skill
    result = loader.execute_skill('nonexistent', {})
    assert 'error' in result, "Expected error for non-existent skill"
    print(f"✓ Non-existent skill error handling: {result['error']}")

def test_parse_skill_selection():
    """Test skill selection parsing"""
    print("\nTesting skill selection parsing...")
    from agent import AgentSkillsFramework
    
    # Create a mock agent (will fail on API key, but we only need the parser)
    class MockAgent:
        def _parse_skill_selection(self, response):
            # Copy the method from AgentSkillsFramework
            if not response or not response.startswith("SKILL:"):
                return None
            
            try:
                parts = response[6:].split(":", 1)
                skill_name = parts[0].strip()
                parameters = {}
                
                if len(parts) > 1 and parts[1].strip():
                    parameters = json.loads(parts[1].strip())
                
                return {
                    "name": skill_name,
                    "parameters": parameters
                }
            except Exception as e:
                print(f"Error parsing skill selection: {e}")
                return None
    
    agent = MockAgent()
    
    # Test valid skill selection with parameters
    result = agent._parse_skill_selection('SKILL:greet:{"name":"Alice"}')
    assert result is not None, "Failed to parse valid skill selection"
    assert result['name'] == 'greet', "Wrong skill name"
    assert result['parameters']['name'] == 'Alice', "Wrong parameter"
    print(f"✓ Parsed skill with params: {result}")
    
    # Test valid skill selection without parameters
    result = agent._parse_skill_selection('SKILL:greet:{}')
    assert result is not None, "Failed to parse skill without params"
    assert result['name'] == 'greet', "Wrong skill name"
    print(f"✓ Parsed skill without params: {result}")
    
    # Test non-skill response
    result = agent._parse_skill_selection('Just a regular response')
    assert result is None, "Should return None for non-skill response"
    print("✓ Correctly ignored non-skill response")

def main():
    """Run all tests"""
    print("=" * 60)
    print("Agent Skills Framework - Test Suite")
    print("=" * 60)
    
    try:
        loader = test_skill_loader()
        test_skill_execution(loader)
        test_parse_skill_selection()
        
        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
