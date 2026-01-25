---
name: verify
description: Verifies web links in a response to ensure they are valid and accessible. Checks for 404s, dead links, and error pages
parameters:
  verify_links:
    response_text:
      type: string
      description: The response text containing URLs to verify
      required: true
---

# Verify Skill

Verifies the validity of web links in the agent's final answer before presenting to the user.

## Purpose

Reviews all URLs cited in the response to ensure they are accessible and contain relevant content. Detects dead links, 404 errors, moved content, or "article not found" pages.

## When to Use

Use this skill before providing a final answer that contains web citations or sources.

## Tools

### verify_links

Checks all URLs in the provided text to confirm they are valid and accessible.

**Parameters:**
- `response_text` (string, required): The agent's response text containing URLs to verify

**Returns:**
- Verification status with details about valid/invalid links
- Modified response text with invalid links removed if any were found
- Recommendation to search again if links are invalid
