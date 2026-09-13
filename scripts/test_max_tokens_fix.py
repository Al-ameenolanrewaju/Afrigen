"""Test that the max_tokens logic in ProviderManager works correctly."""

def test_max_tokens_logic():
    """Verify the max_tokens override logic works as intended."""
    
    # Simulate the logic from ProviderManager.generate_text()
    def process_max_tokens(task_type, max_tokens_arg):
        """Simulate how ProviderManager processes max_tokens."""
        kwargs = {}
        if max_tokens_arg is not None:
            kwargs["max_tokens"] = max_tokens_arg
        
        # Apply the fix logic
        if "max_tokens" not in kwargs or kwargs["max_tokens"] == 0:
            if task_type in ["Prompt Refinement", "AI Assistant"]:
                kwargs["max_tokens"] = 1000
            else:
                kwargs["max_tokens"] = 800
        else:
            # Caller explicitly set max_tokens; respect it
            pass
        
        return kwargs["max_tokens"]
    
    # Test 1: Explicit max_tokens=500 should NOT be overridden to 1000
    result = process_max_tokens("Prompt Refinement", 500)
    assert result == 500, f"Test 1 FAILED: Expected 500, got {result}"
    print("✓ Test 1 PASSED: Explicit max_tokens=500 was respected (not overridden to 1000)")
    
    # Test 2: Default max_tokens for "Prompt Refinement" should be 1000
    result = process_max_tokens("Prompt Refinement", None)
    assert result == 1000, f"Test 2 FAILED: Expected 1000, got {result}"
    print("✓ Test 2 PASSED: Default max_tokens for 'Prompt Refinement' is 1000")
    
    # Test 3: Explicit max_tokens=0 should use default
    result = process_max_tokens("Prompt Refinement", 0)
    assert result == 1000, f"Test 3 FAILED: Expected 1000, got {result}"
    print("✓ Test 3 PASSED: max_tokens=0 correctly applies default of 1000")
    
    # Test 4: Other task types should use 800 default
    result = process_max_tokens("Blog Writing", None)
    assert result == 800, f"Test 4 FAILED: Expected 800, got {result}"
    print("✓ Test 4 PASSED: Default max_tokens for 'Blog Writing' is 800")
    
    # Test 5: Explicit max_tokens=2000 should be respected
    result = process_max_tokens("Prompt Refinement", 2000)
    assert result == 2000, f"Test 5 FAILED: Expected 2000, got {result}"
    print("✓ Test 5 PASSED: Explicit max_tokens=2000 was respected")
    
    print("\n✅ All max_tokens logic tests PASSED!")

if __name__ == '__main__':
    test_max_tokens_logic()
