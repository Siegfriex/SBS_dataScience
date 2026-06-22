# SBS DataScience

SBS 데이터사이언스 실습과 노트북 실행을 위한 초기 환경 설정 저장소입니다.

## Python 환경

권장 Python 버전은 `3.12`입니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m ipykernel install --user --name sbs-datascience --display-name "SBS DataScience"
```

PyTorch, Keras, TensorFlow까지 포함한 ML 실습 환경이 필요하면 다음을 사용합니다.

```bash
python -m pip install -r requirements-ml.txt
```

설치 상태 점검:

```bash
python scripts/check_env.py
```

## R 환경

R 기반 실습이 필요하면 R 설치 후 다음을 실행합니다.

```bash
Rscript requirements.R
```

## Node.js / React / Spring Boot

개발용 언어와 웹/API 실습 환경은 다음 파일과 앱으로 초기 설정되어 있습니다.

- `.nvmrc`: Node.js 24 LTS 기준
- `.java-version`: Java 21 기준
- `package.json`: npm workspace와 공통 스크립트
- `apps/react-js`: Vite + React(JavaScript) 앱
- `apps/spring-boot`: Java 21 + Spring Boot API 앱
- `docs/development-stack.md`: 개발 스택 실행 가이드

```bash
nvm use
npm install
npm run dev:react
```

Spring Boot는 Java 21과 Maven 설치 후 실행합니다.

```bash
mvn -f apps/spring-boot/pom.xml spring-boot:run
```

통합 환경 점검:

```bash
npm run check:env
```

## 의존성 파일

- `requirements.txt`: 데이터 분석/시각화/노트북 기본 의존성
- `requirements-ml.txt`: PyTorch, Keras, TensorFlow 등 ML 확장 의존성
- `pyproject.toml`: 패키지 메타데이터와 optional dependency 그룹
- `environment.yml`: Conda/Mamba 기반 재현 환경
- `requirements.R`: R 데이터 분석 패키지 설치 스크립트
