### e1b · nvidia/llama-nemotron-embed-1b-v2 · query

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 112.455 | 112.5 | 8.108 | 8.694 | 9.115 | 4498 | 0 | 1.15 |  |
| 2 | 184.488 | 184.5 | 9.957 | 10.454 | 11.373 | 7381 | 0 | 1.35 |  |

Read by the rules: {"highest_requests_per_s": 184.488, "highest_items_per_s": 184.5, "saturation_level": 2, "rate_at_one_in_flight": 112.455, "rise_from_one_to_the_highest": 1.64, "highest_level_with_p99_at_most_100_ms": 2, "highest_level_with_p99_at_most_500_ms": 2, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.92}

### e1b · nvidia/llama-nemotron-embed-1b-v2 · passage

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 9.326 | 596.8 | 103.758 | 121.96 | 158.447 | 372 | 0 | 1.05 |  |
| 2 | 12.518 | 801.2 | 156.604 | 178.479 | 201.387 | 500 | 0 | 0.99 |  |

Read by the rules: {"highest_requests_per_s": 12.518, "highest_items_per_s": 801.2, "saturation_level": 2, "rate_at_one_in_flight": 9.326, "rise_from_one_to_the_highest": 1.34, "highest_level_with_p99_at_most_100_ms": null, "highest_level_with_p99_at_most_500_ms": 2, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.98}

### e300 · nvidia/llama-nemotron-embed-300m-v2 · query

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 170.354 | 170.4 | 5.048 | 5.701 | 6.827 | 6815 | 0 | 1.26 |  |
| 2 | 281.261 | 281.3 | 6.067 | 7.346 | 8.992 | 11251 | 0 | 1.59 |  |
| 4 | 373.155 | 373.2 | 9.242 | 12.258 | 15.49 | 14934 | 0 | 1.89 |  |
| 8 | 399.632 | 399.6 | 18.588 | 22.932 | 28.291 | 15994 | 0 | 2.0 |  |
| 16 | 416.197 | 416.2 | 37.146 | 42.309 | 50.472 | 16653 | 0 | 2.11 |  |
| 32 | 417.163 | 417.2 | 75.162 | 81.766 | 94.332 | 16693 | 0 | 2.2 | 413.526 · 94.835 |
| 64 | 416.529 | 416.5 | 151.61 | 162.158 | 184.874 | 16662 | 0 | 2.2 | 413.804 · 181.926 |

Read by the rules: {"highest_requests_per_s": 417.163, "highest_items_per_s": 417.2, "saturation_level": 8, "rate_at_one_in_flight": 170.354, "rise_from_one_to_the_highest": 2.45, "highest_level_with_p99_at_most_100_ms": 32, "highest_level_with_p99_at_most_500_ms": 64, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [1, 2, 4], "lowest_share_of_a_level_held": 0.875}

### e300 · nvidia/llama-nemotron-embed-300m-v2 · passage

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 16.765 | 1073.0 | 56.626 | 66.838 | 89.91 | 670 | 0 | 1.12 |  |
| 2 | 31.096 | 1990.2 | 60.8 | 72.47 | 94.019 | 1244 | 0 | 1.35 |  |
| 4 | 33.332 | 2133.2 | 117.628 | 129.569 | 138.012 | 1333 | 0 | 1.39 |  |
| 8 | 33.328 | 2133.0 | 238.101 | 252.219 | 259.208 | 1333 | 0 | 1.43 |  |
| 16 | 33.398 | 2137.5 | 477.482 | 494.89 | 505.181 | 1336 | 0 | 1.46 |  |
| 32 | 33.334 | 2133.4 | 957.121 | 971.777 | 986.051 | 1333 | 0 | 1.51 | 33.322 · 993.905 |
| 64 | 33.293 | 2130.8 | 1915.571 | 1933.121 | 1953.694 | 1332 | 0 | 1.49 | 33.239 · 1958.305 |

Read by the rules: {"highest_requests_per_s": 33.398, "highest_items_per_s": 2137.5, "saturation_level": 4, "rate_at_one_in_flight": 16.765, "rise_from_one_to_the_highest": 1.99, "highest_level_with_p99_at_most_100_ms": 2, "highest_level_with_p99_at_most_500_ms": 8, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.965}

### evl · nvidia/llama-nemotron-embed-vl-1b-v2 · query

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 296.803 | 296.8 | 2.77 | 2.891 | 3.092 | 11876 | 0 | 1.39 |  |
| 2 | 421.191 | 421.2 | 4.009 | 4.234 | 4.535 | 16853 | 0 | 1.69 |  |

Read by the rules: {"highest_requests_per_s": 421.191, "highest_items_per_s": 421.2, "saturation_level": 2, "rate_at_one_in_flight": 296.803, "rise_from_one_to_the_highest": 1.42, "highest_level_with_p99_at_most_100_ms": 2, "highest_level_with_p99_at_most_500_ms": 2, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [1, 2], "lowest_share_of_a_level_held": 0.83}

### evl · nvidia/llama-nemotron-embed-vl-1b-v2 · passage

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 4.632 | 296.4 | 214.734 | 230.589 | 245.483 | 185 | 0 | 0.99 |  |

Read by the rules: {"highest_requests_per_s": 4.632, "highest_items_per_s": 296.4, "saturation_level": 1, "rate_at_one_in_flight": 4.632, "rise_from_one_to_the_highest": 1.0, "highest_level_with_p99_at_most_100_ms": null, "highest_level_with_p99_at_most_500_ms": 1, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.99}

### n3 · nvidia/nemotron-3-embed-1b · query

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 268.54 | 268.5 | 3.038 | 3.506 | 4.238 | 10743 | 0 | 1.4 |  |
| 2 | 373.799 | 373.8 | 4.517 | 5.305 | 6.385 | 14953 | 0 | 1.72 |  |

Read by the rules: {"highest_requests_per_s": 373.799, "highest_items_per_s": 373.8, "saturation_level": 2, "rate_at_one_in_flight": 268.54, "rise_from_one_to_the_highest": 1.39, "highest_level_with_p99_at_most_100_ms": 2, "highest_level_with_p99_at_most_500_ms": 2, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [1, 2], "lowest_share_of_a_level_held": 0.84}

### n3 · nvidia/nemotron-3-embed-1b · passage

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 3.986 | 255.1 | 248.947 | 271.107 | 301.394 | 159 | 0 | 1.0 |  |
| 2 | 4.258 | 272.5 | 465.86 | 506.194 | 531.908 | 170 | 0 | 0.99 |  |

Read by the rules: {"highest_requests_per_s": 4.258, "highest_items_per_s": 272.5, "saturation_level": 2, "rate_at_one_in_flight": 3.986, "rise_from_one_to_the_highest": 1.07, "highest_level_with_p99_at_most_100_ms": null, "highest_level_with_p99_at_most_500_ms": 1, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.995}

### rr1b · nvidia/llama-nemotron-rerank-1b-v2 · passages_100

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 6.817 | 681.7 | 140.012 | 187.113 | 225.39 | 272 | 0 | 0.97 |  |
| 16 | 9.875 | 987.5 | 1573.076 | 1900.561 | 2232.683 | 394 | 0 | 1.05 |  |

Read by the rules: {"highest_requests_per_s": 9.875, "highest_items_per_s": 987.5, "saturation_level": 16, "rate_at_one_in_flight": 6.817, "rise_from_one_to_the_highest": 1.45, "highest_level_with_p99_at_most_100_ms": null, "highest_level_with_p99_at_most_500_ms": 1, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.983}

### rr1b · nvidia/llama-nemotron-rerank-1b-v2 · passages_10

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 35.834 | 358.3 | 27.445 | 33.977 | 41.886 | 1433 | 0 | 1.03 |  |
| 16 | 72.642 | 726.4 | 215.507 | 260.348 | 287.882 | 2906 | 0 | 1.21 |  |

Read by the rules: {"highest_requests_per_s": 72.642, "highest_items_per_s": 726.4, "saturation_level": 16, "rate_at_one_in_flight": 35.834, "rise_from_one_to_the_highest": 2.03, "highest_level_with_p99_at_most_100_ms": 1, "highest_level_with_p99_at_most_500_ms": 16, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.97}

### rr500 · nvidia/llama-nemotron-rerank-500m-v2 · passages_100

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 11.227 | 1122.7 | 85.181 | 111.15 | 137.256 | 448 | 0 | 0.98 |  |
| 8 | 18.405 | 1840.5 | 423.741 | 504.446 | 581.76 | 736 | 0 | 1.03 |  |

Read by the rules: {"highest_requests_per_s": 18.405, "highest_items_per_s": 1840.5, "saturation_level": 8, "rate_at_one_in_flight": 11.227, "rise_from_one_to_the_highest": 1.64, "highest_level_with_p99_at_most_100_ms": null, "highest_level_with_p99_at_most_500_ms": 1, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.99}

### rr500 · nvidia/llama-nemotron-rerank-500m-v2 · passages_10

| In flight | Requests/s | Items/s | p50 ms | p90 ms | p99 ms | Requests | Errors | Client: cores used | Second container: requests/s · p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 54.976 | 549.8 | 17.514 | 21.403 | 26.582 | 2199 | 0 | 1.05 |  |
| 16 | 141.235 | 1412.3 | 111.14 | 128.824 | 144.524 | 5651 | 0 | 1.41 |  |

Read by the rules: {"highest_requests_per_s": 141.235, "highest_items_per_s": 1412.3, "saturation_level": 16, "rate_at_one_in_flight": 54.976, "rise_from_one_to_the_highest": 2.57, "highest_level_with_p99_at_most_100_ms": 1, "highest_level_with_p99_at_most_500_ms": 16, "levels_with_errors": [], "levels_client_limited": [], "levels_not_held": [], "lowest_share_of_a_level_held": 0.95}

