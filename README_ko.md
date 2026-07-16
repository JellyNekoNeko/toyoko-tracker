# Toyoko Inn 객실 빈방 추적기 — WebUI & 데스크톱

*[Toyoko Inn](https://www.toyoko-inn.com/) 객실 예약 가능 상태를 자동으로 확인하는 귀여운 크로스 플랫폼 도구입니다. Python WebUI와 macOS·Windows·Linux용 데스크톱 앱을 제공합니다.*

- 🌏 [📖 English Guide](https://github.com/JellyNekoNeko/toyoko-tracker/blob/main/README.md)
- 🌏 [📖 中文说明书](https://github.com/JellyNekoNeko/toyoko-tracker/blob/main/README_zh.md)
- 🌏 [📖 日本語ガイド](https://github.com/JellyNekoNeko/toyoko-tracker/blob/main/README_ja.md)

---

## 주요 기능

- 🌐 로컬 WebUI에서 빈방 결과를 실시간으로 표시
- 🖥 macOS·Windows·Linux용 데스크톱 앱
- ⚡ 가벼운 HTTP/API 검색 엔진
- 🧭 호환성을 위한 선택사항 Playwright 엔진
- 🏨 지역 또는 반경을 기준으로 호텔 선택
- 🗂 조건과 결과가 분리된 여러 영구 모니터 작업 및 공정 스케줄링
- 🛏 싱글·더블·트윈 객실 유형 필터
- 💳 회원가와 비회원가 표시
- 📅 선택한 각 호텔의 월간 가격 달력을 필요할 때 새로고침
- 🔀 유연한 날짜·주말 검색과 여러 박 연속 객실 확인
- 🌡 여러 호텔 총액 비교, 가격 히트맵과 일별 최저가 호텔
- 🎯 목표가·회원가·가격 인하·객실 상태 변화 알림
- 🌙 방해 금지 시간, 메시지 묶음, 일일 요약, 긴급 규칙
- 🔔 로컬 데스크톱 알림
- 🤖 Telegram, 📱 Bark, 💬 Server Chan, 📧 SMTP 이메일 알림
- 🚀 여러 호텔을 효율적으로 검색하는 스마트 병렬 스캔

0.7.0 다중 작업 사용법은
[`docs/PHASE1_MULTI_TASK_GUIDE.md`](docs/PHASE1_MULTI_TASK_GUIDE.md)를 참고하세요.
가격 알림과 알림 정책은
[`docs/PHASE2_ALERTS_GUIDE.md`](docs/PHASE2_ALERTS_GUIDE.md)를 참고하세요.
유연한 날짜, 연박 확인과 호텔 가격 비교는
[`docs/PHASE3_FLEXIBLE_STAYS.md`](docs/PHASE3_FLEXIBLE_STAYS.md)를 참고하세요.

## 요구 사항

- Python **3.9 이상** (Python 3.10–3.14 권장)
- 인터넷 연결
- Playwright는 호환 엔진을 사용할 때만 필요

## PyPI에서 설치

### macOS

Homebrew Python은 PEP 668에 따라 시스템 전역 `pip install`을 제한하므로
`pipx` 사용을 권장합니다.

```bash
brew install pipx
pipx ensurepath
pipx install toyoko-tracker
```

터미널을 다시 열고 실행합니다.

```bash
toyoko-tracker
```

### Linux

배포판의 패키지 관리자로 `pipx`를 설치한 다음 실행합니다.

```bash
pipx ensurepath
pipx install toyoko-tracker
toyoko-tracker
```

### Windows

PowerShell 또는 명령 프롬프트에서 실행합니다.

```powershell
py -m pip install --upgrade toyoko-tracker
toyoko-tracker
```

### 가상 환경 사용

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip toyoko-tracker
toyoko-tracker
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip toyoko-tracker
toyoko-tracker
```

## 데스크톱 버전

[GitHub Releases](https://github.com/JellyNekoNeko/toyoko-tracker/releases)에서
시스템에 맞는 파일을 다운로드하세요.

| OS | 아키텍처 | 파일 |
|---|---|---|
| macOS | Apple Silicon | `ToyokoTracker-macos-arm64.zip` |
| macOS | Intel | `ToyokoTracker-macos-x64.zip` |
| Windows | ARM64 | `ToyokoTracker-windows-arm64.zip` |
| Windows | x86-64 | `ToyokoTracker-windows-x64.zip` |
| Linux | ARM64 | `ToyokoTracker-linux-arm64.tar.gz` |
| Linux | x86-64 | `ToyokoTracker-linux-x64.tar.gz` |

macOS에서는 ZIP 파일을 풀고 `ToyokoTracker.app`을 Applications 폴더로
이동한 뒤 실행합니다. 첫 실행 시 보안 경고가 나오면
시스템 설정의 ‘개인정보 보호 및 보안’에서 열기를 허용하세요.

## Playwright 엔진 (선택사항)

가상 환경 안에서 다음을 실행합니다.

```bash
python -m pip install --upgrade "toyoko-tracker[playwright]"
python -m playwright install chromium
```

기본 HTTP/API 엔진은 Playwright가 필요하지 않습니다.

## 기본 사용법

1. `toyoko-tracker`를 실행합니다.
2. 브라우저에 표시된 WebUI를 엽니다.
3. 지역, 호텔, 체크인 날짜, 숙박 일수, 인원, 객실 유형을 선택합니다.
4. ‘검색’ 또는 ‘스캔 시작’을 누릅니다.
5. 필요하면 Telegram, Bark, Server Chan, SMTP 알림을 설정합니다.

기본값은 `127.0.0.1`에서만 접속을 받습니다. 휴대폰이나 LAN에서 접속하려면
WebUI의 모바일/LAN 접속 설정을 사용하세요.

## 알림 설정

WebUI 설정 화면에서 다음 채널을 설정할 수 있습니다.

- **Telegram**: BotFather에서 Bot Token을 만들고 Chat ID와 함께 입력
- **Bark**: iPhone/iPad Bark 키 또는 URL 입력
- **Server Chan**: SendKey 입력
- **SMTP**: SMTP 호스트, 포트, 사용자 이름, 앱 비밀번호, 수신자 입력
- **로컬 알림**: 운영체제의 알림 권한 허용

## 설정 파일

| OS | 기본 폴더 |
|---|---|
| macOS | `~/Library/Application Support/ToyokoTracker/` |
| Windows | `%APPDATA%\ToyokoTracker\` |
| Linux | `~/.config/toyoko-tracker/` |

환경 변수로 저장 위치를 변경할 수 있습니다.

```bash
TOYOKO_TRACKER_CONFIG_DIR=/path/to/config toyoko-tracker
```

## 업데이트

PyPI / pipx 버전:

```bash
pipx upgrade toyoko-tracker
```

`pip`로 설치했다면 해당 환경을 활성화한 뒤 실행합니다.

```bash
python -m pip install --upgrade toyoko-tracker
```

데스크톱 버전은 GitHub Releases의 `desktop-v*` 릴리스를 확인합니다.
WebUI와 데스크톱 버전은 같은 주요 버전 번호를 사용하지만,
각각 PyPI와 GitHub Releases를 통해 업데이트됩니다.

## 문제 해결

### `toyoko-tracker` 명령을 찾을 수 없음

```bash
pipx ensurepath
pipx reinstall toyoko-tracker
```

터미널을 다시 여세요. 가상 환경을 사용한다면 환경을 활성화하고
`python -m toyoko_tracker`를 실행할 수 있습니다.

### macOS에서 로컬 알림이 표시되지 않음

```bash
brew install terminal-notifier
```

‘시스템 설정 → 알림’에서 알림을 허용하세요.

## 라이선스 및 링크

- 라이선스: **MIT**
- 제작자: JellyNeko / bilibili @果冻猫猫丶
- [GitHub](https://github.com/JellyNekoNeko/toyoko-tracker)
- [PyPI](https://pypi.org/project/toyoko-tracker/)
