#!/usr/bin/env python3
"""QA test script for notion-mcp-remote: tests all 26 MCP tools.

Usage (on archbox):
    cd ~/notion-mcp-remote
    source .venv/bin/activate
    python qa_test.py [--token TOKEN]

If --token is not provided, extracts the latest valid token from the token store.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field

import httpx
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MCP_URL = "http://127.0.0.1:8000/mcp"
HOST_HEADER = os.environ.get("BASE_URL", "https://archbox.tail5b443a.ts.net")
# Extract just the hostname for the Host header
HOST_HEADER = HOST_HEADER.replace("https://", "").replace("http://", "")

# Known IDs for read tests
DAILY_NOTES_PAGE_ID = "2fbc2a37-9fe0-802c-8325-f620eb7f00a6"
DAILY_NOTES_DB_ID = "aea5e514-ecd7-4430-ae67-889e37887487"
DAILY_NOTES_DS_ID = "c3cccf83-9a9b-4030-a8ae-fd44ed94057c"

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


@dataclass
class TestResult:
    tool: str
    passed: bool
    detail: str = ""
    duration_ms: float = 0


@dataclass
class TestContext:
    """Holds IDs created during write tests for subsequent operations."""
    scratch_page_id: str = ""
    scratch_db_id: str = ""
    scratch_block_id: str = ""
    data_source_id: str = ""
    user_id: str = ""
    results: list[TestResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# MCP client helpers
# ---------------------------------------------------------------------------


def parse_sse_response(text: str) -> dict:
    """Parse SSE response and extract the JSON-RPC result.

    Skips empty data lines (SSE priming events) and returns the first
    valid JSON payload.
    """
    for line in text.strip().split("\n"):
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                return json.loads(payload)
    raise ValueError(f"No data line found in SSE response: {text[:200]}")


def call_tool(
    client: httpx.Client, token: str, name: str, arguments: dict | None = None
) -> dict:
    """Send MCP tools/call request, return parsed result."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }
    resp = client.post(
        MCP_URL,
        json=payload,
        headers={
            "Host": HOST_HEADER,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
        },
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"HTTP {resp.status_code}: {resp.text[:300]}"
        )

    rpc = parse_sse_response(resp.text)

    if "error" in rpc:
        raise RuntimeError(f"JSON-RPC error: {rpc['error']}")

    result = rpc.get("result", {})
    if result.get("isError"):
        content = result.get("content", [{}])
        text = content[0].get("text", "") if content else ""
        raise RuntimeError(f"Tool error: {text[:300]}")

    return result


def extract_text(result: dict) -> str:
    """Pull the text content from a tool result."""
    content = result.get("content", [])
    if content and content[0].get("type") == "text":
        return content[0]["text"]
    return json.dumps(result)


def extract_json(result: dict) -> dict:
    """Pull parsed JSON from a tool result's text content.

    Raises RuntimeError if the JSON contains a Notion API error.
    """
    text = extract_text(result)
    data = json.loads(text)
    if isinstance(data, dict) and data.get("error"):
        msg = data.get("message", "Unknown error")
        details = data.get("details", {})
        code = details.get("code", "")
        raise RuntimeError(f"Notion API error ({code}): {msg[:200]}")
    return data


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


def run_test(
    ctx: TestContext,
    client: httpx.Client,
    token: str,
    tool_name: str,
    arguments: dict | None = None,
    check: callable | None = None,
) -> dict | None:
    """Run a single tool test, record result."""
    t0 = time.monotonic()
    try:
        result = call_tool(client, token, tool_name, arguments)
        duration = (time.monotonic() - t0) * 1000

        detail = ""
        if check:
            detail = check(result)

        ctx.results.append(
            TestResult(tool_name, True, detail or "OK", duration)
        )
        print(f"  PASS  {tool_name} ({duration:.0f}ms) {detail or ''}")
        return result

    except Exception as e:
        duration = (time.monotonic() - t0) * 1000
        ctx.results.append(
            TestResult(tool_name, False, str(e)[:200], duration)
        )
        print(f"  FAIL  {tool_name} ({duration:.0f}ms) {e}")
        return None


# ---------------------------------------------------------------------------
# Test categories
# ---------------------------------------------------------------------------


def test_search(ctx: TestContext, client: httpx.Client, token: str):
    print("\n--- Search ---")
    run_test(ctx, client, token, "search", {"query": "Daily Notes"})


def test_users(ctx: TestContext, client: httpx.Client, token: str):
    print("\n--- Users ---")

    # get_self
    result = run_test(ctx, client, token, "get_self")
    if result:
        data = extract_json(result)
        ctx.user_id = data.get("id", "")

    # get_users
    run_test(ctx, client, token, "get_users")

    # get_user (use self ID)
    if ctx.user_id:
        run_test(ctx, client, token, "get_user", {"user_id": ctx.user_id})
    else:
        print("  SKIP  get_user (no user_id from get_self)")


def test_pages_read(ctx: TestContext, client: httpx.Client, token: str):
    print("\n--- Pages (read) ---")

    # get_page
    result = run_test(
        ctx, client, token, "get_page", {"page_id": DAILY_NOTES_PAGE_ID}
    )

    # get_page_property_item
    if result:
        data = extract_json(result)
        props = data.get("properties", {})
        if props:
            first_prop_id = next(iter(props.values())).get("id", "title")
            run_test(
                ctx,
                client,
                token,
                "get_page_property_item",
                {
                    "page_id": DAILY_NOTES_PAGE_ID,
                    "property_id": first_prop_id,
                },
            )
        else:
            run_test(
                ctx,
                client,
                token,
                "get_page_property_item",
                {
                    "page_id": DAILY_NOTES_PAGE_ID,
                    "property_id": "title",
                },
            )


def test_databases_read(ctx: TestContext, client: httpx.Client, token: str):
    print("\n--- Databases (read) ---")

    # get_database
    result = run_test(
        ctx, client, token, "get_database", {"database_id": DAILY_NOTES_DB_ID}
    )

    # Extract data_source_id from database response (fallback to known constant)
    if result:
        try:
            data = extract_json(result)
            data_sources = data.get("data_sources", [])
            if data_sources:
                ctx.data_source_id = data_sources[0].get("id", "")
        except RuntimeError:
            pass  # error already recorded by run_test

    if not ctx.data_source_id:
        ctx.data_source_id = DAILY_NOTES_DS_ID

    # query_database
    run_test(
        ctx,
        client,
        token,
        "query_database",
        {"database_id": DAILY_NOTES_DB_ID, "page_size": 2},
    )

    # get_data_source
    run_test(
        ctx,
        client,
        token,
        "get_data_source",
        {"data_source_id": ctx.data_source_id},
    )

    # query_data_source
    run_test(
        ctx,
        client,
        token,
        "query_data_source",
        {"data_source_id": ctx.data_source_id, "page_size": 2},
    )

    # list_data_source_templates
    run_test(
        ctx,
        client,
        token,
        "list_data_source_templates",
        {"data_source_id": ctx.data_source_id},
    )


def test_pages_write(ctx: TestContext, client: httpx.Client, token: str):
    print("\n--- Pages (write) ---")

    # create_page — scratch page under Daily Notes parent
    result = run_test(
        ctx,
        client,
        token,
        "create_page",
        {
            "parent": {"type": "page_id", "page_id": DAILY_NOTES_PAGE_ID},
            "properties": {
                "title": [
                    {
                        "type": "text",
                        "text": {"content": "[QA TEST] Scratch Page"},
                    }
                ]
            },
        },
    )
    if result:
        data = extract_json(result)
        ctx.scratch_page_id = data.get("id", "")

    if not ctx.scratch_page_id:
        print("  SKIP  update_page, archive_page (no scratch page)")
        return

    # update_page — change icon
    run_test(
        ctx,
        client,
        token,
        "update_page",
        {
            "page_id": ctx.scratch_page_id,
            "icon": {"type": "emoji", "emoji": "🧪"},
        },
    )

    # move_page — move to same parent (noop move, just tests the tool)
    run_test(
        ctx,
        client,
        token,
        "move_page",
        {
            "page_id": ctx.scratch_page_id,
            "parent": {"type": "page_id", "page_id": DAILY_NOTES_PAGE_ID},
        },
    )


def test_blocks(ctx: TestContext, client: httpx.Client, token: str):
    print("\n--- Blocks ---")

    if not ctx.scratch_page_id:
        print("  SKIP  all block tests (no scratch page)")
        return

    # append_block_children
    result = run_test(
        ctx,
        client,
        token,
        "append_block_children",
        {
            "block_id": ctx.scratch_page_id,
            "children": [
                {
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "QA test block — append_block_children"
                                },
                            }
                        ]
                    },
                },
                {
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": "Test Heading"},
                            }
                        ]
                    },
                },
            ],
        },
    )
    if result:
        data = extract_json(result)
        results = data.get("results", [])
        if results:
            ctx.scratch_block_id = results[0].get("id", "")

    # get_block_children
    run_test(
        ctx,
        client,
        token,
        "get_block_children",
        {"block_id": ctx.scratch_page_id},
    )

    # get_block
    if ctx.scratch_block_id:
        run_test(
            ctx,
            client,
            token,
            "get_block",
            {"block_id": ctx.scratch_block_id},
        )

        # update_block
        run_test(
            ctx,
            client,
            token,
            "update_block",
            {
                "block_id": ctx.scratch_block_id,
                "content": {
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "QA test block — UPDATED via update_block"
                                },
                            }
                        ]
                    }
                },
            },
        )

        # delete_block
        run_test(
            ctx,
            client,
            token,
            "delete_block",
            {"block_id": ctx.scratch_block_id},
        )
    else:
        print("  SKIP  get_block, update_block, delete_block (no block_id)")


def test_comments(ctx: TestContext, client: httpx.Client, token: str):
    print("\n--- Comments ---")

    if not ctx.scratch_page_id:
        print("  SKIP  all comment tests (no scratch page)")
        return

    # create_comment
    run_test(
        ctx,
        client,
        token,
        "create_comment",
        {
            "parent": {"page_id": ctx.scratch_page_id},
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": "QA test comment"},
                }
            ],
        },
    )

    # get_comments
    run_test(
        ctx,
        client,
        token,
        "get_comments",
        {"block_id": ctx.scratch_page_id},
    )


def test_databases_write(ctx: TestContext, client: httpx.Client, token: str):
    print("\n--- Databases (write) ---")

    # create_database — under scratch page (or Daily Notes parent)
    parent_id = ctx.scratch_page_id or DAILY_NOTES_PAGE_ID
    result = run_test(
        ctx,
        client,
        token,
        "create_database",
        {
            "parent": {"type": "page_id", "page_id": parent_id},
            "title": [
                {"type": "text", "text": {"content": "[QA TEST] Scratch DB"}}
            ],
            "is_inline": True,
        },
    )
    if result:
        data = extract_json(result)
        ctx.scratch_db_id = data.get("id", "")
        # Get data source from the new DB
        ds = data.get("data_sources", [])
        scratch_ds_id = ds[0].get("id", "") if ds else ""

    if not ctx.scratch_db_id:
        print("  SKIP  update_database, archive_database (no scratch DB)")
        return

    # update_database — change title
    run_test(
        ctx,
        client,
        token,
        "update_database",
        {
            "database_id": ctx.scratch_db_id,
            "title": [
                {
                    "type": "text",
                    "text": {"content": "[QA TEST] Scratch DB — UPDATED"},
                }
            ],
        },
    )

    # update_data_source — add a property
    if scratch_ds_id:
        run_test(
            ctx,
            client,
            token,
            "update_data_source",
            {
                "data_source_id": scratch_ds_id,
                "properties": {
                    "Status": {
                        "select": {
                            "options": [
                                {"name": "Todo", "color": "red"},
                                {"name": "Done", "color": "green"},
                            ]
                        }
                    }
                },
            },
        )
    else:
        print("  SKIP  update_data_source (no data_source_id)")

    # archive_database
    run_test(
        ctx,
        client,
        token,
        "archive_database",
        {"database_id": ctx.scratch_db_id},
    )


def test_cleanup(ctx: TestContext, client: httpx.Client, token: str):
    """Archive the scratch page to clean up."""
    print("\n--- Cleanup ---")

    if ctx.scratch_page_id:
        # archive_page — also serves as a test
        run_test(
            ctx,
            client,
            token,
            "archive_page",
            {"page_id": ctx.scratch_page_id},
        )
    else:
        print("  SKIP  archive_page (no scratch page to clean up)")


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------


def get_token_from_store() -> str:
    """Extract the latest valid bearer token from the encrypted token store."""
    from auth.storage import TokenStore

    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        print("ERROR: SESSION_SECRET not set. Pass --token or set in .env")
        sys.exit(1)

    store = TokenStore(secret=secret)
    tokens = store._data.get("access_tokens", {})

    if not tokens:
        print("ERROR: No access tokens in store. Complete OAuth flow first.")
        sys.exit(1)

    # Pick the token with the latest expiration
    now = time.time()
    valid = {t: d for t, d in tokens.items() if d.get("expires_at", 0) > now}

    if not valid:
        print("ERROR: All tokens expired. Re-authenticate via Claude.ai.")
        sys.exit(1)

    token, data = max(valid.items(), key=lambda x: x[1]["expires_at"])
    remaining = (data["expires_at"] - now) / 3600
    print(f"Using token (expires in {remaining:.1f}h)")
    return token


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="QA test all 26 MCP tools")
    parser.add_argument("--token", help="Bearer token (auto-extracts if omitted)")
    args = parser.parse_args()

    token = args.token or get_token_from_store()
    ctx = TestContext()

    print(f"MCP endpoint: {MCP_URL}")
    print(f"Host header:  {HOST_HEADER}")
    print(f"Daily Notes page: {DAILY_NOTES_PAGE_ID}")
    print(f"Daily Notes DB:   {DAILY_NOTES_DB_ID}")

    with httpx.Client(timeout=30) as client:
        # Read-only tests first
        test_search(ctx, client, token)
        test_users(ctx, client, token)
        test_pages_read(ctx, client, token)
        test_databases_read(ctx, client, token)

        # Write tests (create scratch resources, test, clean up)
        test_pages_write(ctx, client, token)
        test_blocks(ctx, client, token)
        test_comments(ctx, client, token)
        test_databases_write(ctx, client, token)

        # Clean up scratch page
        test_cleanup(ctx, client, token)

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for r in ctx.results if r.passed)
    failed = sum(1 for r in ctx.results if not r.passed)
    total = len(ctx.results)
    print(f"RESULTS: {passed}/{total} passed, {failed} failed")
    print(f"Total time: {sum(r.duration_ms for r in ctx.results):.0f}ms")

    if failed:
        print("\nFailed tools:")
        for r in ctx.results:
            if not r.passed:
                print(f"  - {r.tool}: {r.detail}")

    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
