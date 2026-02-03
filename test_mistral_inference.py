from __future__ import annotations

import argparse
import asyncio
import os
import sys

import mistralai


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a quick Mistral SDK chat completion to confirm connectivity."
    )
    parser.add_argument(
        "--model",
        default="mistral-vibe-cli-latest",
        help="Model name to use (default: mistral-vibe-cli-latest).",
    )
    parser.add_argument(
        "--prompt",
        default="Say hello in one short sentence.",
        help="User prompt to send.",
    )
    return parser.parse_args()


async def _run() -> int:
    args = _parse_args()

    if not (api_key := os.getenv("MISTRAL_API_KEY")):
        print("Missing MISTRAL_API_KEY in environment.", file=sys.stderr)
        return 2

    client = mistralai.Mistral(api_key=api_key, server_url="https://api.mistral.ai")
    try:
        response = await client.chat.complete_async(
            model=args.model,
            messages=[
                mistralai.SystemMessage(
                    role="system",
                    content="You are a concise test assistant.",
                ),
                mistralai.UserMessage(role="user", content=args.prompt),
            ],
            temperature=0.2,
        )
    finally:
        await client.__aexit__(None, None, None)

    content = response.choices[0].message.content
    print(content if content else "<empty response>")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
