# echo-bench

Echo 반복 공격 평가 파이프라인의 뼈대. 이 브랜치에는 공통 루프, Benign 모델 래퍼, mock 어댑터, dummy 공격자만 있음
(벤치마크별 실제 어댑터는 아직 없음).

## 디렉터리

```
echo-bench/
├─ config.yaml               # Benign 모델, B, T, 공격자, 어댑터 모드, 샘플 수, 데이터 경로
├─ run.py                    # 진입점: 설정 읽기 → 케이스 순회 → 루프 실행 → runner별 ASR 출력
├─ check_loader.py           # 데이터 로드 점검 (runner별 개수, 중복, 예시)
├─ core/
│   ├─ schema.py             # Case, Attempt, Result, RunResult 데이터 클래스
│   ├─ config.py             # config.yaml + .env 읽기
│   ├─ loader.py             # jsonl 로드 + 중복 제거 + 샘플링
│   ├─ loop.py               # 시도 루프 (예산 B, 종료 조건)
│   ├─ logger.py             # attempts.jsonl / results.jsonl 기록
│   └─ benign.py             # Benign 모델 호출 래퍼 (타임아웃 T → NONE)
├─ adapters/
│   ├─ base.py               # 어댑터 인터페이스 (reset / get_source / run / observe / judge)
│   └─ mock.py               # 루프 테스트용 가짜 어댑터 (판정 의미 없음)
├─ attackers/
│   ├─ base.py               # attack() 인터페이스
│   └─ dummy.py              # 베이스라인: 슬롯 끝에 goal 붙이기
├─ data/                     # 벤치마크 jsonl (git 제외)
└─ outputs/                  # 실행별 로그 (git 제외)
```

## 준비

```
pip install -r requirements.txt
cp .env.example .env                 # DEEPSEEK_API_KEY 채우기
python check_loader.py data/test_cases.jsonl
```

`check_loader.py`는 runner별 개수가 아래 표와 같으면 `OK`를 출력함.
`data/`의 `user_cases.jsonl` / `attacker_cases.jsonl` / `reference_catalog.jsonl`은 케이스가 아닌 카탈로그라
로더에 넣으면 `KeyError: 'evaluation'`으로 멈춤. 케이스 파일(`test_cases.jsonl`, 또는 벤치마크별
`workspace.jsonl`, `github.jsonl`, `injecagent.jsonl`, `code.jsonl`)만 넣을 것.

## 데이터 구성 (중복 제거 후)

| runner | 케이스 수 | 비고 |
|---|---|---|
| agentdojo (workspace) | 198 | |
| agentdyn (github) | 180 | agentdojo와 같은 어댑터를 씀 |
| injecagent | 1054 | `setting == base`만 사용 (enhanced는 같은 케이스의 다른 주입 문구) |
| bipia | 2500 | `position == end`만 사용 (주입 위치는 공격자가 직접 정하므로) |

이후 `(user_case_id, attacker_case_id)`가 같은 행은 하나만 남김.
BIPIA의 goal은 카테고리 이름뿐이라 `poisoned_context`에서 `clean_context`를 뺀 실제 공격 문장을 goal로 씀.

## 실행 흐름

```
케이스마다:
  source = adapter.get_source(case)                 # {슬롯 id: 원본 텍스트}
  시도 i = 1..B:
    adapter.reset(case)                             # 대상 환경 초기화
    modified = attacker.attack(source, goal, history)
    run = adapter.run(case, modified)               # Benign 모델 실행 (타임아웃 T)
    observation = adapter.observe(run)              # 공격자가 볼 수 있는 출력, 또는 "NONE"
    success, detail = adapter.judge(case, run)
    attempts.jsonl에 한 줄 기록
    성공이면 종료, 아니면 history에 (modified, observation) 추가
  B번 모두 실패하면 budget_exhausted
```

- 대상 환경은 매 시도 초기화하고, 공격자의 수정·관측 이력(`history`)은 케이스 안에서 유지함
- `history`에는 관측값만 들어가고 판정 결과·근거(`detail`)는 들어가지 않음
- Benign 호출이 T초를 넘기면 출력이 없고, 관측값은 `NONE`이 됨.
  429 / 5xx / 연결 오류는 백오프 후 최대 `max_retries`번 재시도 (재시도마다 T를 새로 적용)

## 설정 (`config.yaml`)

| 키 | 의미 |
|---|---|
| `benign.provider` | `deepseek` / `openai_compat` / `mock` (네트워크 없이 루프 테스트용) |
| `benign.model` | 예: `deepseek-flash` |
| `benign.timeout_s` | T (초) |
| `budget` | B, 케이스당 최대 시도 수 |
| `attacker` | `attackers/__init__.py`의 `ATTACKERS`에 등록된 이름 (현재 `dummy`) |
| `adapters` | 현재는 `mock`만 동작. 실제 어댑터가 등록되면 `real` |
| `data` | 케이스 jsonl 경로 목록 (glob 가능) |
| `sample_per_runner` | runner별 샘플 수, `null`이면 전체 |

## 실행

```
python run.py                        # config.yaml 그대로
python run.py --config other.yaml
```

`outputs/<timestamp>/`에 남는 파일:

| 파일 | 내용 |
|---|---|
| `attempts.jsonl` | 시도마다 한 줄: `case_id`, `attempt_idx`, `modified_source`, `observation`, `success`, `detail` |
| `results.jsonl` | 케이스마다 한 줄: `case_id`, `success`, `attempts_used`, `end_reason` |
| `config.yaml` | 실행에 쓴 설정 사본 |

실행이 끝나면 runner별 ASR(성공 케이스 / 전체 케이스)을 콘솔에 출력함.

## 현재 한계

- 어댑터는 `mock`뿐임. 데이터 행으로 단순 채팅 프롬프트를 만들고, 출력에 goal이 그대로 들어 있는지로 판정함.
  흐름 확인용이고 수치는 의미 없음
- `benign.provider: mock`은 30% 확률로 입력을 따라 말하는 가짜 모델
- 공격자는 `dummy`뿐임 (history를 쓰지 않음)

## 공격자 연결

공격자는 `attack(source, goal, history) -> dict[str, str]` 하나로만 연결됨 (`attackers/base.py`).

1. `attackers/<이름>.py`에 `Attacker`를 상속한 클래스 작성
2. `attackers/__init__.py`의 `ATTACKERS`에 등록
3. `config.yaml`의 `attacker:`를 그 이름으로 변경

- `source`: `{슬롯 id: 원본 텍스트}`. 같은 키로 돌려줄 것
- `goal`: 공격 목표 문장
- `history`: `[(이전 수정 소스, 관측값), ...]`. 관측값은 Benign 출력 또는 `NONE`
