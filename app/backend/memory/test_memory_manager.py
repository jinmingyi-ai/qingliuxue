# -*- coding: utf-8 -*-
"""Smoke tests for the local memory manager."""

from __future__ import annotations

import tempfile
from pathlib import Path

from memory_manager import MemoryManager


def run_tests() -> bool:
    with tempfile.TemporaryDirectory() as tmp_dir:
        store_path = Path(tmp_dir) / "memory_store.json"
        manager = MemoryManager(store_path=store_path, recent_message_limit=6, max_long_term_memories=8)

        conv1 = manager.create_conversation("visitor", title="美国CS硕士", entry_point="personalized")
        manager.append_message(
            "visitor",
            conv1["conversation_id"],
            "user",
            "我叫小林，GPA 3.55，有2年AI产品工作经验，想申请美国CS硕士，比较看重就业和性价比。",
        )
        manager.append_message(
            "visitor",
            conv1["conversation_id"],
            "assistant",
            "建议优先看美国CS硕士里项目导向和就业资源强的路线，并参考类似AI产品背景案例。",
        )
        manager.append_message("visitor", conv1["conversation_id"], "user", "好的")

        conv2 = manager.create_conversation("visitor", title="英国方向", entry_point="direct")
        manager.append_message("visitor", conv2["conversation_id"], "user", "另外我也想看看英国商科，预算不要太高。")

        profile = manager.export_user_profile("visitor")
        conversations = manager.list_conversations("visitor")
        context = manager.build_prompt_context(
            "visitor",
            conv1["conversation_id"],
            current_query="继续推荐美国AI产品背景的CS硕士路线",
        )

        checks = [
            ("display_name", profile["display_name"] == "小林"),
            ("target_country_us", "US" in profile["goals"]["target_countries"]),
            ("target_country_uk", "UK" in profile["goals"]["target_countries"]),
            ("target_level", profile["goals"]["target_level"] == "graduate"),
            ("major", "Computer Science" in profile["goals"]["target_majors"]),
            ("gpa", profile["academic"]["gpa"] == 3.55),
            ("work_years", profile["experiences"]["work_years"] == 2.0),
            ("product", profile["experiences"]["has_product"] is True),
            ("ai", profile["experiences"]["has_ai"] is True),
            ("multi_conversation", len(conversations) == 2),
            ("prompt_has_profile", "小林" in context.prompt_context and "GPA/绩点: 3.55" in context.prompt_context),
            ("prompt_has_summary", "当前会话摘要" in context.prompt_context),
            ("low_value_pruned_from_memory", all("好的" not in item["content"] for item in context.long_term_memories)),
        ]

        all_passed = True
        for name, passed in checks:
            all_passed = all_passed and passed
            print(f"{name}: {'PASS' if passed else 'FAIL'}")

        removed = manager.forget_memory("visitor", "就业")
        print(f"forget_memory_removed: {removed}")
        all_passed = all_passed and removed >= 1

        print("ALL PASSED" if all_passed else "SOME TESTS FAILED")
        return all_passed


if __name__ == "__main__":
    ok = run_tests()
    raise SystemExit(0 if ok else 1)
