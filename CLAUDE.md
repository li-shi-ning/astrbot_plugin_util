# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This AstrBot plugin provides a small collection of utility behaviors:
- AIOCQHTTP poke response handling
- Message emoji reactions for specific keywords
- Debug and inspection commands under `/lishi`
- TTS helper commands
- Post-processing for LLM responses

## Structure

```text
main.py       # Plugin entrypoint and all handlers
core/
  Filter.py   # Custom event filter for poke events
```

## Notes

- AIOCQHTTP-specific handlers should keep `@filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)`.
- Keep new comments in English.
- Preserve the existing command surface unless the task explicitly asks to change it.
