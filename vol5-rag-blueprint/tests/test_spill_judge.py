"""spill_judge: the C4 rule on numbers shaped like the second night's (made up, not read from its files)."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import spill_judge as J  # noqa: E402

ALONE = {"embed": {"shared_mib": 120, "card_delta_mib": 5600}, "rank": {"shared_mib": 300, "card_delta_mib": 3500},
         "llm": {"shared_mib": 60, "card_delta_mib": 21000}}


def steps(llm_delta=21000):
    return [{"service": "embed", "card_delta_mib": 5600, "at_sample": 0}, {"service": "rank", "card_delta_mib": 3490, "at_sample": 5},
            {"service": "llm", "card_delta_mib": llm_delta, "at_sample": 10}]


def test_pinned_memory_alone_is_not_a_spill():
    shared = [20, 130, 125, 125, 125, 430, 430, 425, 430, 430, 500, 505, 500, 500]     # the reranker's pool, nothing paged out
    r = J.judge(ALONE, steps(), shared)
    assert r["spilled"] is False and r["shared_above_allowed"] == [] and r["starts_below_half"] == []


def test_a_gigabyte_jump_is_a_spill():
    shared = [20, 130, 125, 125, 125, 430, 430, 425, 430, 430, 500, 2600, 2100, 1600]
    r = J.judge(ALONE, steps(), shared)
    assert r["spilled"] and r["shared_above_allowed"][0]["after"] == "llm"


def test_a_start_that_lands_off_the_card_is_a_spill():
    shared = [20, 130, 125, 125, 125, 430, 430, 425, 430, 430, 500, 505, 500, 500]
    r = J.judge(ALONE, steps(llm_delta=9000), shared)
    assert r["spilled"] and r["starts_below_half"][0]["service"] == "llm"


def test_the_allowance_grows_with_each_service():
    shared = [20, 700, 700, 700, 700, 700, 900, 900, 900, 900, 950, 950, 950, 950]   # 700 > 120+512 only before the reranker starts
    r = J.judge(ALONE, steps(), shared)
    assert [x["after"] for x in r["shared_above_allowed"]] == ["embed"]


def test_steady_shared_skips_the_start():
    assert J.steady_shared([0] * 3 + [900] * 2 + [200] * 20, ready_index=3) == 200
