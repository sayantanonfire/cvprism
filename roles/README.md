# roles

Starter role profiles ship inside the package at [`cvprism/data/roles/`](../cvprism/data/roles/): `academic`, `industry-ds`, `applied-ai`, `hydrodynamics`, `geospatial`. Schema: [docs/SCHEMA.md](../docs/SCHEMA.md#-role-profile).

To customise one, create `roles/<id>.yaml` **in your vault**. A vault role overrides a starter of the same id. Use `extends:` to inherit everything and change only what differs:

```yaml
v: 1
id: ml-engineer
title: Machine Learning Engineer
extends: applied-ai
vocabulary: [PyTorch, distributed training, inference optimisation, Kubernetes]
limits: {pages: 1}
```

Then run `cvprism build --role ml-engineer`. No code needed.
