# SmartSME extraction accuracy

Generated 2026-11-10 21:02 - engines: google

P/R/F1 are percentages. **Exact** is the share of inputs where every scored field was right, which is the share a shopkeeper could accept without editing anything.

> Two passes on the same day. On the first, the provider answered 503 (busy) for 8 of 70 notes and the pipeline answered those with the offline parser, which the harness flags. Those notes (n010, n014, n015, n024, n042, n044, n049, n060) were run again on their own through the same harness, and this file holds the model's own answer for every note it eventually answered. Temperature is pinned at 0, so which pass answered a note should not change the answer.

### Typed notes (n=70, synthetic)

| Engine | n | Exact | type P/R/F1 | party P/R/F1 | items P/R/F1 | amount P/R/F1 | category P/R/F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **google** | 70 | 100.0% | 100.0/100.0/100.0 | 100.0/100.0/100.0 | 100.0/100.0/100.0 | 100.0/100.0/100.0 | 100.0/100.0/100.0 |


### By variant - google

| Variant | n | Exact |
|---|---:|---:|
| en | 18 | 100.0% |
| hi | 11 | 100.0% |
| hi-latn | 18 | 100.0% |
| kn | 11 | 100.0% |
| kn-latn | 12 | 100.0% |


### Variants

- `en` - English
- `hi-latn` - Hindi in Latin letters
- `hi` - Hindi (Devanagari)
- `kn-latn` - Kannada in Latin letters
- `kn` - Kannada (Kannada script)
