"""
API Exorcist — autonomous discovery and safe elimination of zombie, shadow and
orphaned APIs.

Package layout
--------------
    config          runtime settings, resolved from the environment
    connectors/     six discovery sources, each a partial and imperfect witness
    ingestion/      transport: LocalBus (default), Kafka, Elasticsearch
    inventory/      multi-source correlation into a unified inventory
    engine/         classification and explanation
    evaluation/     metrics and the comparative benchmark
    dataset/        labelled dataset construction for the ML engine
    simulated_env/  the simulated estate and its ground truth

Dependency direction is one-way: connectors know nothing of ingestion, and the
engine never reaches back to a data source. `engine`, `inventory` and
`connectors` must never import `simulated_env`, which holds the answer key —
a test enforces this at the AST level.
"""

__version__ = "0.5.0"

__all__ = ["__version__"]
