# -*- coding: utf-8 -*-
"""Smoke tests for the hybrid RAG retriever."""

from __future__ import annotations

from retriever import HybridCaseRetriever


TESTS = [
    {
        "name": "美国本科 CS + 竞赛背景",
        "query": "GPA 3.6左右，有信息学奥赛、NOIP和ACM比赛，想申请美国CS本科",
        "filters": {"level": "undergrad", "country": "US"},
        "expected_any": ["us_undergrad_009", "us_undergrad_006"],
    },
    {
        "name": "美国硕士 + 2年工作经验",
        "query": "本科背景一般，GPA 3.55，有2年AI产品和后端工作经验，想申请美国CS硕士",
        "filters": {"level": "graduate", "country": "US"},
        "expected_any": ["us_graduate_002", "us_graduate_004", "us_graduate_006", "us_graduate_008"],
    },
    {
        "name": "加拿大研究型硕士 + 科研",
        "query": "985本科GPA 3.7，有实验室科研和论文经历，想申请加拿大CS研究型硕士",
        "filters": {"level": "graduate", "country": "Canada"},
        "expected_any": ["ca_graduate_001"],
    },
    {
        "name": "英国本科 + 牛剑学术兴趣",
        "query": "预测成绩A*A*A，数学能力强，MAT高分，想申请英国牛剑计算机本科",
        "filters": {"level": "undergrad", "country": "UK"},
        "expected_any": ["uk_undergrad_001"],
    },
    {
        "name": "澳洲硕士 + 工作项目落地",
        "query": "GPA 3.55，有真实工作经验和项目落地经历，想申请澳大利亚CS硕士，重视就业",
        "filters": {"level": "graduate", "country": "Australia"},
        "expected_any": ["au_graduate_002", "au_graduate_004"],
    },
    {
        "name": "加拿大本科 + 自学逆袭",
        "query": "普通高中，成绩一般但自学编程能力强，有成长故事，想申请加拿大CS本科",
        "filters": {"level": "undergrad", "country": "Canada"},
        "expected_any": ["ca_undergrad_004", "ca_undergrad_006"],
    },
]


def run_tests(k: int = 5) -> bool:
    retriever = HybridCaseRetriever(rebuild=False)
    all_passed = True

    for test in TESTS:
        print("\n" + "=" * 92)
        print(test["name"])
        print("Query:", test["query"])
        results = retriever.retrieve(test["query"], k=k, filters=test["filters"])
        returned_profile_ids = [item.metadata.get("profile_id") for item in results]
        passed = any(expected in returned_profile_ids[:3] for expected in test["expected_any"])
        all_passed = all_passed and passed

        print("Expected any in Top3:", test["expected_any"])
        print("Returned:", returned_profile_ids)
        print("PASS" if passed else "FAIL")

        for rank, result in enumerate(results[:3], 1):
            meta = result.metadata
            print(
                f"Top{rank} score={result.score:.2f} "
                f"{meta.get('profile_id')} {meta.get('name')} "
                f"{meta.get('country')} {meta.get('level')} "
                f"choice={meta.get('final_choice')}"
            )
            print("  reasons:", " | ".join(result.reasons[:5]))

    print("\n" + "=" * 92)
    print("ALL PASSED" if all_passed else "SOME TESTS FAILED")
    return all_passed


if __name__ == "__main__":
    ok = run_tests()
    raise SystemExit(0 if ok else 1)
