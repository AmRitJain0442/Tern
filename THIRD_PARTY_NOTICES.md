# Third-party components

Tern's original code and documentation use the [MIT License](LICENSE). Dependencies and downloaded model files retain their own licenses; Tern does not relicense them. No model weights or third-party runtime source are vendored in this Git repository.

| Component | Source and pinned revision | License |
|---|---|---|
| Laya-MLX runtime | [mizorewww/laya-mlx](https://github.com/mizorewww/laya-mlx/tree/0a859518634112655cb97c745dbf04f5191aaf13), `0a859518634112655cb97c745dbf04f5191aaf13` | [Apache-2.0](https://github.com/mizorewww/laya-mlx/blob/0a859518634112655cb97c745dbf04f5191aaf13/LICENSE) |
| Laya-MLX checkpoint | [aac6fef/laya-mlx](https://huggingface.co/aac6fef/laya-mlx/tree/20aed815fc6acde75733882e7ec0e3f28aeb9717), `20aed815fc6acde75733882e7ec0e3f28aeb9717` | [Apache-2.0](https://huggingface.co/aac6fef/laya-mlx/blob/20aed815fc6acde75733882e7ec0e3f28aeb9717/LICENSE) |
| Original Laya model and implementation | [Convai Innovations](https://huggingface.co/convaiinnovations/laya) and [Laya contributors](https://github.com/NandhaKishorM/laya) | See the checkpoint's upstream notices |
| MLX | [ml-explore/mlx](https://github.com/ml-explore/mlx), version pinned in `uv.lock` | [MIT](https://github.com/ml-explore/mlx/blob/main/LICENSE) |

Both download paths retain the checkpoint's `LICENSE`, `NOTICE` and `manifest.json`. Keep those files with the model when redistributing a downloaded snapshot or an image containing it. Installed Python distributions also supply their own license metadata. `uv.lock` records exact runtime dependency versions and origins; CUDA components carry NVIDIA's separate terms.

OpenRouter and other hosted providers are separate services with their own terms, model licenses and usage charges. Configuring a compatible endpoint does not grant rights to its models or guarantee availability.

Tern's bird and wordmarks were generated with an image-generation tool; terminal screenshots come from the project's synthetic demonstration or local configuration checks. Their provenance is documented in [the brand guide](docs/branding.md). Third-party names identify integrations and do not imply endorsement.
