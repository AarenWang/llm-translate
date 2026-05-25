# Sample Book

This document explains how an Agent can call a Tool Call.

## Chapter 1. Basics

Run `docker compose up -d` before opening https://example.com/docs.

See [OpenAI documentation](https://platform.openai.com/docs).

![System Architecture](./images/architecture.png)

| Term | Meaning |
|---|---|
| Agent | Runtime actor |
| Tool Call | External action |

```python
def hello(name: str) -> str:
    return f"hello {name}"
```

> Keep references like [12] unchanged.
