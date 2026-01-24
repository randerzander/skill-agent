---
name: web
description: Search the web and read content from URLs. Search returns results with titles and links. Read extracts text from URLs
parameters:
  search:
    query:
      type: string
      description: The search query
      required: true
  read_url:
    url:
      type: string
      description: The URL to fetch content from
      required: true
---

# Web Skill

Provides web research capabilities through two tools: search the web for information, and read content from URLs.

## Search
Searches multiple engines and returns a list of results with titles, URLs, and descriptions.

## Read URL
Fetches and extracts content from URLs. Automatically handles different formats: web pages, YouTube videos, Wikipedia articles, PDFs, etc
