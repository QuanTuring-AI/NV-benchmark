# results/night1

The night-1 pre-registration ([`prediction_v5_night1.json`](prediction_v5_night1.json)), supplements 1 to 7 (`addendum_*.json`), each with its `.sha256` file, and the results of the night-1 cells: control (a), control (b) and its diagnosis, the validity gate, and C1 on the whole HotpotQA store.

## A program changed after the pre-registration

The pre-registration binds `scripts/control_query_vectors.py` by its SHA-256. The first run of control (a) stopped before producing any vector: the program took the embedding address from the environment as it is, the Blueprint's `sanitize_nim_url` appended a second `/v1`, and the embedding service answered 404. The program was changed to make the call the rag-server makes (model and address as the configuration holds them) and supplement 1 ([`addendum_1_control_a_program.json`](addendum_1_control_a_program.json)) records both digests; the pass rule did not change. The file as it was registered is kept here byte for byte: [`control_query_vectors_as_registered.py.txt`](control_query_vectors_as_registered.py.txt). The two versions differ in two places: that call, and the model and address written to the output.
