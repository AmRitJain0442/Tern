# Model Router Lab

Research and experiments for using Laya typed decision models to select LLMs under quality, latency, and cost constraints.

This project distinguishes a **routing proposal** from a measured prediction that a particular LLM will succeed. Laya's confidence is not automatically downstream answer quality.

## Initial direction

1. Enforce capability, context, and privacy constraints before model inference.
2. Start with two model tiers and one short Laya question.
3. Measure Laya against static, random, heuristic, and learned routing baselines.
4. Use a held-out quality/cost evaluation before enabling cheaper model decisions.
5. Benchmark Linux MLX CPU portability for GCP; retain upstream PyTorch as a comparison.

Research and decisions are recorded in [docs/research.md](docs/research.md). Published upstream timings are not measurements of this deployment.

Work is in progress. No downstream quality or cost saving is established yet.
