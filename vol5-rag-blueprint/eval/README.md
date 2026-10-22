# The scorer of Vol.5: retrieval at two levels, the answer map, the no-answer set, paired comparison

`rag_eval.py` scores one question-answering system on one question set. It knows nothing about the system: an adapter turns a system's responses into one neutral format, and the scorer reads that, the question set, and the reference text of the source files. No question set is in this repository yet; the tests use three invented documents and five invented questions.

```bash
python rag_eval.py score --questions Q.jsonl --outputs O.jsonl --reference-dir DIR --out REPORT.json --no-overlap-list
python rag_eval.py compare --a REPORT_A.json --b REPORT_B.json --out FILE.json --metric passage_hit@5
python -m pytest -q tests          # 37 tests
```

## Formats

| | Fields |
|---|---|
| Question | `id`, `question`, `lang`, `answerable`, `gold_file_ids[]`, `gold_passage_spans[]` (`file_id`, `start`, `end`), `key_facts[]` |
| System output | `id`, `retrieved[]` (ranked; each `file_id` with `text`, or with `start` and `end`), `answer`, `refused` (or null), `cited[]` (or null), `judged_correct` (or null) |
| Reference text | `DIR/<file id>.txt`, UTF-8 |

**A gold passage is a span of the file's reference text**, not a chunk id: the offsets count characters after NFKC normalisation with all white space removed (`normalize()`; `span_of()` makes a span from a quotation). Two systems that cut the same file into different chunks are then scored against the same thing. A retrieved passage given as text is placed in the reference text in two steps and no third: as given, or after the same normalisation on both sides. A passage found neither way is "not located" and can hit nothing: nothing approximate counts as a hit. The reference text of a file is the text taken from the issuer's own file, not from a rendition of it.

## What a report holds

| Block | Meaning |
|---|---|
| File level, Hit@k | one of the first k retrieved passages comes from a gold file: the right document was found |
| Passage level, Hit@k | one of the first k retrieved passages **covers a gold span whole**: the answer was found |
| Passage given file | passage-level hits among the questions with a file-level hit |
| Sensitivity line | the passage level with "any overlap" in place of "covers"; printed under that name, never as the figure |
| Answer map | for answerable questions, by two gates: was a gold span among the passages given to the system, and did it answer or refuse. Four cells; "answered with the passage" is split into correct, wrong and not judged |
| No-answer set | questions the corpus cannot answer: refused or answered, and answered with citations. Reported apart, part of no other figure |
| By language | the first four blocks per language |

Every proportion carries its count and a Wilson 95% interval, and is marked when it rests on fewer than 50 questions. Correctness is a judge's verdict when the output carries one, else the mechanical check that every key fact of the question occurs in the answer; the report says which. A refusal is the output's own flag when it has one, else a pattern match on the answer (English, Chinese, Japanese).

## Gates

A report has figures only if every gate passes. Otherwise `figures` is `null` and the exit code is 3.

| Gate | Rule |
|---|---|
| no-answer set | at least 10 questions with `answerable: false` (`--min-no-answer`) |
| train/test overlap | no digest of a question is in a list of digests of items used for training or prompts; a planted digest must be found. Asked for by name (`--overlap-list`) or waived by name (`--no-overlap-list`) |
| complete | every question has exactly one output; every gold file has a reference text; every span lies inside its file and belongs to a gold file; `answerable` agrees with the gold fields |
| located | at most 5% of the passages given as text cannot be located in their file (`--max-not-located`); the report says how many were located as given, how many after normalisation, and how many not at all |

## Paired comparison

`compare` takes two reports scored on the same question file (same SHA-256) whose gates passed: the four counts of the paired table, the difference with a 95% interval, the exact McNemar test, and the smallest imbalance of discordant pairs the test could have detected at that number of pairs. A p above 0.05 reads "no difference could be measured with these questions".

## The adapter for the RAG Blueprint

`blueprint_adapter.py` turns the answers of the NVIDIA RAG Blueprint's RAG server (v2.6.2) into the scorer's output records. What the server returns about its sources, read from its response classes (`src/nvidia_rag/rag_server/response_generator.py`, lines 143 to 246 at tag `v2.6.2`):

| Field of the server's answer | In the scorer's record |
|---|---|
| `citations.results[]`, in the server's order (the passages it gave to the model; the first stream event carries them) | `retrieved[]`, in that order |
| `.document_name` (the file's base name) | `file_id`, without the extension |
| `.content` (the chunk's text; a base64 image for image, table and chart chunks, whose text is in `.metadata.description`) | `text` |
| `.document_type`, `.score`, `.metadata.page_number` | kept beside the passage (`type`, `score`, `page`); not used by the scorer |
| `.document_id` (empty), character offsets (none) | not available: a passage is identified by its file and its text, which the scorer locates |
| which passages the answer used | not returned: `cited` is null |
| a sign for "no answer" | none: `refused` is null and the scorer's pattern decides |

## Tests

`tests/test_rag_eval.py`: 33 tests on three invented documents (English, Chinese, Japanese) and five invented questions, two of them without an answer. A mutation run with 57 single changes to the rules (the cover rule, the Wilson interval, each gate, each cell of the answer map, the paired test, the exit codes) left none undetected; the first pass left three, which showed three assertions that could not fail, since added. `tests/test_blueprint_adapter.py`: 4 tests of the adapter on invented records.

## What it does not do

It does not call a system, does not judge an answer's wording (it takes a verdict or checks key facts), and writes no question, answer or passage text into a report: ids, counts, digests.
