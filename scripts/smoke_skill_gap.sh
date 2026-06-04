#!/bin/bash
# Skill Gap API Smoke Test
# 用法: bash scripts/smoke_skill_gap.sh

echo "=== Skill Gap API Smoke Test ==="

# 1. 正常请求
echo -e "\n--- 正常请求 ---"
curl -s -X POST http://localhost:8000/skill_gap \
  -H "Content-Type: application/json" \
  -d '{"job_name": "Python后端", "user_skills": ["Python", "MySQL", "Git"], "top_n": 10}' \
  | python -m json.tool 2>/dev/null || echo "Failed"

# 2. 空 user_skills
echo -e "\n--- 空 user_skills ---"
curl -s -X POST http://localhost:8000/skill_gap \
  -H "Content-Type: application/json" \
  -d '{"job_name": "Python后端", "user_skills": []}' \
  | python -m json.tool 2>/dev/null || echo "Failed"

# 3. job_name 为空（应返回 400）
echo -e "\n--- job_name 为空（应返回 400）---"
curl -s -w "\nHTTP Status: %{http_code}\n" -X POST http://localhost:8000/skill_gap \
  -H "Content-Type: application/json" \
  -d '{"job_name": "", "user_skills": ["Python"]}' \
  | python -m json.tool 2>/dev/null || echo "Failed"

# 4. top_n 超出范围（应返回 422）
echo -e "\n--- top_n=100（应返回 422）---"
curl -s -w "\nHTTP Status: %{http_code}\n" -X POST http://localhost:8000/skill_gap \
  -H "Content-Type: application/json" \
  -d '{"job_name": "Python后端", "user_skills": ["Python"], "top_n": 100}' \
  | python -m json.tool 2>/dev/null || echo "Failed"

echo -e "\n=== Smoke Test Complete ==="
