# P102 · follow-up arms, each on its own line with its own interval

| Arm | Judge | Track · group | Detection (Wilson 95%) | False alarm (Wilson 95%) | No verdict | c=1 p50 / p99, ms | c=16 verdicts/s | Output tokens p50 |
|---|---|---|---|---|---|---|---|---|
| LG3 | Llama Guard 3 8B | input · aegis2 | 66.4% [63.5, 69.2] (690/1039) | 6.7% [5.3, 8.6] (60/889) | 0.0% | 51 / 106 | 98.1 | 3 |
| LG3 | Llama Guard 3 8B | input · vol1 | 93.3% [70.2, 98.8] (14/15) | 0.0% [0.0, 11.4] (0/30) | 0.0% | 51 / 106 | 98.1 | 3 |
| LG3 | Llama Guard 3 8B | input · xstest | 82.0% [76.1, 86.7] (164/200) | 2.8% [1.4, 5.7] (7/250) | 0.0% | 51 / 106 | 98.1 | 3 |
| LG3 | Llama Guard 3 8B | input · xstest_harmless_only | - | 2.8% [1.4, 5.7] (7/250) | 0.0% | 51 / 106 | 98.1 | 3 |
| LG3 | Llama Guard 3 8B | input · aegis2_needs_caution_only | - | 8.8% [5.2, 14.4] (13/148) | 0.0% | 51 / 106 | 98.1 | 3 |
| LG3 | Llama Guard 3 8B | output · aegis2 | 51.3% [46.3, 56.2] (202/394) | 4.1% [2.5, 6.4] (17/419) | 0.0% | 52 / 101 | 64.8 | 3 |
