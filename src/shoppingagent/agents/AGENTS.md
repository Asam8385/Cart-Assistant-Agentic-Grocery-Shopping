# Shopping agent package instructions

This project was built with the microsoft-foundry skill. Before working on or answering questions about Foundry agents, read the microsoft-foundry skill first.

- Keep the pipeline explicit: extraction LLM, deterministic tool loop, then response LLM.
- Every tool invocation must produce a stream event that can be displayed by the frontend.
- Never allow an LLM to invent catalogue identifiers, price, stock, or availability.
- Use Qdrant for candidate retrieval and MySQL `store_offers` for live availability confirmation.
- Crossed-out and uncertain image items must not be searched automatically.
