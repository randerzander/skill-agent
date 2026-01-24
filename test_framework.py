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
    assert len(metadata) >= 1, "Expected at least 1 skill"
    # Find greet skill in metadata
    greet_skill = next((s for s in metadata if s['name'] == 'greet'), None)
    assert greet_skill is not None, "Expected greet skill in metadata"
    assert 'description' in greet_skill, "Expected description in metadata"
    print("✓ Skill metadata correct")
    
    # Check XML generation
    xml = loader.get_skills_xml()
    assert '<available_skills>' in xml, "Expected XML format"
    assert '<name>greet</name>' in xml, "Expected greet skill in XML"
    print("✓ Skills XML format correct")
    
    return loader

def test_skill_activation(loader):
    """Test skill activation (progressive disclosure)"""
    print("\nTesting skill activation...")
    
    # Initially, content should not be loaded
    skill = loader.skills['greet']
    assert not skill['content_loaded'], "Content should not be loaded initially"
    print("✓ Progressive disclosure: content not loaded at startup")
    
    # Activate skill
    content = loader.activate_skill('greet')
    assert content is not None, "Failed to activate skill"
    assert '---' in content, "Expected YAML frontmatter"
    assert 'name: greet' in content, "Expected name in frontmatter"
    assert '# Greet Skill' in content, "Expected markdown content"
    print("✓ Skill activated and full content loaded")
    
    # Check that content is now marked as loaded
    assert skill['content_loaded'], "Content should be marked as loaded"
    print("✓ Progressive disclosure: content loaded on activation")

def test_skill_execution(loader):
    """Test skill execution"""
    print("\nTesting skill execution...")
    
    # Test greet script with name
    result = loader.execute_skill_script('greet', 'greet', {'name': 'TestUser'})
    assert 'result' in result, "Expected result key"
    assert 'TestUser' in result['result'], "Expected name in greeting"
    print(f"✓ Greet with name: {result['result'][:80]}...")
    
    # Test greet script without name
    result = loader.execute_skill_script('greet', 'greet', {})
    assert 'result' in result, "Expected result key"
    print(f"✓ Greet without name: {result['result'][:80]}...")
    
    # Test non-existent skill
    result = loader.execute_skill_script('nonexistent', 'test', {})
    assert 'error' in result, "Expected error for non-existent skill"
    print(f"✓ Non-existent skill error handling: {result['error']}")

def test_skill_tools(loader):
    """Test skill tools generation"""
    print("\nTesting skill tools...")
    
    # Test getting scripts
    scripts = loader.get_skill_scripts('greet')
    assert len(scripts) > 0, "Expected at least one script"
    assert scripts[0]['name'] == 'greet', "Expected greet script"
    print(f"✓ Found {len(scripts)} script(s) for greet skill")
    
    # Test tool generation
    tools = loader.get_skill_tools('greet')
    assert len(tools) > 0, "Expected at least one tool"
    assert tools[0]['type'] == 'function', "Expected function type"
    assert 'greet' == tools[0]['function']['name'], "Expected greet function name"
    print(f"✓ Generated {len(tools)} tool(s) for greet skill")
    print(f"✓ Tool name: {tools[0]['function']['name']}")

def main():
    """Run all tests"""
    print("=" * 60)
    print("Agent Skills Framework - Test Suite")
    print("=" * 60)
    
    try:
        loader = test_skill_loader()
        test_skill_activation(loader)
        test_skill_execution(loader)
        test_skill_tools(loader)
        
        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
if __name__ == "__main__":
    exit(main())
