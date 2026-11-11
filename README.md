# echo-bench directory 
```
echo_bench/
├─ config.yaml               # 모델, B, T, 샘플 수, 데이터 경로
├─ run.py                    # 진입점: 설정 읽기 → 케이스 순회 → 루프 실행
├─ core/
│   ├─ schema.py             # Case, Attempt, Result 데이터 클래스
│   ├─ loader.py             # jsonl 로드 + 중복 제거 + 샘플링
│   ├─ loop.py               # 시도 루프 (예산 B, 종료 조건)
│   ├─ logger.py             # 시도별 jsonl 기록
│   └─ benign.py             # Benign 모델 호출 래퍼 (타임아웃 T → NONE)
├─ adapters/
│   ├─ base.py               # 어댑터 인터페이스
│   ├─ injecagent.py
│   ├─ agentdojo.py          # workspace + github 같이 처리
│   └─ bipia.py
├─ attackers/
│   ├─ base.py               # attack() 인터페이스
│   └─ dummy.py              # source + goal 붙이기
└─ outputs/                  # 로그, 집계 결과`
```