# How accurate the extraction actually is

Measured numbers, not impressions. The test suite proves the code does what it
was written to do; it cannot say whether reading "Anita ko 5 kilo chawal becha"
produces the *right* sale. This page is that second question.

[&larr; Back to the README](../README.md) &nbsp;·&nbsp;
Harness, data format and how to run it: [backend/eval](../backend/eval/README.md)

---

## Method in one paragraph

Every input has a **gold label**, the correct answer, written down by a person
before any system saw it. The harness runs each input through the same functions
the application uses, compares the result to its label, and counts. Per-field
precision, recall and F1; plus **exact**, the share of inputs where every field
was right, which is the share a shopkeeper could accept without editing
anything. A wrong answer costs twice, once as a miss and once as a fabrication,
because a wrong customer is worse than no customer.

Last run: 2026-11-10 for the typed notes and the unknown-word set, both
engines; 2026-09-16 for the slips, consistency and latency. Regenerate with
`python -m eval` from `backend`.

## Typed notes (n = 70)

| Engine | Exact | type F1 | party F1 | items F1 | amount F1 | category F1 |
|---|---:|---:|---:|---:|---:|---:|
| Heuristic (offline regex) | 87.1% | 100.0 | 94.8 | 93.7 | 95.2 | 100.0 |
| Gemini 3.5 Flash Lite | **100.0%** | 100.0 | **100.0** | **100.0** | **100.0** | 100.0 |

By language variant, exact-match:

| Variant | n | Heuristic | Gemini |
|---|---:|---:|---:|
| English | 18 | 66.7% | **100.0%** |
| Hindi, Latin letters | 18 | 83.3% | **100.0%** |
| Hindi, Devanagari | 11 | 100.0% | 100.0% |
| Kannada, Latin letters | 12 | 100.0% | 100.0% |
| Kannada script | 11 | 100.0% | 100.0% |

**What this says.** The offline parser is competitive on well-formed notes and
falls behind on messy ones: no verb, no capitals, typos, two items on a line,
which is where English and Hinglish lose their points. Both native scripts score
100% for both engines, but for different reasons. The model reads Hindi and
Kannada directly: its prompt names the languages, scripts and common verbs, and
the note reaches it unchanged. The offline parser only gets there because
[`app/ai/lang.py`](../backend/app/ai/lang.py) first rewrites the note into
English word order, which `heuristic_parse()` does and the model path does not.
On these notes the two engines tie, so the native-script rows cannot separate
them.

**Against the September run.** The same seventy notes scored 85.7% (items F1
91.9) for the offline parser and 97.1% (items F1 96.8) for the model on
2026-09-16. The two notes the model missed then both put two items on one line
("ramesh ko 2 chai aur 3 biscuit becha", "anita stores 5 rice 2 sugar") and
lost the second one. Both are read in full now, and the first is right for the
offline parser as well; on the second it still finds no customer. The model's
prompt also gained its [point of view](smart-input.md#point-of-view) paragraph
since then, and no note it got right in September is wrong now.

A perfect score on seventy author-written notes is the ceiling of this test,
not of the model. The set can no longer tell two good engines apart, which is
what the [unknown-word set](#words-outside-the-lexicon-n--24) below is for.

The model's row is the model's own answer for all seventy notes. On the first
pass the provider answered 503 (busy) for eight of them, the pipeline fell
back to the offline parser as designed, and the harness flagged those rows;
they were run again on their own until the model answered. Per-note results:
[`notes_after.md`](../backend/eval/results/notes_after.md) (dated 2026-11-04;
the offline parser's run of 2026-11-10 reproduced it exactly) and
[`notes_after_gemini.md`](../backend/eval/results/notes_after_gemini.md).

**What this does not say.** These notes are **synthetic**, written by the same
author as the parser. The first fifty scored 100% on the heuristic, which says
more about who wrote them than about the parser; twenty deliberately messier
ones brought it down to 85.7%, and it is 87.1% today. Numbers from
author-written data cannot tell you how the system behaves for a stranger.

## Words outside the lexicon (n = 24)

The seventy notes above use the words the system was built around. This set is
the opposite: 24 notes written to break it, six in each of four variants
(Hindi and Kannada, each in its own script and in Latin letters). Half use
verbs and grammar the offline normaliser was never taught ("de di", "le
gaye", "ಕೊಟ್ಟೆ", "bandide"). The other half name
products the lexicon has never heard of (sago, raisins, camphor, dates, ragi
flour, jowar), scored against a catalogue that stocks them
([`catalogue_oov.json`](../backend/eval/data/catalogue_oov.json)).

| Engine | Exact | type F1 | party F1 | items F1 |
|---|---:|---:|---:|---:|
| Heuristic, before the two rules below | 20.8% | 95.8 | 69.8 | 54.2 |
| Heuristic | 29.2% | 95.8 | 69.8 | 62.5 |
| Gemini 3.5 Flash Lite, before | 45.8% | 100.0 | 87.5 | 54.2 |
| Gemini 3.5 Flash Lite | **83.3%** | 100.0 | **91.7** | **91.7** |

By language variant, exact-match, as it stands now:

| Variant | n | Heuristic | Gemini |
|---|---:|---:|---:|
| Hindi, Devanagari | 6 | 16.7% | 83.3% |
| Hindi, Latin letters | 6 | 66.7% | **100.0%** |
| Kannada script | 6 | 0.0% | 66.7% |
| Kannada, Latin letters | 6 | 33.3% | 83.3% |

**What moved it.** Two rules in grounding, described under
[Words the lexicon does not know](smart-input.md#words-the-lexicon-does-not-know):

1. **A qualifier has to be honoured.** "ragi atta" used to come back as
   `Wheat Flour 10kg`, because "atta" is a known word and "ragi" was ignored: a
   wrong product, offered with confidence. Now a product must name the
   qualifier, so the note finds `Ragi Flour 1kg` or finds nothing. This helps
   both engines, and it is the whole of the offline parser's gain (two notes).
2. **The model also says what the item is in English.** "साबूदाना" matches
   nothing in an English catalogue; "sago" matches `Sago 500g`. The English
   name is tried only when the note's own word finds nothing. Only the model
   can supply it, which is why Gemini's items F1 went from 54.2 to 91.7 and
   the offline parser's did not.

**What still fails.** Four notes, for the model:

```
ಸನ್ರೈಸ್ ಹೋಲ್ಸೇಲ್ ಕಡೆಯಿಂದ ೮ ಎಣ್ಣೆ ಬಂತು          supplier left in Kannada script, not
ಎಬಿಸಿ ಸಪ್ಲೈಯರ್ಸ್ ಇಂದ ೧೫ ಕರ್ಪೂರ ಖರೀದಿಸಿದೆ       matched to the English name on file
ABC सप्लायर्स से 20 कपूर के पैकेट खरीदे           item came back as "कपूर के पैकेट",
                                              unit attached, and matched no product
Sunrise Wholesale inda 6 kilo jola kharidiside  "jola" (jowar) matched no product
```

The offline parser stays near 29%, and that is the expected result, not a bug
to chase. It still tells a sale from a purchase (type F1 95.8); what it cannot
do is name a product it has never seen or pick a customer out of grammar it
was not written for, and no rule will teach it that "साबूदाना" is sago. This
is the case for keeping a model in the loop, made with numbers.

**How to read it.** A miss here is a product or a name left unmatched on the
confirm screen for the shopkeeper to fill in, not a wrong product: the
qualifier rule exists so that an unknown word is declined and not guessed. And
the set is small and adversarial on purpose. One note is 4.2 points, and each
variant row is six notes, so the variant figures show where the system breaks,
not how often it would for a real shopkeeper.

The "before" rows are from 2026-11-04
([`oov.md`](../backend/eval/results/oov.md)). In that run one of the 24 Gemini
rows was answered by the offline parser, so read 45.8% as "about 46%". The
current rows are [`oov_after.md`](../backend/eval/results/oov_after.md) and
[`oov_after_gemini.md`](../backend/eval/results/oov_after_gemini.md); one note
hit a 503 on the model's first pass and was run again, as above.

## Handwritten order slips (n = 12, real photographs)

| Engine | Exact | party F1 | phone F1 | items F1 |
|---|---:|---:|---:|---:|
| Vision model (Gemini) | **100.0%** | 100.0 | 100.0 | 100.0 |
| OCR.space (character OCR) | 75.0% | 100.0 | 100.0 | 91.7 |

Split by whether the customer corrected something on the paper:

| Engine | Clean slips | Slips with an in-place correction |
|---|---:|---:|
| Vision model | 9 / 9 | **3 / 3** |
| OCR.space | 9 / 9 | **0 / 3** |

**This is the finding.** Both engines read the handwriting accurately: party
and phone are perfect for both, and character OCR gets every clean slip. The
entire difference is the three slips where something was struck out and
rewritten:

```
Meena      1 kg  C̶o̶f̶f̶e̶e̶  /  1 kg Coffee    read literally: 2 kg billed for 1
S. Khan    5 bags  W̶h̶e̶a̶t̶  Atta            read literally: product "Wheat Atta"
A. Sharma  4 bags  P̶r̶o̶d̶u̶c̶t̶ ̶B̶              read literally: a cancelled item ordered
```

A strikethrough is not a character, so it cannot survive character recognition.
No post-processing recovers information that never entered the text. The
failure is structural, not a tuning problem. A vision model can be *told* to
ignore cancelled text, and on all three it is.

Three of twelve slips in an **unplanned** sample carried a correction, so this
is not an edge case; correcting an order in place is just how people write on
paper. It is also the reason the vision path is tried first and the free OCR
path is labelled by name on the confirm screen, so whoever reviews a draft
knows a cancelled line could be sitting in it.

## Consistency: does the same note give the same draft?

An LLM is sampled, so identical input can produce different output. That matters
more here than in a chat: the same order typed twice must not become two
different sales.

Measured on five notes, three runs each:

| | Same draft every run |
|---|---|
| Before, at the model's default temperature | **3 / 5** |
| After pinning `temperature: 0` | **5 / 5** |

The two that varied failed in ways a shopkeeper would have noticed:

```
ಅನಿತಾಗೆ ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ    party was sometimes "ಅನಿತಾಗೆ" - the name with its
                                Kannada case-ending still attached, which then
                                matched no customer at all
anita stores 5 rice 2 sugar    items were sometimes [Rice Bag 25kg x5] and
                                sometimes [Item x1] - the whole order lost
```

Extraction is not writing: there is no value in sampling. Accuracy was unchanged
after the switch (97.1% at the time), so determinism here was free.

## Latency

| Path | Median | Notes |
|---|---|---|
| Text note → draft (Gemini) | **2.2 s** | end to end, including the catalogue match |
| Photograph → draft (Gemini vision) | **1.4 s** | 12 real slips |
| Photograph → draft (OCR.space) | **1.9 s** | includes re-encoding the image |

The p90 for text notes reads 16.8 s, but that is the *harness* rather than the
model: it retries with backoff when the free tier refuses, and those waits are
inside the measurement. A single uncontended call is ~1-2 s.

## Four bugs the evaluation found that 364 passing tests did not

1. **The expense category vocabulary was not pinned.** The regex path answered
   "Electricity", the model answered "Utilities", and the Expenses page grouped
   them as two different things. Fixed by
   [`app/ai/categories.py`](../backend/app/ai/categories.py). Worth 7 points of
   exact-match on its own: 90.0% → 97.1%.
2. **A tab between a label and its value ate the phone number.** Splitting on
   every tab was right for two items merged onto one row and wrong for
   `Ph no:⇥9443311220`.
3. **A name and a phone merged onto one line** were read as one very long
   customer name.
4. **A bug in the harness itself**: `300` and `300.0` compared unequal as text,
   so a correct extraction was reported as a failure.

The harness also caught itself being misled: on the first real run, **38 of 70
examples silently fell back to the heuristic** because the free tier stops at
about sixteen calls a minute, and every AI path here degrades rather than fails.
Without that check, the regex parser's score would have been published under
Gemini's name. Runs now report how many examples a different engine produced,
and a row with that warning is not a measurement.

## What is still missing

- **Real users.** The slips are real photographs but come from one writer, in
  good light, in neat block capitals. The notes are author-written. Neither is
  evidence about shopkeepers.
- **A second annotator.** Every gold label here was written once, by one person.
  Serious work has two people label independently and reports how often they
  agreed.
- **Latency under concurrency.** The figures above are single calls on an idle
  machine. Nobody has measured what happens when twenty shopkeepers submit a
  note in the same minute - and the binding constraint there is not this app but
  the free tier's ~15 requests a minute.
