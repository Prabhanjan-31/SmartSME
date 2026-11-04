# SmartSME extraction accuracy

Generated 2026-11-04 20:34 - engines: heuristic, google

P/R/F1 are percentages. **Exact** is the share of inputs where every scored field was right, which is the share a shopkeeper could accept without editing anything.

### Typed notes (n=24, synthetic)

| Engine | n | Exact | type P/R/F1 | party P/R/F1 | items P/R/F1 |
|---|---:|---:|---:|---:|---:|
| **heuristic** | 24 |  20.8% |  95.8/ 95.8/ 95.8 |  78.9/ 62.5/ 69.8 |  54.2/ 54.2/ 54.2 |
| **google** | 24 |  45.8% | 100.0/100.0/100.0 |  87.5/ 87.5/ 87.5 |  54.2/ 54.2/ 54.2 |

> **google: 1 of 24 examples were produced by a different engine** (provider unavailable, so the pipeline degraded as designed). Those rows are not a measurement of google.


### By variant - heuristic

| Variant | n | Exact |
|---|---:|---:|
| hi | 6 |  16.7% |
| hi-latn | 6 |  50.0% |
| kn | 6 |   0.0% |
| kn-latn | 6 |  16.7% |


### By variant - google

| Variant | n | Exact |
|---|---:|---:|
| hi | 6 |  33.3% |
| hi-latn | 6 |  66.7% |
| kn | 6 |  33.3% |
| kn-latn | 6 |  50.0% |


### Variants

- `en` - English
- `hi-latn` - Hindi in Latin letters
- `hi` - Hindi (Devanagari)
- `kn-latn` - Kannada in Latin letters
- `kn` - Kannada (Kannada script)
