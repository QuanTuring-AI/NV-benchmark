### e1b · nvidia/llama-nemotron-embed-1b-v2 · query

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 110.502 | 110.5 | 8.218 | 8.574 | 9.682 | 4436 | 0 | 1.16 |  |
| 2 | 182.612 | 182.6 | 10.023 | 10.516 | 11.4 | 7330 | 0 | 1.35 |  |
| 4 | 183.396 | 183.4 | 20.775 | 21.36 | 22.253 | 7360 | 0 | 1.37 |  |
| 8 | 183.676 | 183.7 | 42.36 | 43.402 | 45.136 | 7369 | 0 | 1.43 |  |
| 16 | 182.084 | 182.1 | 86.528 | 88.089 | 91.837 | 7305 | 0 | 1.48 |  |
| 32 | 182.148 | 182.1 | 173.91 | 176.476 | 184.123 | 7308 | 0 | 1.53 | 181.969 · 184.491 |
| 64 | 181.739 | 181.7 | 349.594 | 355.489 | 375.358 | 7289 | 0 | 1.52 | 182.568 · 381.938 |

Read by the rules: {"highest_requests_per_s": 183.676, "highest_items_per_s": 183.7, "saturation_level": 2, "rate_at_one_in_flight": 110.502, "rise_from_one_to_the_highest": 1.66, "highest_level_with_p99_at_most_100_ms": 16, "highest_level_with_p99_at_most_500_ms": 64, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.92}

### e1b · nvidia/llama-nemotron-embed-1b-v2 · passage

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 9.276 | 593.7 | 103.895 | 122.15 | 158.66 | 372 | 0 | 1.05 |  |
| 2 | 12.407 | 794.0 | 157.598 | 179.846 | 203.695 | 497 | 0 | 1.1 |  |
| 4 | 12.423 | 795.1 | 318.335 | 349.839 | 367.59 | 498 | 0 | 1.11 |  |
| 8 | 12.44 | 796.2 | 639.699 | 677.412 | 693.731 | 499 | 0 | 1.12 |  |
| 16 | 12.415 | 794.6 | 1284.379 | 1328.529 | 1352.391 | 498 | 0 | 1.17 |  |
| 32 | 12.42 | 794.8 | 2564.999 | 2604.069 | 2633.628 | 498 | 0 | 1.19 | 12.384 · 2622.57 |
| 64 | 12.347 | 790.2 | 5140.965 | 5189.577 | 5226.902 | 496 | 0 | 1.14 | 12.385 · 5201.801 |

Read by the rules: {"highest_requests_per_s": 12.44, "highest_items_per_s": 796.2, "saturation_level": 2, "rate_at_one_in_flight": 9.276, "rise_from_one_to_the_highest": 1.34, "highest_level_with_p99_at_most_100_ms": null, "highest_level_with_p99_at_most_500_ms": 4, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.98}

### e300 · nvidia/llama-nemotron-embed-300m-v2 · passage

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 17.501 | 1120.1 | 54.126 | 63.871 | 87.069 | 700 | 0 | 1.14 |  |

Read by the rules: {"highest_requests_per_s": 17.501, "highest_items_per_s": 1120.1, "saturation_level": 1, "rate_at_one_in_flight": 17.501, "rise_from_one_to_the_highest": 1.0, "highest_level_with_p99_at_most_100_ms": 1, "highest_level_with_p99_at_most_500_ms": 1, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.97}

### evl · nvidia/llama-nemotron-embed-vl-1b-v2 · query

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 292.741 | 292.7 | 2.8 | 2.963 | 3.193 | 11763 | 0 | 1.38 |  |
| 2 | 418.35 | 418.4 | 4.081 | 4.314 | 4.527 | 16805 | 0 | 1.64 |  |
| 4 | 418.812 | 418.8 | 8.836 | 9.135 | 9.416 | 16832 | 0 | 1.68 |  |
| 8 | 418.758 | 418.8 | 18.255 | 18.695 | 19.392 | 16823 | 0 | 1.74 |  |
| 16 | 411.099 | 411.1 | 37.423 | 38.437 | 60.639 | 16505 | 0 | 1.85 |  |
| 32 | 417.081 | 417.1 | 75.341 | 76.926 | 78.783 | 16761 | 0 | 1.91 | 424.673 · 77.338 |
| 64 | 418.685 | 418.7 | 151.044 | 152.975 | 157.897 | 16830 | 0 | 1.92 | 425.653 · 155.672 |

Read by the rules: {"highest_requests_per_s": 418.812, "highest_items_per_s": 418.8, "saturation_level": 2, "rate_at_one_in_flight": 292.741, "rise_from_one_to_the_highest": 1.43, "highest_level_with_p99_at_most_100_ms": 32, "highest_level_with_p99_at_most_500_ms": 64, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [1, 2], "lowest_share_of_a_level_held": 0.83}

### evl · nvidia/llama-nemotron-embed-vl-1b-v2 · passage

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 4.539 | 290.5 | 217.375 | 234.489 | 251.482 | 182 | 0 | 0.99 |  |
| 2 | 4.658 | 298.1 | 425.6 | 456.36 | 472.34 | 187 | 0 | 0.99 |  |
| 4 | 4.689 | 300.1 | 847.606 | 890.379 | 915.786 | 188 | 0 | 1.0 |  |
| 8 | 4.681 | 299.6 | 1693.174 | 1764.266 | 1791.589 | 188 | 0 | 0.99 |  |
| 16 | 4.673 | 299.1 | 3406.461 | 3496.131 | 3522.431 | 187 | 0 | 1.02 |  |
| 32 | 4.677 | 299.3 | 6804.435 | 6903.744 | 6955.853 | 187 | 0 | 1.01 | 4.723 · 6877.764 |
| 64 | 4.688 | 300.0 | 13578.298 | 13672.251 | 13765.113 | 187 | 0 | 0.92 | 4.737 · 13533.617 |

Read by the rules: {"highest_requests_per_s": 4.689, "highest_items_per_s": 300.1, "saturation_level": 1, "rate_at_one_in_flight": 4.539, "rise_from_one_to_the_highest": 1.03, "highest_level_with_p99_at_most_100_ms": null, "highest_level_with_p99_at_most_500_ms": 2, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.976}

### evl112_onnx · nvidia/llama-nemotron-embed-vl-1b-v2 · query

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 35.51 | 35.5 | 26.607 | 29.768 | 35.561 | 1422 | 0 | 1.04 |  |
| 2 | 41.998 | 42.0 | 45.12 | 51.274 | 68.273 | 1682 | 0 | 1.08 |  |

Read by the rules: {"highest_requests_per_s": 41.998, "highest_items_per_s": 42.0, "saturation_level": 2, "rate_at_one_in_flight": 35.51, "rise_from_one_to_the_highest": 1.18, "highest_level_with_p99_at_most_100_ms": 2, "highest_level_with_p99_at_most_500_ms": 2, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.97}

### n3 · nvidia/nemotron-3-embed-1b · query

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 268.705 | 268.7 | 3.038 | 3.521 | 4.25 | 10800 | 0 | 1.39 |  |
| 2 | 371.096 | 371.1 | 4.447 | 5.249 | 6.412 | 14926 | 0 | 1.73 |  |
| 4 | 384.286 | 384.3 | 9.484 | 10.26 | 11.332 | 15457 | 0 | 1.79 |  |
| 8 | 382.38 | 382.4 | 19.782 | 21.108 | 22.564 | 15375 | 0 | 1.86 |  |
| 16 | 377.176 | 377.2 | 41.079 | 43.32 | 46.248 | 15173 | 0 | 1.91 |  |
| 32 | 378.58 | 378.6 | 82.827 | 86.162 | 89.258 | 15233 | 0 | 2.05 | 378.546 · 98.155 |
| 64 | 377.898 | 377.9 | 166.8 | 172.681 | 188.334 | 15196 | 0 | 2.05 | 373.256 · 221.747 |

Read by the rules: {"highest_requests_per_s": 384.286, "highest_items_per_s": 384.3, "saturation_level": 2, "rate_at_one_in_flight": 268.705, "rise_from_one_to_the_highest": 1.43, "highest_level_with_p99_at_most_100_ms": 32, "highest_level_with_p99_at_most_500_ms": 64, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [1, 2], "lowest_share_of_a_level_held": 0.825}

### n3 · nvidia/nemotron-3-embed-1b · passage

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 3.935 | 251.8 | 250.948 | 270.706 | 310.336 | 158 | 0 | 0.99 |  |
| 2 | 4.23 | 270.7 | 465.297 | 508.631 | 533.94 | 170 | 0 | 1.0 |  |
| 4 | 4.247 | 271.8 | 931.066 | 991.038 | 1021.539 | 168 | 0 | 0.99 |  |
| 8 | 4.25 | 272.0 | 1865.453 | 1937.197 | 1967.969 | 168 | 0 | 1.01 |  |
| 16 | 4.218 | 269.9 | 3763.105 | 3855.708 | 3864.429 | 160 | 0 | 1.03 |  |
| 32 | 4.176 | 267.2 | 7553.866 | 7722.902 | 7733.477 | 160 | 0 | 1.0 | 4.159 · 7770.555 |
| 64 | 4.233 | 270.9 | 15110.31 | 15134.246 | 15139.32 | 128 | 0 | 0.91 | 4.168 · 15309.131 |

Read by the rules: {"highest_requests_per_s": 4.25, "highest_items_per_s": 272.0, "saturation_level": 2, "rate_at_one_in_flight": 3.935, "rise_from_one_to_the_highest": 1.08, "highest_level_with_p99_at_most_100_ms": null, "highest_level_with_p99_at_most_500_ms": 1, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.99}

### rr1b · nvidia/llama-nemotron-rerank-1b-v2 · passages_100

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 6.783 | 678.3 | 140.107 | 187.416 | 227.15 | 272 | 0 | 0.95 |  |
| 2 | 8.246 | 824.6 | 238.188 | 284.988 | 339.113 | 331 | 0 | 0.97 |  |
| 4 | 8.498 | 849.8 | 459.048 | 551.612 | 627.25 | 341 | 0 | 0.98 |  |
| 8 | 9.333 | 933.3 | 828.548 | 974.22 | 1187.584 | 374 | 0 | 1.0 |  |
| 16 | 9.826 | 982.6 | 1521.832 | 2058.607 | 2392.196 | 394 | 0 | 1.05 |  |
| 32 | 9.779 | 977.9 | 3198.762 | 3588.562 | 3890.795 | 389 | 0 | 1.07 | 9.822 · 3882.495 |
| 64 | 9.77 | 977.0 | 6481.346 | 6869.047 | 7143.262 | 392 | 0 | 1.02 | 9.752 · 7276.362 |

Read by the rules: {"highest_requests_per_s": 9.826, "highest_items_per_s": 982.6, "saturation_level": 16, "rate_at_one_in_flight": 6.783, "rise_from_one_to_the_highest": 1.45, "highest_level_with_p99_at_most_100_ms": null, "highest_level_with_p99_at_most_500_ms": 2, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.979}

### rr1b · nvidia/llama-nemotron-rerank-1b-v2 · passages_10

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 35.952 | 359.5 | 27.342 | 33.807 | 41.989 | 1445 | 0 | 1.04 |  |
| 2 | 49.043 | 490.4 | 39.324 | 49.479 | 58.223 | 1971 | 0 | 1.08 |  |
| 4 | 53.754 | 537.5 | 72.22 | 87.177 | 102.287 | 2159 | 0 | 1.08 |  |
| 8 | 66.011 | 660.1 | 118.862 | 136.06 | 154.51 | 2653 | 0 | 1.13 |  |
| 16 | 72.167 | 721.7 | 217.753 | 250.789 | 279.859 | 2898 | 0 | 1.22 |  |
| 32 | 72.064 | 720.6 | 439.294 | 484.548 | 519.839 | 2894 | 0 | 1.25 | 72.072 · 523.325 |
| 64 | 71.743 | 717.4 | 885.392 | 938.684 | 975.427 | 2880 | 0 | 1.25 | 71.849 · 970.267 |

Read by the rules: {"highest_requests_per_s": 72.167, "highest_items_per_s": 721.7, "saturation_level": 16, "rate_at_one_in_flight": 35.952, "rise_from_one_to_the_highest": 2.01, "highest_level_with_p99_at_most_100_ms": 2, "highest_level_with_p99_at_most_500_ms": 16, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.97}

### rr500 · nvidia/llama-nemotron-rerank-500m-v2 · passages_100

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 11.129 | 1112.9 | 85.299 | 111.838 | 139.593 | 446 | 0 | 0.98 |  |
| 2 | 16.107 | 1610.7 | 120.824 | 147.023 | 175.452 | 646 | 0 | 1.0 |  |
| 4 | 16.737 | 1673.7 | 232.704 | 283.859 | 319.817 | 672 | 0 | 1.01 |  |
| 8 | 18.22 | 1822.0 | 427.428 | 510.349 | 594.398 | 729 | 0 | 1.03 |  |
| 16 | 19.091 | 1909.1 | 817.408 | 958.602 | 1086.367 | 765 | 0 | 1.1 |  |
| 32 | 19.013 | 1901.3 | 1653.648 | 1826.476 | 1949.007 | 762 | 0 | 1.14 | 19.12 · 1954.793 |
| 64 | 19.132 | 1913.2 | 3312.6 | 3519.29 | 3638.145 | 766 | 0 | 1.11 | 19.036 · 3702.691 |

Read by the rules: {"highest_requests_per_s": 19.132, "highest_items_per_s": 1913.2, "saturation_level": 8, "rate_at_one_in_flight": 11.129, "rise_from_one_to_the_highest": 1.72, "highest_level_with_p99_at_most_100_ms": null, "highest_level_with_p99_at_most_500_ms": 4, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.972}

### rr500 · nvidia/llama-nemotron-rerank-500m-v2 · passages_10

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 54.754 | 547.5 | 17.64 | 21.356 | 26.208 | 2192 | 0 | 1.07 |  |
| 2 | 90.219 | 902.2 | 20.742 | 26.266 | 32.367 | 3614 | 0 | 1.19 |  |
| 4 | 99.476 | 994.8 | 38.756 | 47.189 | 56.402 | 3984 | 0 | 1.19 |  |
| 8 | 123.019 | 1230.2 | 63.501 | 75.72 | 86.929 | 4928 | 0 | 1.27 |  |
| 16 | 140.249 | 1402.5 | 111.665 | 130.465 | 145.813 | 5615 | 0 | 1.4 |  |
| 32 | 139.652 | 1396.5 | 226.48 | 249.054 | 271.88 | 5594 | 0 | 1.44 | 139.839 · 266.528 |
| 64 | 139.87 | 1398.7 | 455.12 | 481.011 | 505.604 | 5600 | 0 | 1.45 | 139.718 · 503.562 |

Read by the rules: {"highest_requests_per_s": 140.249, "highest_items_per_s": 1402.5, "saturation_level": 16, "rate_at_one_in_flight": 54.754, "rise_from_one_to_the_highest": 2.56, "highest_level_with_p99_at_most_100_ms": 8, "highest_level_with_p99_at_most_500_ms": 32, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.95}

