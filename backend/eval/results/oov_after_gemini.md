# SmartSME extraction accuracy

Generated 2026-11-10 21:03 - engines: google

P/R/F1 are percentages. **Exact** is the share of inputs where every scored field was right, which is the share a shopkeeper could accept without editing anything.

> Two passes on the same day. On the first, the provider answered 503 (busy) for 1 of 24 notes and the pipeline answered it with the offline parser, which the harness flags. That note (o020) was run again on its own through the same harness, and this file holds the model's own answer for every note it eventually answered. Temperature is pinned at 0, so which pass answered a note should not change the answer.

### Typed notes (n=24, synthetic)

| Engine | n | Exact | type P/R/F1 | party P/R/F1 | items P/R/F1 |
|---|---:|---:|---:|---:|---:|
| **google** | 24 |  83.3% | 100.0/100.0/100.0 |  91.7/ 91.7/ 91.7 |  91.7/ 91.7/ 91.7 |


### By variant - google

| Variant | n | Exact |
|---|---:|---:|
| hi | 6 |  83.3% |
| hi-latn | 6 | 100.0% |
| kn | 6 |  66.7% |
| kn-latn | 6 |  83.3% |


### Variants

- `en` - English
- `hi-latn` - Hindi in Latin letters
- `hi` - Hindi (Devanagari)
- `kn-latn` - Kannada in Latin letters
- `kn` - Kannada (Kannada script)
