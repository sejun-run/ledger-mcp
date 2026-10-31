# 내일 치트시트 — ledger MCP

엔드포인트: `https://ledger.sejun.run/<PREFIX>/mcp` — 실제 PREFIX는 PRIVATE.md (git 제외)

## 1. 설정 붙여넣기 — 환경 안에서 실행 (장부가 워크스페이스에 남음)

1순위: `uvx`가 있는 환경
```json
"ledger": { "command": "uvx", "args": ["--from", "git+https://github.com/sejun-run/ledger-mcp", "ledger-mcp"] }
```
2순위: `uvx` 없고 `pip`만 있을 때
```json
"ledger": { "command": "sh", "args": ["-c", "pip install -q git+https://github.com/sejun-run/ledger-mcp && ledger-mcp"] }
```
3순위(최후): 환경에 Python이 없을 때만 원격. 장부가 내 서버에 저장되므로 끝나면 reset.
```json
"ledger": { "type": "http", "url": "https://ledger.sejun.run/<PREFIX>/mcp" }
```

같이 붙일 것:
```json
"context7": { "type": "http", "url": "https://mcp.context7.com/mcp" }
```

Codex TOML이면:
```toml
[mcp_servers.ledger]
command = "uvx"
args = ["--from", "git+https://github.com/sejun-run/ledger-mcp", "ledger-mcp"]
```

장부 파일은 작업 디렉토리의 `ledger.json`. 제출물에 그대로 포함됨(`LEDGER_PATH` env로 위치 변경 가능).

## 2. 시작
첫 메시지:
> "ledger `start`를 task 요약과 함께 호출해. AI 직원들과의 대화는 내가 별도 패널에서 하고 여기로 옮겨줄게. 체크리스트대로 질문 목록부터 만들어줘."

장부가 비어있지 않으면 먼저: "ledger reset을 confirm=true로 호출해".

## 3. 도구 8개
| 도구 | 용도 |
|---|---|
| `start(task)` | 시작 시각 기록 + 킥오프 체크리스트. 제일 먼저 |
| `next()` | 경과 시간 기준 단계(discover/build/verify/submit) + 장부 상태 + 지금 할 일 |
| `log(kind, text, source, rationale, links)` | 한 건 기록. kind = problem / requirement / constraint / assumption / question / decision / risk |
| `log_many(items)` | 여러 건 한 번에. 대화 덩어리를 붙여넣었을 때 Codex가 씀 |
| `update(id, status, note, links)` | 상태 변경 + 메모(답변, 검증 증거) |
| `show(kind, status)` | 조회 |
| `report()` | Q&A용 마크다운. 미검증 항목은 "Where this could fail"에 자동 수집 |
| `reset(confirm=true)` | 초기화 |

## 4. 루프: 나 = AI 직원 패널 ↔ Codex 사이의 전달자
예상 흐름: 문제가 넓고 많음 → 직원 대화로 범위 결정 → localhost 웹으로 관리 도구 구축.

1. `start` → Codex가 워크스페이스 탐색하고 발견한 사실을 `workspace:<경로>` 출처로 기록, 나한테 요약.
2. Codex가 인터뷰 질문을 `question`으로 등록하고 직원별로 출력 → 복사해서 패널에 질문.
3. 답변을 Codex 채팅에 붙여넣기. 발화자만 앞에 표시:
   ```
   [PM 직원] 수율 리포트를 매일 손으로 취합함. 08시 전 필요
   [설비 직원] 알람 분류가 느린데 실시간 피드가 필요함. 외부망 불가
   ```
   Codex가 `log_many`로 problem / requirement / constraint 분류, 질문은 `answered`.
4. **범위 결정.** 후보 문제 3개 이상 모이면 Codex가 하나를 제안 → 내가 직원에게 확인 → 붙여넣기 → Codex가 `SCOPE:` decision 기록, 나머지 `dropped`.
   `next`는 SCOPE decision이 없으면 build로 못 넘어가게 막음.
5. 빌드: 30분 안에 localhost에 뜨는 최소 버전부터, 이후 요구사항 하나씩. 검증은 코드 읽기 말고 실제 호출.
6. 직원이 말을 바꾸면 그대로 붙여넣기 → `decision`.
7. 마지막 30분: "report 호출해서 제출물에 붙여". `ledger.json`도 제출물에 포함됨. report 맨 앞에 Scope 섹션(선택한 문제 ✔, 버린 문제와 이유)이 나와서 Q&A의 "왜 이 문제를 골랐나"에 바로 답이 됨.

내가 챙길 것: 한 시간에 한 번 "next 호출해봐", 붙여넣을 때 발화자 표시, 범위 확정 전에 코드 못 짜게, 마지막 report.

## 5. 비상시
- 도메인 안 붙으면: `http://<AMPERE_PUBLIC_IP>:8000/mcp` (OCI 8000 열려있을 때만)
- 서버 재시작: `ssh ampere docker restart ledger`
- 장부 백업: `ssh ampere docker exec ledger cat /data/ledger.json`

## 6. 외울 것
```json
"ledger":   { "command": "uvx", "args": ["--from", "git+https://github.com/sejun-run/ledger-mcp", "ledger-mcp"] },
"context7": { "type": "http", "url": "https://mcp.context7.com/mcp" }
```
- 리포 주소 = github.com/<내 깃헙 아이디>/ledger-mcp. 명령 이름 = ledger-mcp.
- `uvx` 없으면 `sh -c "pip install -q git+<리포> && ledger-mcp"`.
- 붙인 뒤 "ledger show 호출해봐" → `(no entries)` 면 OK. 안 뜨면 원격 URL(PRIVATE.md)로 교체.
